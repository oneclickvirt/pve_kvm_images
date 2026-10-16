#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
[[ $(id -u) == 0 && $(hostname) == pve-ci ]] || { echo 'Disposable PVE guest required' >&2; exit 1; }
address=$(ip -4 -o address show scope global | awk 'NR==1 {split($4,a,"/"); print a[1]}')
[[ -n "$address" ]]
sed -i '/[[:space:]]pve-ci\([[:space:].]\|$\)/d' /etc/hosts
printf '%s pve-ci.test pve-ci\n' "$address" >> /etc/hosts
printf 'manage_etc_hosts: false\n' >/etc/cloud/cloud.cfg.d/99-pve-ci-hosts.cfg
cat >/etc/apt/apt.conf.d/80-ci-bounds <<'EOF'
Acquire::Retries "3";
Acquire::http::Timeout "30";
Acquire::https::Timeout "30";
DPkg::Lock::Timeout "180";
EOF
curl -fLsS --connect-timeout 15 --max-time 120 --retry 3 \
  https://enterprise.proxmox.com/debian/proxmox-release-trixie.gpg \
  -o /usr/share/keyrings/proxmox-archive-keyring.gpg
# Packages remain authenticated by the official archive key. The upstream
# repository documents HTTP; no signature or certificate check is disabled.
cat >/etc/apt/sources.list.d/pve-ci.sources <<'EOF'
Types: deb
URIs: http://download.proxmox.com/debian/pve
Suites: trixie
Components: pve-no-subscription
Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg
EOF
echo 'postfix postfix/main_mailer_type select Local only' | debconf-set-selections
echo 'postfix postfix/mailname string pve-ci.test' | debconf-set-selections
apt-get update
apt-get install -y --no-install-recommends proxmox-ve postfix open-iscsi dnsmasq-base iptables curl python3
test -n "$(find /boot -maxdepth 1 -name 'vmlinuz-*-pve' -print -quit)"
update-grub
echo 'NATIVE_PVE_PROVISION packages-installed=true kernel-reboot-required=true'
