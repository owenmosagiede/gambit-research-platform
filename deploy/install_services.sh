#!/bin/sh
# Execute only on the new Linux host, after its verified research volume is mounted.
set -eu
[ "$(id -u)" -eq 0 ] || { echo 'Run as root on the cloud host.' >&2; exit 1; }
[ "$(uname -s)" = Linux ] || exit 1
mountpoint -q /srv/gambit || { echo 'Research volume is not mounted.' >&2; exit 1; }
[ -f /srv/gambit/research_platform/migration-manifest.json ] || { echo 'Verified migration is required.' >&2; exit 1; }
for unit in gambit-web gambit-worker; do
    if systemctl is-active --quiet "$unit"; then echo 'Drain and stop services before installation.' >&2; exit 1; fi
done
/opt/gambit/venv/bin/python -c 'import sys; assert sys.version_info[:3] == (3,14,8), "Cloud Python must be 3.14.8"'
/opt/gambit/venv/bin/python /srv/gambit/research_platform/tools/cloud_migration.py verify --root /srv/gambit/research_platform --output /srv/gambit/research_platform/migration-manifest.json
getent passwd gambit >/dev/null || useradd --system --home-dir /srv/gambit --shell /usr/sbin/nologin gambit
install -d -m 0750 -o root -g gambit /etc/gambit
install -d -m 0700 -o gambit -g gambit /srv/gambit/auth
chown root:gambit /srv/gambit
chmod 0750 /srv/gambit
chown -R root:gambit /srv/gambit/research_platform
chmod -R o-rwx /srv/gambit/research_platform
# The export root is deliberately private on the Mac; allow the service group
# to traverse its imported deployment root without opening access to others.
chmod 0750 /srv/gambit/research_platform
chown -R gambit:gambit /srv/gambit/research_platform/storage
if [ ! -e /etc/gambit/session-secret ]; then
    /opt/gambit/venv/bin/python -c 'import os,secrets; fd=os.open("/etc/gambit/session-secret",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o640); os.write(fd,secrets.token_urlsafe(64).encode()); os.close(fd)'
    chown root:gambit /etc/gambit/session-secret
    chmod 0640 /etc/gambit/session-secret
fi
[ -e /etc/gambit/web.env ] || install -m 0640 -o root -g gambit /srv/gambit/research_platform/deploy/production.env.example /etc/gambit/web.env
install -m 0644 /srv/gambit/research_platform/deploy/systemd/gambit-web.service /etc/systemd/system/
install -m 0644 /srv/gambit/research_platform/deploy/systemd/gambit-worker.service /etc/systemd/system/
install -m 0644 /srv/gambit/research_platform/deploy/systemd/gambit-backup.service /etc/systemd/system/
install -m 0644 /srv/gambit/research_platform/deploy/systemd/gambit-backup.timer /etc/systemd/system/
systemctl daemon-reload
# Deliberately do not enable/start anything or activate production submissions here.
echo 'Services installed disabled. Complete Linux tests, auth provisioning, restore proof, DNS and acceptance before enabling.'
