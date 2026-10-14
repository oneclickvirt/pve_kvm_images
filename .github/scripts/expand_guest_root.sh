#!/usr/bin/env bash
set -euo pipefail

image=${1:?qcow2 image required}
[[ -s "$image" ]]

root_part=$(virt-filesystems -a "$image" --filesystems --long |
    awk '$1 ~ /^\/dev\/(sd[a-z][0-9]+|vd[a-z][0-9]+|nvme[0-9]+n[0-9]+p[0-9]+)$/ && $3 == "ext4" {print $1}' |
    tail -n 1)
[[ -n "$root_part" ]] || { echo 'No ext4 guest root partition was detected' >&2; exit 1; }

source_size=$(qemu-img info --output=json "$image" | jq -er '."virtual-size"')
[[ "$source_size" =~ ^[0-9]+$ ]]
target_size=$((source_size + 4 * 1024 * 1024 * 1024))
minimum_size=$((8 * 1024 * 1024 * 1024))
(( target_size < minimum_size )) && target_size=$minimum_size

expanded=${image%.qcow2}-expanded.qcow2
rm -f "$expanded"
trap 'rm -f "$expanded"' EXIT
qemu-img create -f qcow2 "$expanded" "$target_size" >/dev/null
virt-resize --expand "$root_part" "$image" "$expanded"
qemu-img check "$expanded"
mv "$expanded" "$image"
trap - EXIT
echo "Expanded $root_part to an $target_size-byte qcow2 guest disk"
