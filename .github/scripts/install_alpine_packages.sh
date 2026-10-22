#!/bin/sh
set -eu

# Refresh the index on every attempt so a mirror update cannot leave apk
# requesting a package version that has already been replaced.
for attempt in 1 2 3; do
    if apk update && apk add sudo qemu-guest-agent bash-completion unzip wget curl \
        net-tools iputils nano screen less vim bzip2 mtr htop bind-tools zstd \
        cronie lsof openssh openrc; then
        exit 0
    fi
    if [ "$attempt" -lt 3 ]; then
        echo "Alpine package installation attempt $attempt failed; refreshing the index before retrying." >&2
        sleep "$((attempt * 5))"
    fi
done

echo 'Alpine package installation failed after 3 attempts.' >&2
exit 1
