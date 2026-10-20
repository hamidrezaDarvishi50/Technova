#!/usr/bin/env bash
set -e

echo "RUNNING technova Backend..."

echo "Waiting for PostgreSQL..."
while ! nc -z "${POSTGRES_HOST:-db}" "${POSTGRES_PORT:-5432}"; do
  echo "Waiting for PostgreSQL..."
  sleep 2
done
echo "Connected to PostgreSQL"

# Run migrations only for the Django web service
if [ "${1:-web}" = "web" ]; then
  python /home/app/manage.py migrate --noinput

  echo "Starting Gunicorn..."
  exec gunicorn config.wsgi:application \
    --name product-gunicorn \
    --bind "0.0.0.0:${APP_PORT:-8000}" \
    --workers "${GUNICORN_WORKER_NUMBER:-3}" \
    --pythonpath "/home/app/" \
    --log-level=info \
    --log-file=- \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --reload
fi

# Run the command passed by Docker Compose (e.g. Celery)
exec "$@"
