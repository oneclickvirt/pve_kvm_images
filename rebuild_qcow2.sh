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
# sudo apt-get install -y passt
export LIBGUESTFS_BACKEND=direct
export LIBGUESTFS_BACKEND_SETTINGS="passt:no"
ls -l /dev/kvm
ls -l /var/lib/libvirt/
qcow_file=$1
echo "----------------------------------------------------------"
echo "转换文件$qcow_file中......"

# 通用的cloud-init和SSH配置修复
echo "修复cloud-init配置..."
sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/ssh_pwauth:[[:space:]]*false/ssh_pwauth: true/g' /etc/cloud/cloud.cfg"
sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/ssh_pwauth:[[:space:]]*0/ssh_pwauth: 1/g' /etc/cloud/cloud.cfg"
sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/disable_root:[[:space:]]*true/disable_root: false/g' /etc/cloud/cloud.cfg"
sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/disable_root:[[:space:]]*1/disable_root: 0/g' /etc/cloud/cloud.cfg"

if [[ "$qcow_file" == *"debian"* || "$qcow_file" == *"ubuntu"* || "$qcow_file" == *"arch"* ]]; then
    echo "处理Debian/Ubuntu/Arch系统..."
    echo "启用SSH功能..."
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl enable ssh"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl start ssh"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl enable sshd"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl start sshd"
    
    echo "修改SSH配置目录中的文件..."
    sudo virt-customize -v -x -a $qcow_file --run-command "find /etc/ssh/sshd_config.d/ -name '*.conf' -exec sed -i 's/#*PermitRootLogin.*/PermitRootLogin yes/g' {} \;"
    sudo virt-customize -v -x -a $qcow_file --run-command "find /etc/ssh/sshd_config.d/ -name '*.conf' -exec sed -i 's/#*PasswordAuthentication.*/PasswordAuthentication yes/g' {} \;"
    sudo virt-customize -v -x -a $qcow_file --run-command "find /etc/ssh/sshd_config.d/ -name '*.conf' -exec sed -i 's/ChallengeResponseAuthentication no/ChallengeResponseAuthentication yes/g' {} \;"
    
    echo "启用root登录..."
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*PermitRootLogin.*/PermitRootLogin yes/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*PasswordAuthentication.*/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*Port.*/Port 22/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*AddressFamily.*/AddressFamily any/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*ListenAddress 0.0.0.0.*/ListenAddress 0.0.0.0/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*ListenAddress ::.*/ListenAddress ::/g' /etc/ssh/sshd_config"
    
    # 确保SSH配置生效
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl restart sshd"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl restart ssh"
    
    if [[ "$qcow_file" == *"debian"* || "$qcow_file" == *"ubuntu"* ]]; then
        sudo virt-customize -v -x -a $qcow_file --run-command "apt-get update -y"
        sudo virt-customize -v -x -a $qcow_file --run-command "apt-get install sudo -y"
        sudo virt-customize -v -x -a $qcow_file --run-command "apt-get install cron -y"
        sudo virt-customize -v -x -a $qcow_file --run-command "apt-get install curl -y"
        sudo virt-customize -v -x -a $qcow_file --run-command "apt-get install wget -y"
        sudo virt-customize -v -x -a $qcow_file --run-command "apt-get install lsof -y"
        echo "安装qemu-guest-agent..."
        sudo virt-customize -v -x -a $qcow_file --run-command "apt-get install qemu-guest-agent -y"
        sudo virt-customize -v -x -a $qcow_file --run-command "systemctl start qemu-guest-agent"
        sudo virt-customize -v -x -a $qcow_file --run-command "systemctl enable qemu-guest-agent"
    elif [[ "$qcow_file" == *"arch"* ]]; then
        sudo virt-customize -v -x -a $qcow_file --run-command "pacman -Sy --noconfirm --needed sudo"
        sudo virt-customize -v -x -a $qcow_file --run-command "pacman -Sy --noconfirm --needed cronie"
        sudo virt-customize -v -x -a $qcow_file --run-command "pacman -Sy --noconfirm --needed curl"
        sudo virt-customize -v -x -a $qcow_file --run-command "pacman -Sy --noconfirm --needed wget"
        sudo virt-customize -v -x -a $qcow_file --run-command "pacman -Sy --noconfirm --needed lsof"
        echo "安装qemu-guest-agent..."
        sudo virt-customize -v -x -a $qcow_file --run-command "pacman -Sy --noconfirm --needed qemu-guest-agent"
        sudo virt-customize -v -x -a $qcow_file --run-command "systemctl start qemu-guest-agent"
        sudo virt-customize -v -x -a $qcow_file --run-command "systemctl enable qemu-guest-agent"
    fi
elif [[ "$qcow_file" == *"alpine"* ]]; then
    echo "处理Alpine系统..."
    echo "安装依赖..."
    sudo virt-customize -v -x -a $qcow_file --run-command "apk update"
    sudo virt-customize -v -x -a $qcow_file --run-command "apk add --no-cache openssh-server"
    sudo virt-customize -v -x -a $qcow_file --run-command "apk add --no-cache sshpass"
    sudo virt-customize -v -x -a $qcow_file --run-command "apk add --no-cache curl"
    sudo virt-customize -v -x -a $qcow_file --run-command "apk add --no-cache wget"
    sudo virt-customize -v -x -a $qcow_file --run-command "apk add --no-cache sudo"
    sudo virt-customize -v -x -a $qcow_file --run-command "apk add --no-cache lsof"
    sudo virt-customize -v -x -a $qcow_file --run-command "apk add --no-cache qemu-guest-agent"
    sudo virt-customize -v -x -a $qcow_file --run-command "rc-update add qemu-guest-agent default"
    sudo virt-customize -v -x -a $qcow_file --run-command "rc-service qemu-guest-agent start"
    echo "启用SSH功能..."
    sudo virt-customize -v -x -a $qcow_file --run-command "rc-update add sshd"
    sudo virt-customize -v -x -a $qcow_file --run-command "ssh-keygen -A"
    echo "启用root登录..."
    sudo virt-customize -v -x -a $qcow_file --edit '/etc/cloud/cloud.cfg:s/preserve_hostname: *false/preserve_hostname: true/'
    sudo virt-customize -v -x -a $qcow_file --edit '/etc/cloud/cloud.cfg:s/disable_root: *true/disable_root: false/'
    sudo virt-customize -v -x -a $qcow_file --edit '/etc/ssh/sshd_config:s/.*PasswordAuthentication.*/PasswordAuthentication yes/'
    sudo virt-customize -v -x -a $qcow_file --edit '/etc/ssh/sshd_config:s/^#*Port.*/Port 22/'
    sudo virt-customize -v -x -a $qcow_file --edit '/etc/ssh/sshd_config:s/^#*PermitRootLogin.*/PermitRootLogin yes/'
    sudo virt-customize -v -x -a $qcow_file --edit '/etc/ssh/sshd_config:s/^#*AddressFamily.*/AddressFamily any/'
    sudo virt-customize -v -x -a $qcow_file --edit '/etc/ssh/sshd_config:s/^#*ListenAddress 0.0.0.0.*/ListenAddress 0.0.0.0/'
    sudo virt-customize -v -x -a $qcow_file --run-command "rc-service sshd restart"
elif [[ "$qcow_file" == *"almalinux9"* || "$qcow_file" == *"rockylinux"* ]]; then
    echo "处理AlmaLinux 9/Rocky Linux系统..."
    sudo virt-customize -v -x -a $qcow_file --run-command "yum update -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "yum install sudo -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "yum install cronie -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "yum install curl -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "yum install wget -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "yum install lsof -y"
    echo "启用SSH功能..."
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl enable ssh"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl start ssh"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl enable sshd"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl start sshd"
    
    echo "修改SSH配置目录中的文件..."
    sudo virt-customize -v -x -a $qcow_file --run-command "find /etc/ssh/sshd_config.d/ -name '*.conf' -exec sed -i 's/#*PermitRootLogin.*/PermitRootLogin yes/g' {} \;"
    sudo virt-customize -v -x -a $qcow_file --run-command "find /etc/ssh/sshd_config.d/ -name '*.conf' -exec sed -i 's/#*PasswordAuthentication.*/PasswordAuthentication yes/g' {} \;"
    sudo virt-customize -v -x -a $qcow_file --run-command "find /etc/ssh/sshd_config.d/ -name '*.conf' -exec sed -i 's/ChallengeResponseAuthentication no/ChallengeResponseAuthentication yes/g' {} \;"
    
    echo "启用root登录..."
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*PermitRootLogin.*/PermitRootLogin yes/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*PasswordAuthentication.*/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*Port.*/Port 22/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*AddressFamily.*/AddressFamily any/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*ListenAddress 0.0.0.0.*/ListenAddress 0.0.0.0/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*ListenAddress ::.*/ListenAddress ::/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl restart sshd"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl restart ssh"
    echo "安装qemu-guest-agent..."
    sudo virt-customize -v -x -a $qcow_file --run-command "yum install qemu-guest-agent -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl start qemu-guest-agent"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl enable qemu-guest-agent"
elif [[ "$qcow_file" == *"almalinux8"* || "$qcow_file" == *"centos9-stream"* || "$qcow_file" == *"centos8-stream"* || "$qcow_file" == *"centos7"* ]]; then
    echo "处理AlmaLinux 8/CentOS系统..."
    sudo virt-customize -v -x -a $qcow_file --run-command "yum update -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "yum install sudo -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "yum install cronie -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "yum install curl -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "yum install wget -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "yum install lsof -y"
    echo "启用SSH功能..."
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl enable ssh"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl start ssh"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl enable sshd"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl start sshd"
    
    echo "清理可能冲突的SSH配置文件..."
    sudo virt-customize -v -x -a $qcow_file --run-command "rm -f /etc/ssh/sshd_config.d/*.conf"
    
    echo "启用root登录..."
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*PermitRootLogin.*/PermitRootLogin yes/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*PasswordAuthentication.*/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*Port.*/Port 22/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*AddressFamily.*/AddressFamily any/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*ListenAddress 0.0.0.0.*/ListenAddress 0.0.0.0/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*ListenAddress ::.*/ListenAddress ::/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl restart sshd"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl restart ssh"
    echo "安装qemu-guest-agent..."
    sudo virt-customize -v -x -a $qcow_file --run-command "yum install qemu-guest-agent -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl start qemu-guest-agent"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl enable qemu-guest-agent"
else
    echo "处理其他系统（使用DNF）..."
    sudo virt-customize -v -x -a $qcow_file --run-command "dnf update -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "dnf install sudo -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "dnf install cronie -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "dnf install curl -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "dnf install wget -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "dnf install lsof -y"
    echo "启用SSH功能..."
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl enable ssh"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl start ssh"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl enable sshd"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl start sshd"
    
    echo "清理可能冲突的SSH配置文件..."
    sudo virt-customize -v -x -a $qcow_file --run-command "rm -f /etc/ssh/sshd_config.d/*.conf"
    
    echo "启用root登录..."
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*PermitRootLogin.*/PermitRootLogin yes/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*PasswordAuthentication.*/PasswordAuthentication yes/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*Port.*/Port 22/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*AddressFamily.*/AddressFamily any/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*ListenAddress 0.0.0.0.*/ListenAddress 0.0.0.0/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "sed -i 's/#*ListenAddress ::.*/ListenAddress ::/g' /etc/ssh/sshd_config"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl restart sshd"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl restart ssh"
    echo "安装qemu-guest-agent..."
    sudo virt-customize -v -x -a $qcow_file --run-command "dnf install qemu-guest-agent -y"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl start qemu-guest-agent"
    sudo virt-customize -v -x -a $qcow_file --run-command "systemctl enable qemu-guest-agent"
fi

# 通用的最终配置
echo "设置motd和密码..."
sudo virt-customize -v -x -a $qcow_file --run-command "echo '' > /etc/motd"
sudo virt-customize -v -x -a $qcow_file --run-command "echo 'Modified from https://github.com/oneclickvirt/pve_kvm_images' >> /etc/motd"
sudo virt-customize -v -x -a $qcow_file --run-command "echo 'Related repo https://github.com/spiritLHLS/pve' >> /etc/motd"
sudo virt-customize -v -x -a $qcow_file --run-command "echo '--by https://t.me/spiritlhl' >> /etc/motd"
sudo virt-customize -v -x -a $qcow_file --run-command "echo root:oneclickvirt | chpasswd"

# 不是所有机器都需要IPV6保活，故而暂不添加保活命令
# sudo virt-customize -v -x -a $qcow_file --run-command "echo '*/1 * * * * curl -m 6 -s ipv6.ip.sb || curl -m 6 -s ipv6.ip.sb' | crontab -"
echo "创建备份..."
cp $qcow_file ${qcow_file}.bak
echo "复制新文件..."
cp $qcow_file ${qcow_file}.tmp
echo "覆盖原文件..."
mv ${qcow_file}.tmp $qcow_file
rm -rf *.bak
echo "$qcow_file修改完成"
