# Hosted image maintenance

Image builds and boot tests use disposable GitHub-hosted Ubuntu runners. Every published image must pass the guest SSH listener, HTTPS/DNS and reboot checks. Publication failure retains previous release assets.

CentOS Stream 8 is retired and its maintained guest validation failed after reboot in run [38635941548](https://github.com/oneclickvirt/pve_kvm_images/actions/runs/38635941548). Scheduled CentOS builds therefore select Stream 9 only. The `include_retired` manual input retains the repair path for Stream 8; it never bypasses boot validation or deletes existing images.

The published-image workflow accepts `acceleration=tcg` to force software emulation even when the hosted runner exposes KVM. This also forces the libguestfs overlay preparation and failure diagnostics to use TCG. Weekly smoke tests exercise both automatic acceleration and forced TCG; guest execution, SSH listener, verified HTTPS/DNS and a changed boot ID after reboot are required in both modes. The `maintained` scope covers the current maintained assets while `full` and exact filenames retain manual access to historical assets.

These tests boot the released disk directly with QEMU. PVE-specific `qm` import and configuration, and `pct` template restoration, require a separate PVE host test; a QEMU or Incus result alone is not recorded as that test.
