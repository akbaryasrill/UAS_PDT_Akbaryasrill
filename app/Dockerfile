# UAS-PDT/app/Dockerfile

FROM python:3.9-alpine

WORKDIR /app

# Instal dependensi Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instal dependensi sistem untuk driver database
# psycopg2-binary membutuhkan build-base dan libpq-dev
# pymongo dan redis tidak membutuhkan dependensi sistem khusus di alpine
RUN apk add --no-cache \
    build-base \
    postgresql-dev \
    gcc \
    musl-dev

# Copy aplikasi Flask dan skrip ETL
COPY . .

# Exposure port Flask
EXPOSE 5000

# Perintah default untuk menjalankan aplikasi Flask (akan di-override oleh docker-compose)
CMD ["python3", "app.py"]
