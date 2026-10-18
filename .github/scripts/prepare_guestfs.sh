#!/usr/bin/env bash
set -euo pipefail
source .github/scripts/ci_network.sh
ci_retry sudo apt-get update -y
ci_retry sudo apt-get install -y --no-install-recommends curl wget unzip zip jq libguestfs-tools qemu-utils axel rng-tools linux-image-generic isc-dhcp-client dhcpcd-base policycoreutils
bash .github/scripts/prepare_selinux_appliance.sh
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
# guestfish debug sh always invokes the appliance's POSIX /bin/sh.  Keep this
# probe POSIX instead of using bash-only /dev/tcp redirections, which made the
# hosted image builds fail before any image work started on appliances without
# bash.
set -eu
ip -brief address
ip route
cat /etc/resolv.conf
if command -v getent >/dev/null 2>&1; then
    getent hosts archive.ubuntu.com >/dev/null
fi
if command -v wget >/dev/null 2>&1; then
    wget -q -O /dev/null --timeout=20 http://archive.ubuntu.com/ubuntu/ || exit 1
elif command -v curl >/dev/null 2>&1; then
    curl -fsS -o /dev/null --connect-timeout 20 --max-time 30 http://archive.ubuntu.com/ubuntu/ || exit 1
fi
echo 'network probe passed'
PROBE
# debug sh splits and rejoins arguments, losing nested shell quoting. Upload
# the script into appliance /tmp so only a plain command is passed through.
probe_output="$(timeout --kill-after=30s 240s guestfish --network -a "$probe_image" run : debug-upload "$probe_script" /tmp/network-probe.sh 0600 : debug sh 'timeout 30 bash /tmp/network-probe.sh')"
printf '%s\n' "$probe_output"
if ! grep -qE '^HTTP/[0-9.]+ [1-5][0-9][0-9]' <<< "$probe_output"; then
    echo 'The guest appliance could not resolve and connect to the package mirror' >&2
    exit 1
fi
