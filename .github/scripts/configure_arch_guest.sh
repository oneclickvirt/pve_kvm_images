#!/bin/bash
set -euo pipefail
export SYSTEMD_OFFLINE=1

# pacman-key starts agents inside the guest. Stop them on success and failure
# so libguestfs can unmount its temporary device filesystem.
cleanup() {
    gpgconf --homedir /etc/pacman.d/gnupg --kill all || true
    sync
}
trap cleanup EXIT

# libguestfs provides /proc but its minimal /dev lacks these standard links.
# Kernel package hooks use /dev/stdin when writing mkinitcpio presets.
test -d /proc/self/fd
ln -sfn /proc/self/fd /dev/fd
ln -sfn /proc/self/fd/0 /dev/stdin
ln -sfn /proc/self/fd/1 /dev/stdout
ln -sfn /proc/self/fd/2 /dev/stderr

# Build against the official mirror first to avoid a stale mirror database.
# Keep a second mirror available if a package download fails.
cat > /etc/pacman.d/mirrorlist <<'MIRRORS'
Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch
Server = https://mirrors.aliyun.com/archlinux/$repo/os/$arch
MIRRORS
printf '%s\n' 'nameserver 8.8.8.8' 'nameserver 1.1.1.1' > /etc/resolv.conf
pacman-key --init
pacman-key --populate archlinux
pacman -Sy --noconfirm archlinux-keyring
pacman -Syu --noconfirm
pacman -S --needed --noconfirm cloud-guest-utils qemu-guest-agent sudo \
    bash-completion unzip wget curl axel net-tools iputils nano screen less \
    vim bzip2 htop zstd cronie lsof openssh
if ! pacman -S --needed --noconfirm spice-vdagent bind; then
    echo 'Optional desktop/DNS utilities could not be installed' >&2
fi

# pacman can return success despite a failing post-transaction hook. Rebuild
# explicitly and validate the files before the image can reach publication.
mkdir -p /etc/mkinitcpio.conf.d
printf '%s\n' 'MODULES+=(virtio_pci virtio_blk virtio_scsi btrfs)' \
    > /etc/mkinitcpio.conf.d/90-cloud.conf
mkinitcpio -P
test -s /boot/vmlinuz-linux
test -s /boot/initramfs-linux.img
lsinitcpio /boot/initramfs-linux.img > /dev/null
grub-mkconfig -o /boot/grub/grub.cfg
test -s /boot/grub/grub.cfg
systemctl enable qemu-guest-agent
systemctl enable sshd
pacman -Scc --noconfirm

# Preserve the preferred mirror for users, with the official fallback.
cat > /etc/pacman.d/mirrorlist <<'MIRRORS'
Server = https://mirrors.aliyun.com/archlinux/$repo/os/$arch
Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch
MIRRORS
