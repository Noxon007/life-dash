# Life-Dash — backend + frontend in one container
#
# Anmerkung 210: Das Basis-Image ist am DIGEST festgenagelt, nicht nur am Tag.
# `python:3.13-slim` zeigt jede Woche auf etwas anderes — bequem für
# Sicherheitsaktualisierungen, unbrauchbar als Aussage darüber, was gebaut
# wurde. Der Tag steht als Kommentar daneben, damit lesbar bleibt, worauf der
# Digest zeigt; Dependabot hebt beides gemeinsam an (`.github/dependabot.yml`).
# **Ein Digest ohne einen Mechanismus, der ihn anhebt, ist eine Konserve** —
# deshalb kommt das eine nicht ohne das andere.
FROM python:3.14-slim@sha256:a7fb1e634c4a578f9e0bd6327f11a3cde11b7a9395f48e24360c0988bcc5c2bc

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
# Anmerkung 223: `psycopg2-binary` stand hier ungepinnt hinter der Datei — die
# einzige Abhängigkeit des Images ohne feste Version, und ausgerechnet der
# Datenbanktreiber. Das Basis-Image ist am Digest festgenagelt, mit der
# Begründung, ein Tag sei „unbrauchbar als Aussage darüber, was gebaut wurde";
# ein Treiber, der bei jedem Bau ein anderer sein darf, hebt genau diese Aussage
# wieder auf. Er steht jetzt in `requirements.txt` und wird von Dependabot
# mitgehoben wie alles andere.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

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

# Anmerkung 223: `MEDIA_DIR` gehört dazu, und zwar hierher.
#
# Drei der vier Pfade standen hier, der vierte nicht — und `config.py` legt ihn
# vorgabeweise neben den Code (`/app/media`). Über `docker compose` fiel das nie
# auf: die Compose-Datei setzt ihn. Wer das Image direkt startet, bekam dagegen
# beides auf einmal: die hochgeladenen Bilder landen AUSSERHALB des
# `/data`-Volumes (weg beim nächsten `docker run`), und `/app` gehört root,
# während der Prozess als 10001 läuft — der erste Upload scheitert.
#
# Derselbe Wert steht im Einstiegspunkt als Vorgabe (`${MEDIA_DIR:-/data/media}`).
# Ein Image, das seine eigene Vorgabe anders beantwortet als sein Einstiegspunkt,
# ist die Doppelregel in ihrer teuersten Form: sie stimmt auf dem dokumentierten
# Weg und nur dort.
ENV MODULES_DIR=/app/modules \
    FRONTEND_DIR=/app/frontend \
    DATABASE_URL=sqlite:////data/lifedash.db \
    MEDIA_DIR=/data/media \
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
