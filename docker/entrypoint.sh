#!/bin/bash
set -e
rm -f /tmp/.X99-lock

Xvfb :99 -screen 0 1440x900x24 &
sleep 1

fluxbox &

x11vnc -display :99 -forever -shared -nopw -rfbport 5900 -quiet &
sleep 1

websockify --web=/usr/share/novnc/ 7900 localhost:5900 &

echo ""
echo "======================================================================"
echo " Контейнер запущен."
echo " Смотреть на работу браузера:  http://localhost:7900/vnc.html"
echo " Отправить задачу агенту:      docker compose exec agent python -m src.cli \"твоя задача\""
echo "======================================================================"
echo ""

exec "$@"
