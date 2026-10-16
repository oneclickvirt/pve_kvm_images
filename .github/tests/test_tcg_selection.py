import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock


scripts = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(scripts))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, scripts / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = load('tcg_runtime', 'hosted_image_test.py')
suite = load('tcg_suite', 'published_image_suite.py')


class AccelerationSelectionTests(unittest.TestCase):
    def test_forced_tcg_never_probes_or_selects_kvm(self):
        with mock.patch.object(runtime, 'kvm_available', side_effect=AssertionError('KVM must not be used')):
            self.assertFalse(runtime.qemu_accelerated('tcg'))

    def test_auto_keeps_software_fallback_when_kvm_is_absent(self):
        for available in (True, False):
            with self.subTest(kvm=available), mock.patch.object(runtime, 'kvm_available', return_value=available):
                self.assertEqual(runtime.qemu_accelerated('auto'), available)

    def test_explicit_kvm_does_not_silently_turn_into_software(self):
        with mock.patch.object(runtime, 'kvm_available', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'explicitly requested'):
                runtime.qemu_accelerated('kvm')

    def test_software_overlay_tools_get_backend_settings_after_sudo(self):
        for tool in ('virt-customize', 'virt-log', 'virt-cat'):
            self.assertEqual(runtime.guestfs_command(tool, False), [
                'sudo', 'env', 'LIBGUESTFS_BACKEND=direct',
                'LIBGUESTFS_BACKEND_SETTINGS=force_tcg', tool,
            ])
            self.assertNotIn('LIBGUESTFS_BACKEND_SETTINGS=force_tcg', runtime.guestfs_command(tool, True))


class PublishedTCGSelectionTests(unittest.TestCase):
    def test_maintained_scope_excludes_retired_and_historical_assets(self):
        assets = [
            {'name': 'debian13.qcow2', 'tag': 'debian'},
            {'name': 'ubuntu2404.qcow2', 'tag': 'ubuntu'},
            {'name': 'ubuntu24.qcow2', 'tag': 'images'},
            {'name': 'centos8.qcow2', 'tag': 'centos'},
            {'name': 'alpine3.20.qcow2', 'tag': 'alpine'},
        ]
        rows = suite.matrix(assets, 'pve_kvm_images', 'maintained', 'vm', 'tcg')['include']
        self.assertEqual({row['image'] for row in rows}, {'debian13.qcow2', 'ubuntu2404.qcow2'})
        self.assertTrue(all(row['runner'] == 'ubuntu-24.04' and row['acceleration'] == 'tcg' for row in rows))
        self.assertEqual(len(suite.matrix(assets, 'pve_kvm_images', 'full', 'vm')['include']), 5)

    def test_both_schedules_distinct_automatic_and_software_jobs(self):
        assets = [{'name': 'debian13.qcow2', 'tag': 'debian'}]
        rows = suite.matrix(assets, 'pve_kvm_images', 'smoke', 'vm', 'both')['include']
        self.assertEqual(len(rows), 2)
        self.assertEqual({row['acceleration'] for row in rows}, {'auto', 'tcg'})

    def test_empty_maintained_selection_cannot_report_success(self):
        with self.assertRaisesRegex(ValueError, 'no published images'):
            suite.matrix([{'name': 'centos8.qcow2', 'tag': 'centos'}], 'pve_kvm_images', 'maintained', 'vm', 'tcg')


if __name__ == '__main__':
    unittest.main()
