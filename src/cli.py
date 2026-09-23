from __future__ import annotations

import sys

from .agent import BrowserAgent, CLIBridge
from .browser_controller import BrowserController
from .config import CONFIG
from .llm_client import get_llm_client


def main():
    problems = CONFIG.validate()
    if problems:
        print("Конфигурация некорректна:")
        for p in problems:
            print(f"  - {p}")
        print("\nЗаполните .env (см. .env.example) и попробуйте снова.")
        sys.exit(1)

    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        print("Введите задачу для агента (например: «Найди 3 подходящие вакансии AI-инженера на hh.ru и откликнись»):")
        task = input("> ").strip()
        if not task:
            print("Задача не задана, выход.")
            sys.exit(1)

    print(f"\n Задача: {task}")
    print("Запускаю браузер (видимый, с сохранением сессии)…")
    print(f"Профиль браузера: {CONFIG.user_data_dir} (войдите в нужные сервисы вручную, если требуется, "
          f"дальше агент продолжит с этой же сессией)\n")

    cli = CLIBridge()
    llm = get_llm_client(CONFIG)

    with BrowserController(CONFIG) as browser:
        agent = BrowserAgent(task=task, browser=browser, llm=llm, cli=cli, cfg=CONFIG)
        try:
            result = agent.run()
        except KeyboardInterrupt:
            print("\n  Остановлено пользователем.")
            sys.exit(130)


    print("ГОТОВО" if result.success else "  ЗАВЕРШЕНО БЕЗ ПОЛНОГО УСПЕХА")
    print(f"Шагов выполнено: {result.steps_taken}")
    print(result.summary)



if __name__ == "__main__":
    main()
