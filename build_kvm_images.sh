#!/bin/bash
#from https://github.com/oneclickvirt/pve_kvm_images


links=($(curl -s -m 6 https://down.idc.wiki/Image/realServer-Template/current/qcow2/ | grep -o '<a href="[^"]*">' | awk -F'"' '{print $2}' | sed -n '/qcow2$/s#/Image/realServer-Template/current/qcow2/##p'))
if [ ${#links[@]} -gt 0 ]; then
    for link in "${links[@]}"; do
        echo "$link"
    done
else
    echo "没有找到KVM镜像"
fi
sudo apt-get install -y libguestfs-tools rng-tools curl
sudo apt-get install -y libguestfs-tools rng-tools curl --fix-missing
curl -o rebuild_qcow2.sh https://raw.githubusercontent.com/spiritLHLS/pve/main/back/rebuild_qcow2.sh
chmod 777 rebuild_qcow2.sh
for image in "${links[@]}"; do
  curl -o $image "https://down.idc.wiki/Image/realServer-Template/current/qcow2/$image"
  chmod 777 $image
done
for image in "${links[@]}"; do
  ./rebuild_qcow2.sh $image
done
