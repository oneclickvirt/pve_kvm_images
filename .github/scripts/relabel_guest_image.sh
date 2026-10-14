#!/usr/bin/env bash
set -euo pipefail
[[ "${RUNNER_ENVIRONMENT:-}" == github-hosted ]] || { echo 'A disposable GitHub-hosted runner is required' >&2; exit 1; }
image=${1:?Expected a guest image}
[[ -s "$image" ]] || { echo 'Guest image is missing' >&2; exit 1; }
# The guestfs API fails if setfiles is absent; it never substitutes a boot flag.
sudo timeout --kill-after=30s 15m guestfish --rw -a "$image" -i \
    available selinuxrelabel : \
    selinux-relabel /etc/selinux/targeted/contexts/files/file_contexts / force:true : \
    rm-f /.autorelabel
context=$(sudo timeout --kill-after=30s 240s guestfish --ro -a "$image" -i \
    getxattr /etc/ld.so.cache security.selinux | tr -d '\000')
[[ "$context" == *:ld_so_cache_t:* ]] || { echo 'Guest library cache SELinux label was not restored' >&2; exit 1; }
printf 'Guest SELinux label verified: %s\n' "$context"
