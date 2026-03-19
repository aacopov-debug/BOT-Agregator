FROM python:3.12-slim

# Установка системных зависимостей (ffmpeg для pydub)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка зависимостей Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование проекта
COPY . .

# Команда по умолчанию (будет переопределена в docker-compose)
CMD ["python", "main.py"]
