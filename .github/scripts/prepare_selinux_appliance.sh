#!/usr/bin/env bash
set -euo pipefail
[[ "${RUNNER_ENVIRONMENT:-}" == github-hosted ]] || { echo 'A disposable GitHub-hosted runner is required' >&2; exit 1; }
export LIBGUESTFS_BACKEND=direct
unset LIBGUESTFS_BACKEND_SETTINGS
# Ubuntu's appliance manifest omits policycoreutils. virt-customize then
# silently falls back to /.autorelabel, which an unlabeled system cannot run.
appliance_path="$(guestfish get-path)"
[[ "$appliance_path" == /* && "$appliance_path" != *:* ]] || { echo 'Unsupported guest appliance path' >&2; exit 1; }
packages="$appliance_path/supermin.d/packages"
[[ -f "$packages" ]] || { echo 'Guest appliance package manifest is missing' >&2; exit 1; }
if ! grep -qxF policycoreutils "$packages"; then
    printf '%s\n' policycoreutils | sudo tee -a "$packages" >/dev/null
fi
sudo find /boot -maxdepth 1 -type f -name 'vmlinuz-*' -exec chmod a+r {} +
probe_image="$(mktemp "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/selinux-probe.XXXXXX")"
trap 'rm -f "$probe_image"' EXIT
qemu-img create -f qcow2 "$probe_image" 16M >/dev/null
# Check the appliance's actual setfiles capability, not the host package list.
timeout --kill-after=30s 240s guestfish -a "$probe_image" run : available selinuxrelabel
echo 'Guest appliance offline SELinux relabel capability verified'
