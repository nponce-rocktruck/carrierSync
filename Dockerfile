FROM python:3.11-slim

WORKDIR /app

# Copiar requirements primero para aprovechar cache de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Cloud Run expone por defecto el puerto 8080
ENV PORT=8080
EXPOSE 8080

# Cloud Run requiere escuchar en 0.0.0.0 y en el puerto PORT
CMD sh -c "echo 'Iniciando CarrierSync API en puerto ${PORT:-8080}' && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --timeout-keep-alive 30 --timeout-graceful-shutdown 10 --log-level info --no-access-log --limit-concurrency 1000"
