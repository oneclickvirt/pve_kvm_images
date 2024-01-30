#!/bin/bash
#from https://github.com/oneclickvirt/pve_kvm_images

if ! command -v virt-customize &> /dev/null
then
    echo "virt-customize not found, installing libguestfs-tools"
    sudo apt-get update
    sudo apt-get install -y libguestfs-tools
    sudo apt-get install -y libguestfs-tools --fix-missing
fi
if ! command -v rngd &> /dev/null
then
    echo "rng-tools not found, installing rng-tools"
    sudo apt-get update
    sudo apt-get install -y rng-tools
    sudo apt-get install -y rng-tools --fix-missing
fi
qcow_file=$1
echo "转换文件$qcow_file中......"
if [[ "$qcow_file" == *"debian"* || "$qcow_file" == *"ubuntu"* || "$qcow_file" == *"arch"* ]]; then
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/ssh_pwauth:[[:space:]]*0/ssh_pwauth: 1/g' /etc/cloud/cloud.cfg"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo '' > /etc/motd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo 'Modified from https://github.com/oneclickvirt/pve_kvm_images' >> /etc/motd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo 'Related repo https://github.com/spiritLHLS/pve' >> /etc/motd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo '--by https://t.me/spiritlhl' >> /etc/motd"
    echo "启用SSH功能..."
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl enable ssh"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl start ssh"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl enable sshd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl start sshd"
    echo "启用root登录..."
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#PasswordAuthentication no/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#Port 22/Port 22/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#AddressFamily any/AddressFamily any/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#ListenAddress 0.0.0.0/ListenAddress 0.0.0.0/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#ListenAddress ::/ListenAddress ::/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "service ssh restart"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "service sshd restart"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl restart sshd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl restart ssh"
    if [[ "$qcow_file" == *"debian"* || "$qcow_file" == *"ubuntu"* ]]; then
        sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "apt-get install sudo -y"
        echo "安装qemu-guest-agent..."
        sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "apt-get update -y && apt-get install qemu-guest-agent -y"
        sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl start qemu-guest-agent"
    fi
elif [[ "$qcow_file" == *"alpine"* ]]; then
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "apk update"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "apk add --no-cache wget curl openssh-server sshpass"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "apk add --no-cache sudo"
    echo "启用SSH功能..."
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "cd /etc/ssh"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "ssh-keygen -A"
    echo "启用root登录..."
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --edit '/etc/cloud/cloud.cfg:s/preserve_hostname: *false/preserve_hostname: true/'
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --edit '/etc/cloud/cloud.cfg:s/disable_root: *true/disable_root: false/'
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --edit '/etc/ssh/sshd_config:s/PasswordAuthentication no/PasswordAuthentication yes/'
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --edit '/etc/ssh/sshd_config:s/^#?\(Port\).*/\1 22/'
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --edit '/etc/ssh/sshd_config:s/^#PermitRootLogin\|PermitRootLogin/c PermitRootLogin yes/'
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --edit '/etc/ssh/sshd_config:s/^#AddressFamily\|AddressFamily/c AddressFamily any/'
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --edit '/etc/ssh/sshd_config:s/^#ListenAddress\|ListenAddress/c ListenAddress 0.0.0.0/'
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "/usr/sbin/sshd"
elif [[ "$qcow_file" == *"almalinux9"* || "$qcow_file" == *"rockylinux"* ]]; then
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/ssh_pwauth:[[:space:]]*0/ssh_pwauth: 1/g' /etc/cloud/cloud.cfg"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo '' > /etc/motd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo 'Modified from https://github.com/oneclickvirt/pve_kvm_images' >> /etc/motd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo 'Related repo https://github.com/spiritLHLS/pve' >> /etc/motd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo '--by https://t.me/spiritlhl' >> /etc/motd"
    echo "启用SSH功能..."
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl enable ssh"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl start ssh"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl enable sshd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl start sshd"
    echo "启用root登录..."
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/ssh_pwauth:[[:space:]]*0/ssh_pwauth: 1/g' /etc/cloud/cloud.cfg"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#PasswordAuthentication no/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/^ChallengeResponseAuthentication no/ChallengeResponseAuthentication yes/g' /etc/ssh/sshd_config.d/50-redhat.conf"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#Port 22/Port 22/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#AddressFamily any/AddressFamily any/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#ListenAddress 0.0.0.0/ListenAddress 0.0.0.0/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#ListenAddress ::/ListenAddress ::/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "service ssh restart"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "service sshd restart"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl restart sshd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl restart ssh"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "yum install sudo -y"
    echo "安装qemu-guest-agent..."
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "yum update -y && yum install qemu-guest-agent -y"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl start qemu-guest-agent"
elif [[ "$qcow_file" == *"almalinux8"* || "$qcow_file" == *"centos9-stream"* || "$qcow_file" == *"centos8-stream"* || "$qcow_file" == *"centos7"* ]]; then
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/ssh_pwauth:[[:space:]]*0/ssh_pwauth: 1/g' /etc/cloud/cloud.cfg"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo '' > /etc/motd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo 'Modified from https://github.com/oneclickvirt/pve_kvm_images' >> /etc/motd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo 'Related repo https://github.com/spiritLHLS/pve' >> /etc/motd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo '--by https://t.me/spiritlhl' >> /etc/motd"
    echo "启用SSH功能..."
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl enable ssh"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl start ssh"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl enable sshd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl start sshd"
    echo "启用root登录..."
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#PasswordAuthentication no/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/^ChallengeResponseAuthentication no/ChallengeResponseAuthentication yes/g' /etc/ssh/sshd_config.d/50-redhat.conf"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#Port 22/Port 22/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#AddressFamily any/AddressFamily any/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#ListenAddress 0.0.0.0/ListenAddress 0.0.0.0/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#ListenAddress ::/ListenAddress ::/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "service ssh restart"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "service sshd restart"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl restart sshd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl restart ssh"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "yum install sudo -y"
    echo "安装qemu-guest-agent..."
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "yum update -y && yum install qemu-guest-agent -y"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl start qemu-guest-agent"
else
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/disable_root:[[:space:]]*1/disable_root: 0/g' /etc/cloud/cloud.cfg"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/ssh_pwauth:[[:space:]]*0/ssh_pwauth: 1/g' /etc/cloud/cloud.cfg"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo '' > /etc/motd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo 'Modified from https://github.com/oneclickvirt/pve_kvm_images' >> /etc/motd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo 'Related repo https://github.com/spiritLHLS/pve' >> /etc/motd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo '--by https://t.me/spiritlhl' >> /etc/motd"
    echo "启用SSH功能..."
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl enable ssh"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl start ssh"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl enable sshd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl start sshd"
    echo "启用root登录..."
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#PasswordAuthentication no/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#Port 22/Port 22/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#AddressFamily any/AddressFamily any/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#ListenAddress 0.0.0.0/ListenAddress 0.0.0.0/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "sed -i 's/#ListenAddress ::/ListenAddress ::/g' /etc/ssh/sshd_config"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "service ssh restart"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "service sshd restart"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl restart sshd"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl restart ssh"
    echo "安装qemu-guest-agent..."
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "dnf update -y && dnf install qemu-guest-agent -y"
    sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "systemctl start qemu-guest-agent"
fi
sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo root:oneclickvirt | chpasswd root"
sudo SUPERMIN_KERNEL=./boot/vmlinuz-image-$(uname -r) virt-customize -a $qcow_file --run-command "echo root:oneclickvirt | sudo chpasswd root"
echo "创建备份..."
cp $qcow_file ${qcow_file}.bak
echo "复制新文件..."
cp $qcow_file ${qcow_file}.tmp
echo "覆盖原文件..."
mv ${qcow_file}.tmp $qcow_file
rm -rf *.bak
echo "$qcow_file修改完成"
