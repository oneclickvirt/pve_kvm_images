"""A boot-time relabel flag must never substitute for offline SELinux support."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


class SELinuxApplianceTests(unittest.TestCase):
    def test_manifest_extension_is_idempotent_and_absent_appliance_capability_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            appliance = root / 'guestfs'
            manifest = appliance / 'supermin.d/packages'
            manifest.parent.mkdir(parents=True)
            manifest.write_text('bash\nlibselinux1\n')
            binary = root / 'bin'
            binary.mkdir()
            commands = {
                'sudo': '#!/bin/sh\nexec "$@"\n',
                'find': '#!/bin/sh\nexit 0\n',
                'qemu-img': '#!/bin/sh\n: > "$4"\n',
                'timeout': '#!/bin/sh\nshift;shift;exec "$@"\n',
                'guestfish': '#!/bin/sh\nif [ "$1" = get-path ]; then printf "%s\\n" "$APPLIANCE_FIXTURE"; else printf "%s\\n" "$*" >> "$CALLS_FIXTURE"; exit "${MISSING_CAPABILITY:-0}"; fi\n',
            }
            for name, content in commands.items():
                (binary / name).write_text(content)
                (binary / name).chmod(0o755)
            environment = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'],
                               RUNNER_ENVIRONMENT='github-hosted', RUNNER_TEMP=str(root),
                               APPLIANCE_FIXTURE=str(appliance), CALLS_FIXTURE=str(root / 'calls'))
            for _ in range(2):
                subprocess.run(['bash', str(SCRIPTS / 'prepare_selinux_appliance.sh')], env=environment, check=True, timeout=5, capture_output=True)
            self.assertEqual(manifest.read_text(), 'bash\nlibselinux1\npolicycoreutils\n')
            self.assertIn('run : available selinuxrelabel', (root / 'calls').read_text())
            result = subprocess.run(['bash', str(SCRIPTS / 'prepare_selinux_appliance.sh')], env=dict(environment, MISSING_CAPABILITY='9'), timeout=5, capture_output=True)
            self.assertEqual(result.returncode, 9)
            self.assertNotIn(b'capability verified', result.stdout)
            self.assertEqual(list(root.glob('selinux-probe.*')), [])

    def test_private_or_persistent_hosts_are_rejected_before_any_mutation(self):
        result = subprocess.run(['bash', str(SCRIPTS / 'prepare_selinux_appliance.sh')],
                                env=dict(os.environ, RUNNER_ENVIRONMENT='self-hosted'),
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'disposable GitHub-hosted', result.stderr)


if __name__ == '__main__':
    unittest.main()
