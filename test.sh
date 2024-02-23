#!/bin/bash
# by https://github.com/oneclickvirt/pve_kvm_images
# 2024.02.23
# curl -L https://raw.githubusercontent.com/oneclickvirt/pve_kvm_images/main/test.sh -o test.sh && chmod +x test.sh && ./test.sh

rm -rf log
date=$(date)
system_names=()
echo "$date" >>log
echo "------------------------------------------" >>log
release_names=("ubuntu" "debian" "kali" "centos" "almalinux" "rockylinux" "fedora" "opensuse" "alpine" "archlinux" "gentoo" "openwrt" "oracle" "openeuler")
response=$($(curl -s -m 6 https://down.idc.wiki/Image/realServer-Template/current/qcow2/ | grep -o '<a href="[^"]*">' | awk -F'"' '{print $2}' | sed -n '/qcow2$/s#/Image/realServer-Template/current/qcow2/##p'))
if [ $? -eq 0 ] && [ -n "$response" ]; then
    system_names+=($(echo "$response"))
fi
for ((i = 0; i < ${#release_names[@]}; i++)); do
    release_name="${release_names[i]}"
    temp_images=()
    for sy in "${system_names[@]}"; do
        if [[ $sy == "${release_name}"* ]]; then
            curl -m 60 -LO "https://github.com/oneclickvirt/pve_kvm_images/releases/download/images/${sy}"
            if [ $? -ne 0 ]; then
                curl -m 60 -LO "https://cdn.spiritlhl.net/https://github.com/oneclickvirt/pve_kvm_images/releases/download/images/${sy}"
            fi
            temp_images+=("${sy}")
        fi
    done
    for image in "${temp_images[@]}"; do
        echo "$image"
        echo "$image" >>log
        qm create 102 --agent 1 --scsihw virtio-scsi-single --serial0 socket --cores $core --sockets 1 --cpu host --net0 virtio,bridge=vmbr1,firewall=0
        qm importdisk 102 /root/qcow/${image} local
        raw_name=$(ls /var/lib/vz/images/102/*.raw | xargs -n1 basename | tail -n 1)
        if [ -n "$raw_name" ]; then
            qm set 102 --scsihw virtio-scsi-pci --scsi0 local:102/${raw_name}
        else
            qm set 102 --scsihw virtio-scsi-pci --scsi0 local:102/vm-102-disk-0.raw
        fi
        qm set 102 --bootdisk scsi0
        qm set 102 --boot order=scsi0
        qm set 102 --memory 2048
        qm set 102 --ide2 local:cloudinit
        user_ip="172.16.1.111"
        res0=$(qm set 102 --ipconfig0 ip=${user_ip}/24,gw=172.16.1.1)
        if [[ $res0 == *"error"* || $res0 == *"failed: exit code"* ]]; then
            echo "set eth0 failed" >>log
        fi
        qm set 102 --nameserver 8.8.8.8
        qm set 102 --searchdomain local
        sleep 5
        qm resize 102 scsi0 10G
        qm start 102
        sleep 300
        res1=$(qm guest exec 102 -- ps aux|grep ssh)
        if [[ $res1 == *"ssh"* ]]; then
            echo "ssh config correct"
        fi
        echo "nameserver 8.8.8.8" | qm guest exec 102 -- tee -a /etc/resolv.conf
        res4=$(qm guest exec 102 curl https://raw.githubusercontent.com/spiritLHLS/ecs/main/back/test)
        if [[ $res4 == *"success"* ]]; then
            echo "network is public"
        else
            echo "no public network" >>log
        fi
        pct stop 102
        sleep 30
        if [ $? -eq 0 ]; then
            pct start 102
            sleep 15
            echo "nameserver 8.8.8.8" | qm guest exec 102 -- tee -a /etc/resolv.conf
            res5=$(qm guest exec 102 curl https://raw.githubusercontent.com/spiritLHLS/ecs/main/back/test)
            if [[ $res5 == *"success"* ]]; then
                echo "reboot success"
            else
                echo "reboot failed" >>log
            fi
        else
            echo "reboot failed" >>log
        fi
        pct stop 102
        pct destroy 102
        rm -rf $image
        echo "------------------------------------------" >>log
    done
done
