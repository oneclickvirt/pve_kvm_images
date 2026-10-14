import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DebianSourceTests(unittest.TestCase):
    def configure(self, version, codename):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "sources"
        subprocess.run(
            ["bash", str(ROOT / "scripts/configure_debian_sources.sh"), version, codename, str(output)],
            check=True,
        )
        return output

    def test_bullseye_uses_archived_base_and_security_sources(self):
        output = self.configure("11", "bullseye")
        sources = (output / "debian.sources").read_text()
        self.assertIn("archive.debian.org/debian", sources)
        self.assertIn("Suites: bullseye bullseye-updates", sources)
        self.assertIn("URIs: https://archive.debian.org/debian-security", sources)
        self.assertIn("Suites: bullseye-security", sources)
        self.assertNotIn("non-free-firmware", sources)
        apt_config = (output / "99-archive-no-check").read_text()
        self.assertIn('Dir::Etc::sourcelist "/dev/null";', apt_config)
        self.assertIn('Acquire::Check-Valid-Until "false";', apt_config)

    def test_supported_live_releases_keep_security_mirror(self):
        for version, codename in (("12", "bookworm"), ("13", "trixie")):
            with self.subTest(codename=codename):
                output = self.configure(version, codename)
                sources = (output / "debian.sources").read_text()
                self.assertIn("URIs: https://deb.debian.org/debian", sources)
                self.assertIn(f"Suites: {codename} {codename}-updates {codename}-backports", sources)
                self.assertIn(f"Suites: {codename}-security", sources)
                self.assertIn('Dir::Etc::sourcelist "/dev/null";', (output / "99-archive-no-check").read_text())

    def test_rejects_unknown_version_pair(self):
        with tempfile.TemporaryDirectory() as output:
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/configure_debian_sources.sh"), "11", "bookworm", output],
                capture_output=True,
                text=True,
            )
        self.assertEqual(2, result.returncode)


class GuestRootExpansionTests(unittest.TestCase):
    def test_expands_a_small_ext4_guest_to_the_minimum_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bindir = root / "bin"
            bindir.mkdir()
            log = root / "commands.log"
            (bindir / "virt-filesystems").write_text("#!/bin/sh\nprintf '/dev/sda1 2048 ext4\n'\n")
            (bindir / "qemu-img").write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$COMMAND_LOG\"\n"
                "case \"$1\" in\n"
                "  info) printf '{\"virtual-size\":2147483648}\\n' ;;\n"
                "  create) : > \"$4\" ;;\n"
                "  check) test -s \"$2\" ;;\n"
                "esac\n"
            )
            (bindir / "virt-resize").write_text("#!/bin/sh\nprintf resized > \"$4\"\n")
            for command in bindir.iterdir():
                command.chmod(0o755)
            image = root / "guest.qcow2"
            image.write_bytes(b"original")
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/expand_guest_root.sh"), str(image)],
                env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "COMMAND_LOG": str(log)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, f"{result.stdout}\n{result.stderr}")
            self.assertIn("8589934592", log.read_text())
            self.assertTrue(image.is_file())
            self.assertFalse((root / "guest-expanded.qcow2").exists())

    def test_fails_closed_without_a_supported_ext4_partition(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bindir = root / "bin"
            bindir.mkdir()
            (bindir / "virt-filesystems").write_text("#!/bin/sh\nprintf '/dev/sda1 xfs\n'\n")
            (bindir / "qemu-img").write_text("#!/bin/sh\nexit 99\n")
            for command in bindir.iterdir():
                command.chmod(0o755)
            image = root / "guest.qcow2"
            image.write_bytes(b"original")
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/expand_guest_root.sh"), str(image)],
                env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"},
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(b"original", image.read_bytes())


if __name__ == "__main__":
    unittest.main()
