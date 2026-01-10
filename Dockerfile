FROM python:3.11-slim

# Instaliraj git i curl (potrebno za neke operacije)
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Prvo kopiraj requirements (zbog keširanja)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiraj ostatak koda
COPY . .

# Postavi putanju da Python vidi tvoje module
ENV PYTHONPATH=/app

# Pokreni skriptu
ENTRYPOINT ["python", "/app/main.py"]