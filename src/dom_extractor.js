
(function () {
  const INTERACTIVE_SELECTOR = [
    "a[href]", "button", "input", "textarea", "select", "option",
    "[role=button]", "[role=link]", "[role=checkbox]", "[role=radio]",
    "[role=tab]", "[role=menuitem]", "[role=switch]", "[role=combobox]",
    "[role=searchbox]", "[role=option]", "[onclick]",
    "[contenteditable=true]", "summary", "label[for]",
  ].join(",");

  function isVisible(el) {
    if (!el.isConnected) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || parseFloat(style.opacity) === 0) {
      return false;
    }
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function inViewport(rect) {
    return (
      rect.bottom > 0 &&
      rect.right > 0 &&
      rect.top < (window.innerHeight || document.documentElement.clientHeight) &&
      rect.left < (window.innerWidth || document.documentElement.clientWidth)
    );
  }

  function truncate(s, n) {
    if (!s) return "";
    s = s.replace(/\s+/g, " ").trim();
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  function accessibleName(el) {
    const aria = el.getAttribute("aria-label");
    if (aria) return truncate(aria, 120);
    const labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      const labelEl = document.getElementById(labelledBy);
      if (labelEl) return truncate(labelEl.innerText, 120);
    }
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      const ph = el.getAttribute("placeholder");
      if (ph) return truncate(ph, 120);
      if (el.type !== "password" && el.value) return truncate(el.value, 120);
      // попытка найти связанный <label>
      if (el.id) {
        const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (lbl) return truncate(lbl.innerText, 120);
      }
    }
    if (el.tagName === "IMG" && el.alt) return truncate(el.alt, 120);
    const title = el.getAttribute("title");
    if (title) return truncate(title, 120);
    return truncate(el.innerText || el.value || "", 120);
  }

  function implicitRole(el) {
    const explicit = el.getAttribute("role");
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === "a") return "link";
    if (tag === "button") return "button";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {
      const t = (el.getAttribute("type") || "text").toLowerCase();
      if (["checkbox"].includes(t)) return "checkbox";
      if (["radio"].includes(t)) return "radio";
      if (["submit", "button"].includes(t)) return "button";
      return "textbox";
    }
    return tag;
  }

  window.__agentExtract = function (opts) {
    opts = opts || {};
    const maxElements = opts.maxElements || 150;
    const textCap = opts.textCap || 200;

    const nodeList = Array.from(document.querySelectorAll(INTERACTIVE_SELECTOR));
    const seen = new Set();
    const elements = [];
    window.__agentElements = [];

    for (const el of nodeList) {
      if (seen.has(el)) continue;
      seen.add(el);
      if (!isVisible(el)) continue;
      if (el.disabled) continue;

      const rect = el.getBoundingClientRect();
      const idx = window.__agentElements.length;
      window.__agentElements.push(el);

      const tag = el.tagName.toLowerCase();
      const entry = {
        index: idx,
        tag: tag,
        role: implicitRole(el),
        name: accessibleName(el),
        inViewport: inViewport(rect),
        rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
      };
      if (tag === "input") {
        entry.inputType = el.getAttribute("type") || "text";
        if (entry.inputType === "checkbox" || entry.inputType === "radio") {
          entry.checked = !!el.checked;
        }
      }
      if (tag === "a") {
        const href = el.getAttribute("href") || "";
        entry.href = truncate(href, 80);
      }
      if (tag === "select") {
        entry.selected = truncate(el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : "", 60);
      }
      elements.push(entry);
      if (elements.length >= maxElements) break;
    }

    // немного метаданных о странице для ориентации агента
    const headings = Array.from(document.querySelectorAll("h1,h2,h3"))
      .slice(0, 8)
      .map((h) => truncate(h.innerText, 100))
      .filter(Boolean);

    return JSON.stringify({
      url: window.location.href,
      title: document.title,
      scrollY: window.scrollY,
      scrollHeight: document.documentElement.scrollHeight,
      viewportHeight: window.innerHeight,
      totalInteractiveFound: nodeList.length,
      elementsReturned: elements.length,
      headings: headings,
      elements: elements,
    });
  };

  // --- Set-of-marks: рисуем номерные бейджи прямо на странице перед скриншотом ---
  window.__agentMark = function () {
    window.__agentUnmark();
    const layer = document.createElement("div");
    layer.id = "__agent_mark_layer";
    layer.style.position = "fixed";
    layer.style.top = "0";
    layer.style.left = "0";
    layer.style.zIndex = "2147483647";
    layer.style.pointerEvents = "none";
    document.body.appendChild(layer);

    (window.__agentElements || []).forEach((el, idx) => {
      if (!el.isConnected) return;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      if (rect.bottom < 0 || rect.top > window.innerHeight) return; // только видимая область

      const box = document.createElement("div");
      box.style.position = "fixed";
      box.style.left = rect.x + "px";
      box.style.top = rect.y + "px";
      box.style.width = rect.width + "px";
      box.style.height = rect.height + "px";
      box.style.border = "2px solid #ff3366";
      box.style.boxSizing = "border-box";
      box.style.pointerEvents = "none";

      const badge = document.createElement("div");
      badge.textContent = idx;
      badge.style.position = "fixed";
      badge.style.left = rect.x + "px";
      badge.style.top = Math.max(0, rect.y - 14) + "px";
      badge.style.background = "#ff3366";
      badge.style.color = "#fff";
      badge.style.font = "bold 11px monospace";
      badge.style.padding = "1px 3px";
      badge.style.borderRadius = "2px";
      badge.style.lineHeight = "1";

      layer.appendChild(box);
      layer.appendChild(badge);
    });
  };

  window.__agentUnmark = function () {
    const layer = document.getElementById("__agent_mark_layer");
    if (layer) layer.remove();
  };
})();
