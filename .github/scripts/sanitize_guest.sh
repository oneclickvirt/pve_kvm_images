#!/usr/bin/env bash
set -euo pipefail
image=${1:?image path required}
[[ -s "$image" ]] || { echo 'Missing image to sanitize' >&2; exit 1; }
# This must run AFTER the final virt-customize operation: package scripts
# and systemd-machine-id-setup can regenerate identities inside the appliance.
# Duplicate IDs give cloned guests the same DHCPv6 DUID and collide on IPv6.
timeout --kill-after=30s 15m virt-sysprep -a "$image" \
    --operations machine-id,dhcp-client-state,ssh-hostkeys,udev-persistent-net
echo 'Guest clone identity and lease state sanitized'
