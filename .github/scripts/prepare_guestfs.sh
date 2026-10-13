#!/usr/bin/env bash
set -euo pipefail
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends curl wget unzip zip jq libguestfs-tools qemu-utils axel rng-tools linux-image-generic
if [[ -c /dev/kvm ]]; then sudo chmod a+rw /dev/kvm; fi
sudo find /boot -maxdepth 1 -type f -name 'vmlinuz-*' -exec chmod a+r {} +

# libguestfs 1.52 chooses passt when `passt --help` exits 0 or 1; it has
# no passt=no setting. The hosted runner cannot launch passt's namespace.
# Disable that optional executable so the built-in QEMU SLIRP backend is used.
if passt_path="$(command -v passt)"; then
    sudo chmod a-x "$passt_path"
fi
export LIBGUESTFS_BACKEND=direct
unset LIBGUESTFS_BACKEND_SETTINGS

# A launch without networking misses passt failures. Check real DNS and TCP
# inside the network-enabled appliance before downloading large cloud images.
probe_image="$(mktemp --suffix=.qcow2)"
probe_script="$(mktemp)"
trap 'rm -f "$probe_image" "$probe_script"' EXIT
qemu-img create -f qcow2 "$probe_image" 64M
cat > "$probe_script" <<'PROBE'
set -euo pipefail
exec 3<>/dev/tcp/archive.ubuntu.com/80
printf 'HEAD /ubuntu/ HTTP/1.0\r\nHost: archive.ubuntu.com\r\n\r\n' >&3
IFS= read -r status <&3
[[ "$status" == HTTP/* ]]
printf '%s\n' "$status"
PROBE
# debug sh splits and rejoins arguments, losing nested shell quoting. Upload
# the script into appliance /tmp so only a plain command is passed through.
probe_output="$(timeout --kill-after=30s 240s guestfish --network -a "$probe_image" run : debug-upload "$probe_script" /tmp/network-probe.sh 0600 : debug sh 'timeout 30 bash /tmp/network-probe.sh')"
printf '%s\n' "$probe_output"
if ! grep -qE '^HTTP/[0-9.]+ [1-5][0-9][0-9]' <<< "$probe_output"; then
    echo 'The guest appliance could not resolve and connect to the package mirror' >&2
    exit 1
fi
