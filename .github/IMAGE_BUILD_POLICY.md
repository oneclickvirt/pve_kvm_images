# Hosted image maintenance

Image builds and boot tests use disposable GitHub-hosted Ubuntu runners. Every published image must pass the guest SSH listener, HTTPS/DNS and reboot checks. Publication failure retains previous release assets.

CentOS Stream 8 is retired and its maintained guest validation failed after reboot in run [38635941548](https://github.com/oneclickvirt/pve_kvm_images/actions/runs/38635941548). Scheduled CentOS builds therefore select Stream 9 only. The `include_retired` manual input retains the repair path for Stream 8; it never bypasses boot validation or deletes existing images.
