#!/bin/bash

echo "🚀 Начало обновления бота..."

# 1. Загружаем свежий код из GitHub
git pull origin main

# 2. Пересобираем и запускаем контейнеры
docker compose up -d --build

# 3. Очистка старых ненужных образов
docker image prune -f

echo "✅ Бот успешно обновлен и запущен!"
echo "📊 Дашборд доступен на порту 8000."
