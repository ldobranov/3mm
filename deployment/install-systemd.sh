#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi
if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo "Usage: $0 RELEASE_ARCHIVE RELEASE_ID FRONTEND_ORIGIN [IDENTITY_FILE]" >&2
  exit 1
fi

release_archive=$(realpath "$1")
release_id=$2
frontend_origin=$3
identity_source=${4:-}

if [[ ! $release_id =~ ^[a-zA-Z0-9._-]+$ ]]; then
  echo "Release ID contains unsupported characters." >&2
  exit 1
fi
if [[ $frontend_origin != http://* && $frontend_origin != https://* ]]; then
  echo "Frontend origin must use http or https." >&2
  exit 1
fi

install_root=/opt/3mm
release_dir=$install_root/releases/$release_id
venv_dir=$install_root/venv

if ! id -u 3mm >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/3mm --shell /usr/sbin/nologin 3mm
fi

install -d -o root -g root -m 0755 "$install_root/releases"
install -d -o root -g root -m 0755 /etc/3mm
install -d -o 3mm -g 3mm -m 0750 /var/lib/3mm
install -d -o 3mm -g 3mm -m 0700 /var/lib/3mm/agent

if [[ -n $identity_source && ! -e /var/lib/3mm/agent/identity.json ]]; then
  install -o 3mm -g 3mm -m 0600 "$identity_source" \
    /var/lib/3mm/agent/identity.json
fi

systemctl stop 3mm-agent.service 3mm-core.service 3mm-web.service \
  3mm-setup.service 3mm-setup-ap.service 3mm-network-helper.service \
  >/dev/null 2>&1 || true
rm -rf -- "$release_dir"
install -d -o root -g root -m 0755 "$release_dir"
tar -xzf "$release_archive" -C "$release_dir"

if [[ ! -x $venv_dir/bin/python ]]; then
  python3 -m venv "$venv_dir"
fi
"$venv_dir/bin/python" -m pip install --disable-pip-version-check \
  -r "$release_dir/backend/requirements.txt"

ln -sfn "$release_dir" "$install_root/current"
install -o root -g root -m 0644 -t /etc/systemd/system \
  "$release_dir/deployment/systemd/3mm-agent.service" \
  "$release_dir/deployment/systemd/3mm-core.service" \
  "$release_dir/deployment/systemd/3mm-web.service" \
  "$release_dir/deployment/systemd/3mm-setup.service" \
  "$release_dir/deployment/systemd/3mm-setup-ap.service" \
  "$release_dir/deployment/systemd/3mm-network-helper.service"

cat > /etc/3mm/3mm.env <<EOF
DATABASE_URL=sqlite:////var/lib/3mm/core/3mm.db
UPLOADS_DIR=/var/lib/3mm/core/uploads
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8887
CORS_ORIGINS=["$frontend_origin"]
DEVICE_OFFLINE_AFTER_SECONDS=90
THREE_MM_AGENT_HOST=127.0.0.1
THREE_MM_AGENT_PORT=8890
THREE_MM_AGENT_ROLE=standalone
THREE_MM_AGENT_HARDWARE_PROFILE=native
THREE_MM_CORE_URL=http://127.0.0.1:8887
THREE_MM_HEARTBEAT_INTERVAL_SECONDS=30
THREE_MM_PROVISIONING_DATA_DIR=/var/lib/3mm/provisioning
EOF
chown root:3mm /etc/3mm/3mm.env
chmod 0640 /etc/3mm/3mm.env

install -d -o 3mm -g 3mm -m 0750 /var/lib/3mm/core
runuser -u 3mm -- env \
  DATABASE_URL=sqlite:////var/lib/3mm/core/3mm.db \
  PYTHONPATH="$release_dir" \
  "$venv_dir/bin/python" "$release_dir/deployment/migrate_database.py"

systemctl daemon-reload
PYTHONPATH="$release_dir" "$venv_dir/bin/python" -m three_mm_runtime.activate

for service_endpoint in \
  '3mm-agent.service|http://127.0.0.1:8890/ready' \
  '3mm-core.service|http://127.0.0.1:8887/ready' \
  '3mm-web.service|http://127.0.0.1:8080/user/login' \
  '3mm-setup.service|http://127.0.0.1:8895/ready'
do
  service=${service_endpoint%%|*}
  endpoint=${service_endpoint#*|}
  systemctl is-active --quiet "$service" || continue
  for _ in $(seq 1 60); do
    curl -fsS "$endpoint" >/dev/null 2>&1 && break
    sleep 0.5
  done
  curl -fsS "$endpoint" >/dev/null
done

systemctl --no-pager --full status \
  3mm-agent.service 3mm-core.service 3mm-web.service \
  3mm-setup.service 3mm-setup-ap.service 3mm-network-helper.service \
  2>/dev/null || true
