# Life-Dash — Backend + Frontend in einem Container
FROM python:3.13-slim

# Verknüpft das GHCR-Package mit dem Repo (Sichtbarkeit, Übersichtsseite)
LABEL org.opencontainers.image.source="https://github.com/Noxon007/life-dash" \
      org.opencontainers.image.description="Life-Dash — die durchsuchbare Lebensdatenbank" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Abhängigkeiten zuerst (Docker-Layer-Cache)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary

# App-Code + Modul-Definitionen + Frontend
COPY backend/app ./app
COPY backend/modules ./modules
COPY frontend ./frontend

ENV MODULES_DIR=/app/modules \
    FRONTEND_DIR=/app/frontend \
    DATABASE_URL=sqlite:////data/lifedash.db

VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# --proxy-headers: X-Forwarded-For/-Proto vom Reverse Proxy (Pangolin/Traefik) übernehmen
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
