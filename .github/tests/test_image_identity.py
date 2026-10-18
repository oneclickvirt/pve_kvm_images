import pathlib
import unittest

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[2]


class ImageIdentityGate(unittest.TestCase):
    def test_all_distributions_sanitize_after_customization_before_boot_and_publish(self):
        for distro in ('debian', 'ubuntu', 'centos', 'almalinux', 'rockylinux', 'alpine', 'archlinux'):
            with self.subTest(distro=distro):
                workflow = yaml.safe_load((ROOT / '.github/workflows' / (distro + '.yml')).read_text())
                builds = [step['run'] for job in workflow['jobs'].values()
                          for step in job.get('steps', []) if 'run' in step
                          and 'hosted_image_test.py --file' in step['run']]
                self.assertEqual(len(builds), 1)
                script = builds[0]
                clean = script.index('bash .github/scripts/sanitize_guest.sh "$file"')
                self.assertLess(script.rfind('virt-customize'), clean)
                self.assertLess(clean, script.index('python3 .github/scripts/hosted_image_test.py'))
                self.assertLess(clean, script.index('python3 "$RUNNER_TEMP/ci-release-assets.py"'))

    def test_manual_rebuilder_also_cleans_after_last_customization(self):
        script = (ROOT / 'rebuild_qcow2.sh').read_text()
        self.assertGreater(script.index('virt-sysprep'), script.rfind('sudo virt-customize'))


if __name__ == '__main__':
    unittest.main()
