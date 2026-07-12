FROM python:3.12-slim

WORKDIR /app

# Copy requirements first — Docker caches this layer separately.
# As long as requirements.txt doesn't change, pip install is skipped on rebuild.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run as a non-root user so container compromise doesn't grant root access.
# Use an explicit numeric UID/GID so Kubernetes' runAsNonRoot can verify the
# user is non-root at admission (it cannot verify a username alone).
RUN addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app app

# Copy the rest of the app and hand ownership over to the app user
COPY . .
RUN chown -R app:app /app

USER 10001

ENV FLASK_ENV=production

EXPOSE 5001

CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "4", "--threads", "8", "--timeout", "120", "wsgi:app"]
