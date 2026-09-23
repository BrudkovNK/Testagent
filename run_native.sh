#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

pip install -q -r requirements.txt
python -m playwright install chromium

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Создан .env из .env.example — впишите туда ANTHROPIC_API_KEY и запустите скрипт снова."
    exit 1
fi

python -m src.cli "$@"
