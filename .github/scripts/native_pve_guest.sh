#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) == 0 && $(hostname) == pve-ci && $(uname -r) == *-pve ]] || { echo 'Disposable host with a real PVE kernel required' >&2; exit 1; }
cd "$(dirname "$0")"
workdir=$PWD
check=$(cat guest-check.sh)
pveversion
systemctl is-active pve-cluster pvedaemon
if grep -qE '^dir:[[:space:]]+local$' /etc/pve/storage.cfg 2>/dev/null; then
  pvesm set local --content images,rootdir,vztmpl,iso,backup
else
  pvesm add dir local --path /var/lib/vz --content images,rootdir,vztmpl,iso,backup
fi
ip link add vmbr0 type bridge
ip address add 10.42.0.1/24 dev vmbr0
ip link set vmbr0 up
sysctl -w net.ipv4.ip_forward=1
uplink=$(ip -o route show default | awk 'NR==1 {for(i=1;i<=NF;i++) if($i=="dev") {print $(i+1); exit}}')
[[ -n "$uplink" ]]
iptables -t nat -A POSTROUTING -s 10.42.0.0/24 -o "$uplink" -j MASQUERADE
iptables -I FORWARD -i vmbr0 -j ACCEPT
iptables -I FORWARD -o vmbr0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
dnsmasq --interface=vmbr0 --bind-interfaces --except-interface=lo --port=0 \
  --dhcp-range=10.42.0.100,10.42.0.150,255.255.255.0,1h \
  --dhcp-option=3,10.42.0.1 --dhcp-option=6,1.1.1.1 --pid-file="$workdir/dnsmasq.pid"
cleanup() {
  qm stop 201 --skiplock 1 >/dev/null 2>&1 || true
  qm destroy 201 --purge 1 >/dev/null 2>&1 || true
  for id in 101 102 103 104; do
    pct stop "$id" --skiplock 1 >/dev/null 2>&1 || true
    pct destroy "$id" --purge 1 >/dev/null 2>&1 || true
  done
  if [[ -f "$workdir/dnsmasq.pid" ]]; then kill "$(cat "$workdir/dnsmasq.pid")" 2>/dev/null || true; fi
}
trap cleanup EXIT
record() {
  python3 - "$1" "$2" <<'PY'
import json,sys
print('NATIVE_PVE_IMAGE_RESULT '+json.dumps({'kind':sys.argv[1], 'image':sys.argv[2], 'success':True}),flush=True)
PY
}
wait_ct() {
  local id=$1 previous=${2:-} boot deadline=$((SECONDS+360))
  while (( SECONDS < deadline )); do
    if boot=$(timeout 60 pct exec "$id" -- /bin/sh -c "$check" 2>last-ct-error.log); then
      if [[ "$boot" =~ ^[0-9a-f-]{36}$ && "$boot" != "$previous" ]]; then printf '%s\n' "$boot"; return 0; fi
    fi
    sleep 5
  done
  cat last-ct-error.log >&2
  pct config "$id" >&2 || true
  pct exec "$id" -- journalctl -b -n 80 --no-pager >&2 || true
  return 1
}
id=100
while IFS= read -r image; do
  id=$((id+1))
  [[ "$image" =~ ^[A-Za-z0-9_.-]+\.tar\.zst$ && "$id" -le 104 ]]
  echo "Native pct test: $image"
  pct create "$id" "$workdir/$image" --rootfs local:4 --memory 512 --swap 256 --cores 1 \
    --hostname "image-$id" --unprivileged 1 --net0 "name=eth0,bridge=vmbr0,ip=10.42.0.$id/24,gw=10.42.0.1" --nameserver 1.1.1.1
  pct start "$id"
  boot=$(wait_ct "$id")
  pct reboot "$id" --timeout 90
  wait_ct "$id" "$boot" >/dev/null
  record container "$image"
  pct stop "$id"
  pct destroy "$id" --purge 1
done < <(python3 -c 'import json; print("\n".join(x["name"] for x in json.load(open("manifest.json")) if x["kind"]=="container"))')
image=$(python3 -c 'import json; print(next(x["name"] for x in json.load(open("manifest.json")) if x["kind"]=="vm"))')
[[ "$image" =~ ^[A-Za-z0-9_.-]+\.qcow2$ ]]
echo "Native qm test with KVM disabled: $image"
qm create 201 --name image-vm --memory 2048 --cores 2 --kvm 0 --cpu x86-64-v2-AES \
  --machine q35 --bios ovmf --efidisk0 local:1,efitype=4m,pre-enrolled-keys=0 \
  --scsihw virtio-scsi-pci --agent enabled=1 --net0 virtio,bridge=vmbr0 --serial0 socket --vga serial0
qm importdisk 201 "$workdir/$image" local --format qcow2
volume=$(qm config 201 | awk -F': ' '$1=="unused0" {print $2}')
[[ "$volume" == local:* ]]
qm set 201 --scsi0 "$volume" --boot order=scsi0
qm config 201 | grep -Fx 'kvm: 0'
qm start 201
wait_vm() {
  local previous=${1:-} boot deadline=$((SECONDS+900))
  while (( SECONDS < deadline )); do
    if timeout 60 qm guest exec 201 --timeout 40 -- /bin/sh -c "$check" >vm-exec.json 2>last-vm-error.log; then
      if boot=$(python3 - <<'PY'
import json,re,sys
result=json.load(open('vm-exec.json'))
boot=result.get('out-data','').strip()
if not result.get('exited') or result.get('exitcode')!=0 or not re.fullmatch('[0-9a-f-]{36}',boot): sys.exit(1)
print(boot)
PY
      ); then
        if [[ "$boot" != "$previous" ]]; then printf '%s\n' "$boot"; return 0; fi
      fi
    fi
    sleep 5
  done
  cat last-vm-error.log >&2
  qm config 201 >&2 || true
  tail -n 80 /var/log/pve/qemu-server/201.log >&2 || true
  return 1
}
boot=$(wait_vm)
qm reboot 201 --timeout 120
wait_vm "$boot" >/dev/null
record vm "$image"
echo 'NATIVE_PVE_HOST_RESULT success=true inner_vm_acceleration=tcg'
