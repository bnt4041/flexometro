FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# curl para el healthcheck; las librerías Pango/Cairo/gdk-pixbuf son las que
# WeasyPrint necesita para componer y rasterizar el PDF genérico de listados
# (Fase 20 y 21). libreoffice-writer + fonts-liberation son para convertir a
# PDF las plantillas Word rellenadas (Fase 39): fonts-liberation tiene las
# métricas compatibles con Arial/Times/Calibri, así que el PDF no reajusta
# saltos de línea del Word original.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        fonts-dejavu-core \
        libreoffice-writer \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Las dependencias primero: cambiar código no invalida esta capa.
# INSTALL_DEV=false produce la imagen de producción, sin pytest ni ruff.
ARG INSTALL_DEV=true
COPY requirements.txt requirements-dev.txt ./
RUN if [ "$INSTALL_DEV" = "true" ]; then \
        pip install --no-cache-dir -r requirements-dev.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
