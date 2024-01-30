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
