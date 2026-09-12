# El servidor de "A mí me strofa" para Cloud Run.
# El modelo NO va dentro: se lee de GCS al arrancar (MESTROFA_MODELO=gs://...),
# así reentrenar no obliga a reconstruir la imagen.
FROM python:3.14-slim

WORKDIR /app
COPY servidor/requirements.txt servidor/requirements.txt
RUN pip install --no-cache-dir -r servidor/requirements.txt

COPY src/*.py src/
COPY servidor/*.py servidor/

# Cloud Run pasa el puerto en $PORT.
CMD exec uvicorn --factory servidor.app:desde_entorno --host 0.0.0.0 --port ${PORT:-8080}
