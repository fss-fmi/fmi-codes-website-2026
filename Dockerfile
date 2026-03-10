FROM python:3.12-slim

WORKDIR /app

# Copy requirements first — Docker caches this layer separately.
# As long as requirements.txt doesn't change, pip install is skipped on rebuild.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

ENV FLASK_ENV=production

EXPOSE 5001

CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "4", "--threads", "4", "--timeout", "120", "wsgi:app"]
