#!/bin/sh
# Run only after verified import; this is a separately recorded web/operations release.
set -eu
[ "$(id -u)" -eq 0 ]
mountpoint -q /srv/gambit
systemctl is-active --quiet gambit-web && { echo 'Stop web before configuring health.' >&2; exit 1; }
root=/srv/gambit/research_platform
install -m 0644 "$root/deploy/systemd/gambit-health.service" /etc/systemd/system/
install -m 0644 "$root/deploy/systemd/gambit-health.timer" /etc/systemd/system/
if ! grep -q '^GAMBIT_HEALTH_STATUS_FILE=' /etc/gambit/web.env; then
    printf '\nGAMBIT_HEALTH_STATUS_FILE=/run/gambit-health/status.json\n' >> /etc/gambit/web.env
fi
systemctl daemon-reload
# Enable with the web/worker after backup acceptance, never from an import script.
