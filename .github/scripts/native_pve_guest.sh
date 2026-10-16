#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) == 0 && $(hostname) == pve-ci && $(uname -r) == *-pve ]] || { echo 'Disposable host with a real PVE kernel required' >&2; exit 1; }
cd "$(dirname "$0")"
workdir=$PWD
check=$(cat guest-check.sh)
: > native-results.jsonl
serial_pid=''
case "${NATIVE_PVE_OUTER_ACCELERATION:?PVE host acceleration must be explicit}" in
  kvm) vm_boot_budget=900; service_budget=120 ;;
  tcg) vm_boot_budget=2700; service_budget=300 ;;
  *) echo 'Unsupported PVE host acceleration' >&2; exit 1 ;;
esac
echo "NATIVE_PVE_NATIVE_BUDGET vm_boot_seconds=$vm_boot_budget"
pveversion
service_deadline=$((SECONDS+service_budget))
until systemctl is-active --quiet pve-cluster && systemctl is-active --quiet pvedaemon; do
  if (( SECONDS >= service_deadline )); then
    systemctl status pve-cluster pvedaemon --no-pager >&2 || true
    exit 1
  fi
  sleep 5
done
systemctl is-active pve-cluster pvedaemon
storages=$(pvesh get /storage --output-format json)
if python3 -c 'import json,sys; sys.exit(0 if any(x["storage"]=="local" for x in json.load(sys.stdin)) else 1)' <<<"$storages"; then
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
  if [[ -n "$serial_pid" ]]; then kill "$serial_pid" 2>/dev/null || true; fi
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
  python3 - "$1" "$2" <<'PY' | tee -a native-results.jsonl
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
# Under nested software emulation SCSI coldplug can finish only after
# initramfs has already abandoned the root device. Use the supported
# VirtIO block controller for that path; retain SCSI coverage on KVM hosts.
disk_slot=scsi0
if [[ "$NATIVE_PVE_OUTER_ACCELERATION" == tcg ]]; then disk_slot=virtio0; fi
echo "NATIVE_PVE_VM_STORAGE $disk_slot"
echo "Native qm test with KVM disabled: $image"
qm create 201 --name image-vm --ostype l26 --memory 2048 --cores 2 --kvm 0 --cpu x86-64-v2-AES \
  --machine q35 --bios ovmf --efidisk0 local:1,efitype=4m,pre-enrolled-keys=0 \
  --scsihw virtio-scsi-pci --agent enabled=1 --net0 virtio,bridge=vmbr0 --serial0 socket --vga serial0
qm importdisk 201 "$workdir/$image" local --format qcow2
volume=$(qm config 201 | awk -F': ' '$1=="unused0" {print $2}')
[[ "$volume" == local:* ]]
# These are cloud images: supply the same PVE-generated NoCloud network data
# a consumer must configure, without modifying the published filesystem.
qm set 201 --"$disk_slot" "$volume" --boot "order=$disk_slot" --ide2 local:cloudinit \
  --ipconfig0 ip=dhcp --nameserver 1.1.1.1
qm config 201 | grep -Fx 'kvm: 0'
python3 -u - <<'PY' >native-vm-serial.log 2>&1 &
import socket,sys,time
deadline=time.monotonic()+120
stream=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
while True:
    try:
        stream.connect('/run/qemu-server/201.serial0')
        break
    except (FileNotFoundError,ConnectionRefusedError):
        if time.monotonic()>deadline: raise
        time.sleep(1)
while True:
    data=stream.recv(65536)
    if not data: break
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
PY
serial_pid=$!
qm start 201
wait_vm() {
  local previous=${1:-} boot deadline=$((SECONDS+vm_boot_budget)) progress=$SECONDS
  while (( SECONDS < deadline )); do
    if grep -Eq 'Gave up waiting for root file system device|ALERT!.*does not exist.*Dropping to a shell' native-vm-serial.log; then
      echo 'Native qm boot entered initramfs emergency state; retaining failure diagnostics' >&2
      break
    fi
    if timeout 150 qm guest exec 201 --timeout 120 -- /bin/sh -c "$check" >vm-exec.json 2>last-vm-error.log; then
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
    if (( SECONDS >= progress )); then
      echo "Native qm readiness pending; remaining budget $((deadline-SECONDS))s" >&2
      cat last-vm-error.log >&2
      if [[ -s vm-exec.json ]]; then cat vm-exec.json >&2; fi
      progress=$((SECONDS+60))
    fi
    sleep 5
  done
  cat last-vm-error.log >&2
  if [[ -s vm-exec.json ]]; then cat vm-exec.json >&2; fi
  qm config 201 >&2 || true
  tail -c 20000 native-vm-serial.log >&2 || true
  timeout 60 qm guest exec 201 --timeout 40 -- /bin/sh -c \
    'ip address; ip route; cat /etc/resolv.conf; systemctl --failed --no-pager; journalctl -b -n 80 --no-pager' >&2 || true
  return 1
}
boot=$(wait_vm)
qm reboot 201 --timeout 120
wait_vm "$boot" >/dev/null
record vm "$image"
echo 'NATIVE_PVE_HOST_RESULT success=true inner_vm_acceleration=tcg'
