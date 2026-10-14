#!/usr/bin/env bash
set -euo pipefail
[[ "${RUNNER_ENVIRONMENT:-}" == github-hosted ]] || { echo 'A disposable GitHub-hosted runner is required' >&2; exit 1; }
runtime=${1:-incus}
source .github/scripts/ci_network.sh
ci_retry sudo apt-get update -y
ci_retry sudo apt-get install -y --no-install-recommends curl jq unzip xz-utils squashfs-tools qemu-utils qemu-system-x86 qemu-system-arm ovmf qemu-efi-aarch64 cloud-image-utils openssh-client sshpass
if [[ -c /dev/kvm ]]; then sudo chmod a+rw /dev/kvm; fi
if [[ "$runtime" == qemu ]]; then exit 0; fi
if [[ "${RUNNER_ARCH:-}" == ARM64 ]]; then ci_retry sudo apt-get install -y --no-install-recommends libguestfs-tools; fi
if [[ "$runtime" == lxd ]]; then
    ci_retry sudo snap install lxd --channel=5.21/stable
    sudo /snap/bin/lxd waitready --timeout=120
    cli=/snap/bin/lxc
else
    ci_retry sudo apt-get install -y --no-install-recommends incus incus-agent dnsmasq-base qemu-system-modules-spice swtpm
    sudo systemctl start incus
    sudo incus admin waitready --timeout=120
    cli=incus
fi
if [[ "$runtime" == lxd ]]; then sudo /snap/bin/lxd init --preseed <<'PRESEED'
config: {}
networks:
- name: imagebr0
  type: bridge
  config:
    ipv4.address: auto
    ipv4.dhcp: "true"
    ipv4.nat: "true"
    ipv6.address: none
storage_pools:
- name: default
  driver: dir
profiles:
- name: default
  devices:
    root: {type: disk, path: /, pool: default}
    eth0: {type: nic, network: imagebr0, name: eth0}
PRESEED
else sudo "$cli" admin init --preseed <<'PRESEED'
config: {}
networks:
- name: imagebr0
  type: bridge
  config:
    ipv4.address: auto
    ipv4.dhcp: "true"
    ipv4.nat: "true"
    ipv6.address: none
storage_pools:
- name: default
  driver: dir
profiles:
- name: default
  devices:
    root: {type: disk, path: /, pool: default}
    eth0: {type: nic, network: imagebr0, name: eth0}
PRESEED
fi
sudo iptables -I FORWARD -i imagebr0 -j ACCEPT
sudo iptables -I FORWARD -o imagebr0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
if [[ -c /dev/kvm ]]; then sudo chmod a+rw /dev/kvm; fi
sudo "$cli" version
