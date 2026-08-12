#!/bin/sh
# Anmerkung 210: Der Container läuft nicht mehr als root — aber er startet so.
#
# Der Grund ist der Bind-Mount. `./data` und `./media` liegen auf dem Host und
# bringen dessen Besitzverhältnisse mit; ein Image, das direkt als unbekannter
# Benutzer startet, kann in ein bestehendes Verzeichnis nicht schreiben, und
# das äußert sich beim Aktualisieren als eine Instanz, die nicht mehr hochkommt.
# Genau dafür gibt es diesen Zwischenschritt: als root das Verzeichnis
# übereignen, dann die Rechte abgeben und erst danach die Anwendung starten.
#
# Wer `user:` in der Compose-Datei setzt, kommt hier gar nicht als root an —
# dann wird nichts übereignet und direkt gestartet. Das ist beabsichtigt: eine
# ausdrückliche Angabe des Betreibers gewinnt gegen die Bequemlichkeit.
set -e

APP_UID=10001
APP_GID=10001

if [ "$(id -u)" = "0" ]; then
    # Nur die beiden Verzeichnisse, in die geschrieben wird. Ein `chown -R /`
    # wäre bequemer und würde jede Datei des Images anfassen, die niemand
    # ändern soll — der Code gehört ausdrücklich weiter root und ist für den
    # Anwendungsbenutzer nur lesbar.
    # Anmerkung 223: Erst FRAGEN, dann übereignen.
    #
    # `chown -R` lief bei jedem Start über den ganzen Baum. In der Compose-Datei
    # liegt `./media` unter `/data/media`, also INNERHALB des ersten Eintrags —
    # der rekursive Lauf fasst damit jedes Foto an, und die Schleife danach
    # gleich noch einmal. Bei einigen zehntausend Bildern auf einer SD-Karte
    # sind das Sekunden bis Minuten vor jedem Neustart, für Rechte, die sich
    # seit dem letzten Mal nicht geändert haben.
    #
    # Geprüft wird das Verzeichnis selbst: gehört es bereits dem
    # Anwendungsbenutzer, war der letzte Lauf erfolgreich und der Inhalt ist es
    # auch. `-h` sonst nicht nötig; `stat -c` gibt es in Debian-Slim.
    for dir in /data "${MEDIA_DIR:-/data/media}"; do
        [ -d "$dir" ] || mkdir -p "$dir"
        owner="$(stat -c '%u:%g' "$dir" 2>/dev/null || echo '?')"
        [ "$owner" = "$APP_UID:$APP_GID" ] && continue
        echo "Übereigne $dir an $APP_UID:$APP_GID (bisher $owner) — einmalig." >&2
        chown -R "$APP_UID:$APP_GID" "$dir" 2>/dev/null || \
            echo "Hinweis: $dir konnte nicht übereignet werden — liegt es auf" \
                 "einem Netzlaufwerk? Falls die App nicht schreiben kann," \
                 "auf dem Host: chown -R $APP_UID:$APP_GID <ordner>" >&2
    done

    # Rechte abgeben. `setpriv` und `su` kommen beide aus util-linux bzw.
    # passwd und sind in Debian-Slim vorhanden; geprüft wird trotzdem, und
    # zwar LAUT. Ein Rückfall auf „dann eben als root" wäre die Sorte Stille,
    # gegen die diese ganze Runde gebaut ist: die Härtung wäre weg, und
    # niemand erführe es.
    if command -v setpriv >/dev/null 2>&1; then
        exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --init-groups "$@"
    elif command -v su >/dev/null 2>&1; then
        exec su lifedash -s /bin/sh -c 'exec "$0" "$@"' -- "$@"
    fi
    echo "FEHLER: Weder setpriv noch su vorhanden — die Rechte lassen sich" \
         "nicht abgeben, und als root startet dieser Container nicht." >&2
    exit 1
fi

exec "$@"
