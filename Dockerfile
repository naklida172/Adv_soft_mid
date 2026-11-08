FROM python:3.13-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Открытие порта
EXPOSE 8000

# Запуск FastAPI сервиса
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

