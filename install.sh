#!/usr/bin/env bash
set -Eeuo pipefail

readonly THREE_MM_REPOSITORY="ldobranov/3mm"
readonly THREE_MM_DEFAULT_CHANNEL="beta"
readonly THREE_MM_BOOTSTRAP_ROOT="/var/tmp/3mm-bootstrap"
readonly -a THREE_MM_BOOTSTRAP_PACKAGES=(
  avahi-daemon
  ca-certificates
  curl
  dnsmasq-base
  network-manager
  nodejs
  npm
  python3
  python3-venv
  util-linux
)

channel=${THREE_MM_CHANNEL:-$THREE_MM_DEFAULT_CHANNEL}
requested_tag=${THREE_MM_TAG:-}
frontend_origin=${THREE_MM_FRONTEND_ORIGIN:-}

usage() {
  cat <<'EOF'
Install the latest published 3mm release as a detached systemd job.

Usage:
  wget -qO- https://raw.githubusercontent.com/ldobranov/3mm/main/install.sh | sudo bash

Options:
  --channel stable|beta|test  Release channel (default: beta)
  --tag vX.Y.Z[-suffix]      Install one exact published release
  --frontend-origin URL      Public HTTP(S) origin; defaults to this device IP
  -h, --help                 Show this help

The job is detached before 3mm changes Wi-Fi into its setup access point, so
installation can safely be started over a Wi-Fi SSH connection.
EOF
}

fail() {
  printf '3mm install failed: %s\n' "$1" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --channel)
      [[ $# -ge 2 ]] || fail "--channel requires a value"
      channel=$2
      shift 2
      ;;
    --tag)
      [[ $# -ge 2 ]] || fail "--tag requires a value"
      requested_tag=$2
      shift 2
      ;;
    --frontend-origin)
      [[ $# -ge 2 ]] || fail "--frontend-origin requires a value"
      frontend_origin=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1"
      ;;
  esac
done

[[ $channel == stable || $channel == beta || $channel == test ]] || \
  fail "channel must be stable, beta or test"
[[ -z $requested_tag || $requested_tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] || \
  fail "tag must use vX.Y.Z semantic-version form"
[[ ${EUID:-$(id -u)} -eq 0 ]] || \
  fail "run through sudo, for example: wget -qO- .../install.sh | sudo bash"

for command in apt-get hostname python3 sha256sum stat systemctl systemd-run tar wget; do
  command -v "$command" >/dev/null 2>&1 || fail "required command is missing: $command"
done

architecture=$(uname -m)
case "$architecture" in
  aarch64|armv7l|x86_64) ;;
  *) fail "unsupported architecture: $architecture" ;;
esac

if [[ -z $frontend_origin ]]; then
  primary_address=$(hostname -I | tr ' ' '\n' | sed '/^$/d' | head -n 1)
  [[ $primary_address =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || \
    fail "could not detect a LAN IPv4 address; use --frontend-origin"
  frontend_origin="http://$primary_address"
fi
[[ $frontend_origin =~ ^https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?$ ]] || \
  fail "frontend origin must be a plain HTTP(S) origin without a path"

install -d -o root -g root -m 0700 "$THREE_MM_BOOTSTRAP_ROOT"
stage=$(mktemp -d "$THREE_MM_BOOTSTRAP_ROOT/bootstrap.XXXXXX")
chmod 0700 "$stage"
job_started=0

cleanup_before_start() {
  if [[ $job_started -eq 0 ]]; then
    rm -f -- "$stage"/* 2>/dev/null || true
    rmdir -- "$stage" 2>/dev/null || true
  fi
}
trap cleanup_before_start EXIT

release_json="$stage/release.json"
selected_tag_file="$stage/tag"
manifest="$stage/3mm-update-manifest.json"
packages_file="$stage/packages"
artifact_file_name="$stage/artifact-filename"
artifact_url_file="$stage/artifact-url"
artifact_sha_file="$stage/artifact-sha256"
artifact_size_file="$stage/artifact-size"
release_id_file="$stage/release-id"

printf 'Selecting the published %s release for %s...\n' "$channel" "$architecture"
if [[ -n $requested_tag ]]; then
  release_api="https://api.github.com/repos/$THREE_MM_REPOSITORY/releases/tags/$requested_tag"
else
  release_api="https://api.github.com/repos/$THREE_MM_REPOSITORY/releases?per_page=20"
fi
wget --https-only --secure-protocol=TLSv1_2 --timeout=30 --tries=3 \
  -qO "$release_json" "$release_api" || fail "could not read the GitHub release catalog"

python3 - "$release_json" "$channel" "$requested_tag" "$selected_tag_file" <<'PY'
import json
import re
import sys
from pathlib import Path

source, channel, requested_tag, output = sys.argv[1:]
payload = json.loads(Path(source).read_text(encoding="utf-8"))
tag_pattern = re.compile(r"^v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def tag_channel(tag: str) -> str:
    suffix = tag[1:].partition("-")[2]
    if not suffix:
        return "stable"
    return "test" if suffix.split(".", 1)[0].lower() == "test" else "beta"


def valid_release(item: object) -> bool:
    if not isinstance(item, dict) or item.get("draft") is True:
        return False
    tag = item.get("tag_name")
    if not isinstance(tag, str) or tag_pattern.fullmatch(tag) is None:
        return False
    return (
        tag_channel(tag) == channel
        and (item.get("prerelease") is True) == (channel != "stable")
    )


if requested_tag:
    if not valid_release(payload) or payload.get("tag_name") != requested_tag:
        raise SystemExit("Requested tag is not a published release in this channel")
    selected = payload
else:
    if not isinstance(payload, list):
        raise SystemExit("GitHub release catalog has an invalid shape")
    selected = next((item for item in payload if valid_release(item)), None)
    if selected is None:
        raise SystemExit(f"No published {channel} release is available")

Path(output).write_text(selected["tag_name"] + "\n", encoding="ascii")
PY

selected_tag=$(<"$selected_tag_file")
manifest_url="https://github.com/$THREE_MM_REPOSITORY/releases/download/$selected_tag/3mm-update-manifest.json"
wget --https-only --secure-protocol=TLSv1_2 --timeout=30 --tries=3 \
  -qO "$manifest" "$manifest_url" || fail "could not download the release manifest"

python3 - \
  "$manifest" "$THREE_MM_REPOSITORY" "$selected_tag" "$channel" "$architecture" \
  "$release_id_file" "$artifact_file_name" "$artifact_url_file" \
  "$artifact_sha_file" "$artifact_size_file" "$packages_file" <<'PY'
import json
import re
import sys
from pathlib import Path

(
    manifest_path,
    repository,
    selected_tag,
    channel,
    architecture,
    release_id_file,
    filename_file,
    url_file,
    sha_file,
    size_file,
    packages_file,
) = sys.argv[1:]
payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

if payload.get("schema_version") != 1:
    raise SystemExit("Release manifest schema is unsupported")
version = payload.get("version")
commit = payload.get("commit")
if (
    not isinstance(version, str)
    or selected_tag != f"v{version}"
    or payload.get("release_id") != selected_tag
    or payload.get("channel") != channel
    or not isinstance(commit, str)
    or re.fullmatch(r"[0-9a-f]{40}", commit) is None
):
    raise SystemExit("Release manifest identity is invalid")

artifacts = payload.get("artifacts")
matches = (
    [item for item in artifacts if isinstance(item, dict) and item.get("architecture") == architecture]
    if isinstance(artifacts, list)
    else []
)
if len(matches) != 1:
    raise SystemExit("Release has no unique artifact for this architecture")
artifact = matches[0]
filename = artifact.get("filename")
url = artifact.get("download_url")
sha256 = artifact.get("sha256")
size = artifact.get("size_bytes")
expected_url = f"https://github.com/{repository}/releases/download/{selected_tag}/{filename}"
if (
    not isinstance(filename, str)
    or re.fullmatch(r"3mm-[0-9A-Za-z._-]+\.tar\.gz", filename) is None
    or url != expected_url
    or not isinstance(sha256, str)
    or re.fullmatch(r"[0-9a-f]{64}", sha256) is None
    or not isinstance(size, int)
    or size <= 0
):
    raise SystemExit("Release artifact metadata is invalid")

dependencies = payload.get("dependencies")
packages = dependencies.get("apt_packages") if isinstance(dependencies, dict) else None
package_pattern = re.compile(r"[a-z0-9][a-z0-9+.:~-]*")
if (
    not isinstance(packages, list)
    or packages != sorted(packages)
    or len(packages) != len(set(packages))
    or len(packages) > 100
    or any(not isinstance(item, str) or package_pattern.fullmatch(item) is None for item in packages)
):
    raise SystemExit("Release dependency list is invalid")

outputs = {
    release_id_file: selected_tag,
    filename_file: filename,
    url_file: url,
    sha_file: sha256,
    size_file: str(size),
    packages_file: "\n".join(packages),
}
for destination, value in outputs.items():
    Path(destination).write_text(value + "\n", encoding="ascii")
PY

mapfile -t packages < "$packages_file"
printf 'Installing the clean-host and release prerequisites...\n'
export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C
apt-get update
apt-get install --yes --no-install-recommends --no-remove -- \
  "${THREE_MM_BOOTSTRAP_PACKAGES[@]}" "${packages[@]}"

artifact_name=$(<"$artifact_file_name")
artifact_url=$(<"$artifact_url_file")
artifact_sha256=$(<"$artifact_sha_file")
artifact_size=$(<"$artifact_size_file")
release_id=$(<"$release_id_file")
archive="$stage/$artifact_name"

printf 'Downloading and verifying %s...\n' "$release_id"
wget --https-only --secure-protocol=TLSv1_2 --timeout=60 --tries=3 \
  -qO "$archive" "$artifact_url" || fail "could not download the release archive"
actual_size=$(stat -c '%s' "$archive")
[[ $actual_size == "$artifact_size" ]] || fail "release archive size does not match"
printf '%s  %s\n' "$artifact_sha256" "$archive" | sha256sum --check --status || \
  fail "release archive checksum does not match"

installer="$stage/install-systemd.sh"
preflight="$stage/first_boot_preflight.py"
tar -xOf "$archive" deployment/install-systemd.sh > "$installer"
tar -xOf "$archive" deployment/first_boot_preflight.py > "$preflight"
chmod 0700 "$installer" "$preflight"

printf 'Running the read-only first-boot preflight...\n'
python3 "$preflight"

worker="$stage/run-install.sh"
cat > "$worker" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

stage=$1
installer=$2
archive=$3
release_id=$4
frontend_origin=$5
sha256=$6

cleanup() {
  result=$?
  rm -f -- "$stage"/* 2>/dev/null || true
  rmdir -- "$stage" 2>/dev/null || true
  exit "$result"
}
trap cleanup EXIT

/usr/bin/bash "$installer" "$archive" "$release_id" "$frontend_origin" "" "$sha256"
EOF
chmod 0700 "$worker"

unit_suffix=$(basename "$stage" | tr '.[:upper:]' '-[:lower:]')
unit="3mm-bootstrap-$unit_suffix"
printf 'Starting the immutable installation as %s.service...\n' "$unit"
systemd-run \
  --unit="$unit" \
  --collect \
  --no-block \
  --property=Type=exec \
  --property=RuntimeMaxSec=45min \
  --property=UMask=0022 \
  /usr/bin/bash "$worker" "$stage" "$installer" "$archive" \
  "$release_id" "$frontend_origin" "$artifact_sha256"
job_started=1

cat <<EOF

3mm installation is running in the background.
Release: $release_id
Log while LAN access remains: journalctl -fu $unit.service

This Wi-Fi SSH connection is expected to close when setup mode starts.
Then join the open network "3mm Setup XXXX" from a phone. The setup page should
open automatically; fallback: http://10.42.0.1:8895/setup
EOF
