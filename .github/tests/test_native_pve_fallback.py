import hashlib
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


scripts = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location('pve_fallback', scripts / 'native_pve_smoke.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class NativePVEFallbackTests(unittest.TestCase):
    def assets(self, scope='all'):
        kinds = ['vm'] + (['container'] * 4 if scope == 'all' else [])
        return [{'kind': kind, 'name': f'image-{i}.' + ('qcow2' if kind == 'vm' else 'tar.zst'),
                 'repo': 'pve_kvm_images' if kind == 'vm' else 'pve_lxc_images',
                 'id': i + 1, 'size': 7, 'digest': 'sha256:' + hashlib.sha256(b'fixture').hexdigest(),
                 'browser_download_url': f'https://example.invalid/{i}'} for i, kind in enumerate(kinds)]

    def records(self, assets, vm_execution='native'):
        return [{'kind': a['kind'], 'image': a['name'], 'success': True,
                 'backend': 'pct' if a['kind'] == 'container' else 'qm' if vm_execution == 'native' else 'qemu-tcg'}
                for a in assets]

    def test_only_auto_uses_the_capability_based_fallback(self):
        self.assertEqual(runtime.vm_execution_mode('kvm', 'auto'), 'native')
        self.assertEqual(runtime.vm_execution_mode('tcg', 'auto'), 'runner')
        for outer in ('kvm', 'tcg'):
            self.assertEqual(runtime.vm_execution_mode(outer, 'native'), 'native')
            self.assertEqual(runtime.vm_execution_mode(outer, 'runner'), 'runner')
        with self.assertRaises(ValueError):
            runtime.vm_execution_mode('tcg', 'unknown')

    def run_fixture(self, folder, scope='all', mode='auto', acceleration='tcg', output=None):
        assets = self.assets(scope)
        if output is None:
            output = io.StringIO()
        with mock.patch.dict(runtime.os.environ, {'GH_TOKEN': 'fixture-token'}), \
             mock.patch.object(runtime, 'select_assets', return_value=assets), \
             mock.patch.object(runtime, 'download', side_effect=lambda url, path: path.write_bytes(b'fixture')), \
             mock.patch.object(runtime, 'kvm_available', side_effect=AssertionError('forced TCG must not probe KVM')), \
             redirect_stdout(output):
            runtime.run(folder, acceleration, scope, mode)
        return output.getvalue()

    def test_software_host_keeps_native_containers_and_direct_vm_distinct(self):
        assets = self.assets()
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(runtime, 'run_native_host', return_value=self.records(assets[1:])) as native, \
             mock.patch.object(runtime, 'qemu_test') as direct:
            output = self.run_fixture(Path(temporary))
            self.assertEqual(native.call_args.args[1], assets[1:])
            self.assertIs(native.call_args.args[2], False)
            self.assertEqual(native.call_args.args[3], 'runner')
            self.assertEqual(direct.call_args.kwargs, {'acceleration': 'tcg'})
            self.assertEqual(direct.call_args.args[1], Path(temporary) / assets[0]['name'])
        self.assertIn('native_images=4 runner_qemu_images=1', output)
        self.assertIn('PVE_RUNNER_IMAGE_RESULT', output)
        self.assertNotIn('NATIVE_PVE_SMOKE_RESULT', output)

    def test_vm_only_runner_path_does_not_provision_an_unused_pve_host(self):
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(runtime, 'run_native_host') as native, \
             mock.patch.object(runtime, 'qemu_test') as direct:
            output = self.run_fixture(Path(temporary), scope='vm')
        native.assert_not_called()
        direct.assert_called_once()
        self.assertIn('images=1 native_images=0 runner_qemu_images=1', output)

    def test_explicit_native_failure_is_not_replaced_with_direct_success(self):
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(runtime, 'run_native_host', side_effect=RuntimeError('native boot failed')), \
             mock.patch.object(runtime, 'qemu_test') as direct:
            with self.assertRaisesRegex(RuntimeError, 'native boot failed'):
                self.run_fixture(Path(temporary), scope='vm', mode='native')
        direct.assert_not_called()

    def test_direct_failure_cannot_create_a_success_record(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(runtime, 'qemu_test', side_effect=RuntimeError('guest network failed')):
            with self.assertRaisesRegex(RuntimeError, 'guest network failed'):
                self.run_fixture(Path(temporary), scope='vm', output=output)
        self.assertNotIn('PVE_RUNNER_IMAGE_RESULT', output.getvalue())
        self.assertNotIn('PVE_SMOKE_RESULT success=true', output.getvalue())

    def test_wrong_backend_missing_duplicate_or_failed_results_are_rejected(self):
        assets = self.assets()
        valid = self.records(assets, 'runner')
        runtime.validate_results(assets, valid, 'runner')
        wrong_backend = [dict(r) for r in valid]
        wrong_backend[0]['backend'] = 'qm'
        failed = [dict(r) for r in valid]
        failed[0]['success'] = False
        for records in (wrong_backend, valid[:-1], valid + valid[:1], [valid[0]] * 5, failed):
            with self.subTest(records=records), self.assertRaises(ValueError):
                runtime.validate_results(assets, records, 'runner')
        with self.assertRaises(ValueError):
            runtime.validate_results([], [], 'runner')

    def test_native_success_requires_native_vm_attribution(self):
        assets = self.assets()
        runtime.validate_results(assets, self.records(assets), 'native')
        with self.assertRaises(ValueError):
            runtime.validate_results(assets, self.records(assets, 'runner'), 'native')

    def test_download_identity_failure_stops_both_execution_backends(self):
        assets = self.assets('vm')
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.dict(runtime.os.environ, {'GH_TOKEN': 'fixture-token'}), \
             mock.patch.object(runtime, 'select_assets', return_value=assets), \
             mock.patch.object(runtime, 'download', side_effect=lambda url, path: path.write_bytes(b'wrong')), \
             mock.patch.object(runtime, 'run_native_host') as native, \
             mock.patch.object(runtime, 'qemu_test') as direct, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                runtime.run(Path(temporary), 'tcg', 'vm')
        native.assert_not_called()
        direct.assert_not_called()


if __name__ == '__main__':
    unittest.main()
