#!/bin/bash
# New, empty Gambit Ubuntu host only. Does not migrate data or start research.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo 'Run as root on the new cloud host'; exit 1; }
. /etc/os-release
[ "$ID" = ubuntu ] && [ "$VERSION_ID" = 24.04 ] || { echo 'Expected Ubuntu 24.04'; exit 1; }
[ ! -e /etc/gambit/worker-enabled ] || { echo 'Refusing an activated research host'; exit 1; }
export DEBIAN_FRONTEND=noninteractive
install -d -m 0755 /opt/gambit /usr/local/src/gambit
# Prevent the distribution default website from being exposed during installation.
systemctl mask caddy.service
apt-get update
apt-get -y upgrade
apt-get install -y build-essential pkg-config libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev libgdbm-dev libncursesw5-dev uuid-dev libzstd-dev xz-utils ca-certificates curl acl ufw caddy restic nodejs
cd /usr/local/src/gambit
if [ ! -x /opt/gambit/python-3.14.8/bin/python3.14 ]; then
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 -o Python-3.14.8.tar.xz https://www.python.org/ftp/python/3.14.8/Python-3.14.8.tar.xz
  echo 'c2215904f02b175596dc49351585104f4bc20341e1c47378b26a2c274360ce73  Python-3.14.8.tar.xz' | sha256sum --check --strict
  [ ! -e Python-3.14.8 ] || { echo 'Existing partial build; inspect before resuming'; exit 1; }
  tar -xf Python-3.14.8.tar.xz
  cd Python-3.14.8
  ./configure --prefix=/opt/gambit/python-3.14.8 --enable-optimizations --with-ensurepip=install
  make -j2
  make altinstall
fi
/opt/gambit/python-3.14.8/bin/python3.14 - <<'PY'
import sys, ssl, sqlite3, bz2, lzma, ctypes, fcntl, zlib, compression.zstd
assert sys.version_info[:3] == (3,14,8)
assert sys._is_gil_enabled()
print(sys.version)
print(ssl.OPENSSL_VERSION, 'SQLite', sqlite3.sqlite_version)
PY
if [ ! -d /opt/gambit/venv ]; then
  /opt/gambit/python-3.14.8/bin/python3.14 -m venv /opt/gambit/venv
fi
printf '%s\n' 'Runtime built. No production research or web service has been activated.'
