FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils libproj-dev gdal-bin libgdal-dev libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py create_admin_from_env && if [ \"$LOAD_SEED_DATA\" = \"1\" ]; then python manage.py seed_ghg_data; fi && python manage.py generate_catalogo && python manage.py collectstatic --noinput && gunicorn colflux.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]
