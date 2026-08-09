# Life-Dash — backend + frontend in one container
#
# Anmerkung 210: Das Basis-Image ist am DIGEST festgenagelt, nicht nur am Tag.
# `python:3.13-slim` zeigt jede Woche auf etwas anderes — bequem für
# Sicherheitsaktualisierungen, unbrauchbar als Aussage darüber, was gebaut
# wurde. Der Tag steht als Kommentar daneben, damit lesbar bleibt, worauf der
# Digest zeigt; Dependabot hebt beides gemeinsam an (`.github/dependabot.yml`).
# **Ein Digest ohne einen Mechanismus, der ihn anhebt, ist eine Konserve** —
# deshalb kommt das eine nicht ohne das andere.
FROM python:3.13-slim@sha256:9662417aace5ae7b8e2609cce472b72a8958e134ba372808abe9cc1a0c0125e6

# Links the GHCR package to the repo (visibility, overview page)
LABEL org.opencontainers.image.source="https://github.com/Noxon007/life-dash" \
      org.opencontainers.image.description="Life-Dash — your searchable life database" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

WORKDIR /app

# Anmerkung 210: Der Anwendungsbenutzer. Feste Kennung, weil sie auf dem HOST
# sichtbar wird — die Dateien in `./data` und `./media` gehören danach 10001,
# und wer sie sichert, muss wissen, wem. Eine vom System vergebene Kennung
# wäre bei jedem Neubau des Images eine andere.
RUN groupadd --gid 10001 lifedash \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin lifedash

# Dependencies first (Docker layer cache)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary

# App code + module definitions + frontend
COPY backend/app ./app
COPY backend/modules ./modules
COPY frontend ./frontend
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Herkunft des Images. Bewusst NACH den COPY-Schritten: diese Werte ändern
# sich bei jedem Commit und würden weiter oben den Ebenen-Cache zerstören.
# Die Versionsnummer steht weiterhin allein in app/version.py (A3) — das hier
# beantwortet eine andere Frage: „welcher Bau bin ich?". Nötig, seit es
# :main-Images gibt, die zwischen zwei Versionen liegen.
ARG BUILD_REF=""
ARG BUILD_SHA=""

ENV MODULES_DIR=/app/modules \
    FRONTEND_DIR=/app/frontend \
    DATABASE_URL=sqlite:////data/lifedash.db \
    BUILD_REF=${BUILD_REF} \
    BUILD_SHA=${BUILD_SHA}

VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# Der Einstiegspunkt übereignet die beschreibbaren Verzeichnisse und gibt dann
# die Rechte ab — siehe docker-entrypoint.sh. Der Container endet als 10001.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# --proxy-headers: X-Forwarded-For/-Proto vom Reverse Proxy übernehmen.
#
# Anmerkung 210: `--forwarded-allow-ips` ist einstellbar geworden und steht
# vorgabeweise weiter auf `*`. Das ist eine ENTSCHEIDUNG und keine Nachlässigkeit:
# der Proxy hat im Docker-Netz keine feste Adresse, und eine falsche Angabe
# äußert sich als eine Anwendung, die sich für unverschlüsselt hält — also als
# stiller Fehler. Wer die Adresse seines Proxys kennt, trägt sie in der .env als
# FORWARDED_ALLOW_IPS ein; DEPLOY.md sagt, warum das die bessere Wahl ist.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-*}\""]
