# pve_kvm_images

[![Downloads](https://ghdownload.spiritlhl.net/oneclickvirt/pve_kvm_images?color=00c62d)](https://github.com/oneclickvirt/pve_kvm_images/releases)

[![Build PVE KVM images](https://github.com/oneclickvirt/pve_kvm_images/actions/workflows/main.yml/badge.svg)](https://github.com/oneclickvirt/pve_kvm_images/actions/workflows/main.yml)

## 说明

镜像内在执行包管理器更新/安装前，会先把软件源切换到阿里云镜像并刷新索引/缓存，以规避部分官方源不可用导致的更新失败。

Releases中的镜像(每日拉取镜像进行自动修补和更新)：

已预安装：wget curl openssh-server sshpass sudo cron(cronie) qemu-guest-agent

已预开启安装cloudinit，开启SSH登陆，预设SSH监听IPV4和IPV6的22端口，开启允许密码验证登陆

所有镜像均开启允许root用户进行SSH登录

默认用户名：```root```

默认密码：```oneclickvirt```

如果使用务必自行修改密码，否则会有被骇入的风险

旧的通过手动修补的镜像仓库：

https://github.com/oneclickvirt/kvm_images

会支持一些旧的镜像

本仓库的虚拟机镜像服务于： https://github.com/oneclickvirt/pve

## Introduce

Mirrors in Releases (pulls mirrors daily for automatic patching and updating):

Pre-installed: wget curl openssh-server sshpass sudo cron(cronie) qemu-guest-agent

Pre-enabled to install cloudinit, enable SSH login, pre-configure SSH to listen on port 22 for IPV4 and IPV6, and enable password authentication for login.

All mirrors are enabled to allow SSH login for root users.

Default username: ```root```.

Default password: ```oneclickvirt```.

Be sure to change the password if you use it, otherwise you risk being hacked.

Older repositories that were patched manually:

https://github.com/oneclickvirt/kvm_images

Some older mirrors will be supported

This repository VM images serves https://github.com/oneclickvirt/pve

## 感谢

https://down.idc.wiki/Image/realServer-Template/current/qcow2/

提供的原始系统镜像，原始镜像仅开启了cloudinit，其他一切未开启，且不支持root进行SSH登录

## Thanks

https://down.idc.wiki/Image/realServer-Template/current/qcow2/

The original system image provided, the original image only enabled cloudinit, everything else is not enabled, and does not support root for SSH logins.

## 不要使用--Do-Not-USE

Source code (zip)

Source code (tar.gz)
