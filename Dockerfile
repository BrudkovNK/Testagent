FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb x11vnc fluxbox novnc websockify \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium
COPY src/ ./src/
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV DISPLAY=:99 \
    HEADLESS=false \
    USER_DATA_DIR=/data/browser_profile \
    PYTHONUNBUFFERED=1

VOLUME ["/data/browser_profile"]

EXPOSE 7900 5900

ENTRYPOINT ["/entrypoint.sh"]
CMD ["tail", "-f", "/dev/null"]
