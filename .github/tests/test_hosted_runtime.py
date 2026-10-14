import importlib.util
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import socket
import tarfile
import tempfile
import threading
import unittest
from unittest import mock
import subprocess
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location('hosted_runtime',Path(__file__).resolve().parents[1]/'scripts/hosted_image_test.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)


class CredentialIsolationTests(unittest.TestCase):
    def test_child_commands_do_not_inherit_github_tokens(self):
        with mock.patch.dict(runtime.os.environ, {'GH_TOKEN':'secret-a','GITHUB_TOKEN':'secret-b'}), \
             mock.patch.object(runtime.subprocess,'run') as execute:
            runtime.run(['fixture'],env={'GH_TOKEN':'override','PRESERVED':'yes'})
        environment=execute.call_args.kwargs['env']
        self.assertNotIn('GH_TOKEN',environment)
        self.assertNotIn('GITHUB_TOKEN',environment)
        self.assertEqual(environment['PRESERVED'],'yes')


class GuestAgentTests(unittest.TestCase):
    def exchange(self,reply,expect_response=True):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'agent.sock'
            server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(str(path));server.listen(1)
            errors=[]
            def serve():
                try:
                    with server.accept()[0] as client:
                        request=json.loads(client.makefile('rb').readline())
                        reply(client,request)
                except Exception as error:errors.append(error)
                finally:server.close()
            thread=threading.Thread(target=serve);thread.start()
            try:return runtime.qga_command(path,'guest-shutdown' if not expect_response else 'guest-ping',expect_response=expect_response)
            finally:
                thread.join(5)
                if thread.is_alive():raise AssertionError('guest-agent exchange did not finish')
                if errors:raise errors[0]

    def test_eof_is_failure(self):
        with self.assertRaises(ConnectionError):self.exchange(lambda client,request:None)

    def test_split_response_and_stale_message(self):
        def reply(client,request):
            client.sendall(b'{"return":"stale","id":"old"}\n')
            payload=(json.dumps({'return':{},'id':request['id']})+'\n').encode()
            client.sendall(payload[:7]);client.sendall(payload[7:])
        self.assertEqual(self.exchange(reply),{})

    def test_shutdown_does_not_expect_a_reply(self):
        self.assertIsNone(self.exchange(lambda client,request:None,expect_response=False))

    def test_raw_rootfs_receives_consumer_dns_including_cloud_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            for variant in ['default','cloud']:
                rootfs=folder/('debian_13_trixie_amd64_'+variant+'.tar.xz');rootfs.touch()
                metadata,_=runtime.unpack(rootfs,folder,'incus')
                with tarfile.open(metadata) as archive:
                    dns=archive.extractfile('templates/resolv.conf.tpl').read().decode()
                    self.assertIn('user.hosted_dns',dns)
                    self.assertNotIn('127.0.0.53',dns)
                    if variant=='cloud':
                        seed=archive.extractfile('templates/network-config.tpl').read().decode()
                        self.assertIn('nameservers:',seed)
                        self.assertIn('user.hosted_dns',seed)

    def test_cloud_rootfs_receives_consumer_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);rootfs=folder/'debian_13_trixie_amd64_cloud.tar.xz';rootfs.touch()
            metadata,actual=runtime.unpack(rootfs,folder,'incus')
            self.assertEqual(actual,rootfs)
            with tarfile.open(metadata) as archive:
                manifest=archive.extractfile('metadata.yaml').read().decode()
                self.assertIn('/var/lib/cloud/seed/nocloud-net/network-config',manifest)
                self.assertIn('dhcp4: true',archive.extractfile('templates/network-config.tpl').read().decode())



class SSHTransportTests(unittest.TestCase):
    def test_password_is_only_in_subprocess_environment(self):
        with mock.patch.object(runtime, 'run', return_value=mock.Mock(stdout='boot-id')) as execute:
            self.assertEqual(runtime.ssh_command(22022, Path('/tmp/key'), runtime.CHECK, 'fixture-password'), 'boot-id')
        args, options = execute.call_args
        self.assertNotIn('fixture-password', ' '.join(args[0]))
        self.assertEqual(options['env']['SSHPASS'], 'fixture-password')
        self.assertIn('root@127.0.0.1', args[0])

    def test_guest_assertion_failure_is_not_success(self):
        with mock.patch.object(runtime, 'run', side_effect=subprocess.CalledProcessError(1, ['ssh'], stderr='network failed')):
            with self.assertRaises(subprocess.CalledProcessError):
                runtime.ssh_command(22022, Path('/tmp/key'), runtime.CHECK)

class QEMUNetworkTests(unittest.TestCase):
    def test_qemu_runtime_installs_guestfs_before_returning(self):
        script = (Path(__file__).resolve().parents[1] / 'scripts/prepare_hosted_runtime.sh').read_text()
        self.assertLess(script.index('apt-get install -y --no-install-recommends libguestfs-tools'),
                        script.index('if [[ "$runtime" == qemu ]]; then exit 0; fi'))

    def test_cloud_network_matches_stable_qemu_mac(self):
        config=runtime.qemu_network_config()
        device=' '.join(runtime.qemu_network_device())
        self.assertIn('macaddress: '+runtime.HOSTED_NIC_MAC,config)
        self.assertIn('mac='+runtime.HOSTED_NIC_MAC,device)
        self.assertIn('dhcp4: true',config)
        self.assertNotIn('name: eth0',config)


class FirmwareFallbackTests(unittest.TestCase):
    def test_prior_kernel_does_not_hide_a_stalled_efi_loader_after_relabel_reboot(self):
        console = ('BdsDxe: starting Boot0001 "UEFI Misc Device"\n'
                   'Linux version 5.14.0\nRelabel all filesystems\n'
                   'reboot: Restarting system\n'
                   'BdsDxe: starting Boot0003 "rocky" from /EFI/rocky/shimx64.efi\n')
        self.assertTrue(runtime.firmware_without_kernel(console))

    def test_new_kernel_after_efi_loader_is_not_a_firmware_failure(self):
        console = 'BdsDxe: starting Boot0003 "rocky"\nLinux version 5.14.0\n'
        self.assertFalse(runtime.firmware_without_kernel(console))

    def test_bios_boot_and_running_kernel_do_not_trigger_efi_fallback(self):
        for console in ['SeaBIOS\nBooting from Hard Disk\n', 'Linux version 5.14.0\nsshd started\n', '']:
            self.assertFalse(runtime.firmware_without_kernel(console))


class NativeStartupDiagnosticsTests(unittest.TestCase):
    def test_start_failure_prints_bounded_incus_instance_log(self):
        failure=subprocess.CalledProcessError(1,['sudo','incus','start','test-image'],stderr='forkstart failed')
        diagnostic=subprocess.CompletedProcess(['sudo','incus','info'],0,'x'*7000,'')
        output=io.StringIO()
        with mock.patch.object(runtime,'run',side_effect=[None,None,None,failure]), \
             mock.patch.object(runtime.subprocess,'run',return_value=diagnostic) as execute, \
             redirect_stderr(output):
            with self.assertRaises(subprocess.CalledProcessError):
                runtime.native_test(Path('/tmp'),SimpleNamespace(name='image.tar.xz'),Path('/tmp/rootfs.tar.xz'))
        self.assertIn('x'*100,output.getvalue())
        self.assertLessEqual(len(output.getvalue()),6100)
        diagnostic_call=execute.call_args_list[0]
        self.assertEqual(diagnostic_call.args[0],['sudo','incus','info',mock.ANY,'--show-log'])
        self.assertEqual(diagnostic_call.kwargs['timeout'],30)

    def test_diagnostic_failure_does_not_replace_start_failure(self):
        failure=subprocess.CalledProcessError(1,['sudo','incus','start','test-image'])
        output=io.StringIO()
        with mock.patch.object(runtime,'run',side_effect=[None,None,None,failure]), \
             mock.patch.object(runtime.subprocess,'run',side_effect=[
                 subprocess.TimeoutExpired('incus info',30),
                 subprocess.TimeoutExpired('incus delete',60),
                 OSError('incus image delete unavailable'),
             ]), \
             redirect_stderr(output):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                runtime.native_test(Path('/tmp'),SimpleNamespace(name='image.tar.xz'),Path('/tmp/rootfs.tar.xz'))
        self.assertIs(raised.exception,failure)
        self.assertIn('diagnostics unavailable: TimeoutExpired',output.getvalue())

class GuestDHCPRecoveryTests(unittest.TestCase):
    def test_readiness_probe_attempts_available_guest_dhcp_clients(self):
        source=runtime.CHECK
        self.assertIn('network_recovery()',source)
        self.assertIn('dhclient -1 "$interface"',source)
        self.assertIn('udhcpc -n -q',source)
        self.assertIn('dhcpcd -n',source)
        self.assertLess(source.index('network_recovery\n  https_check'),source.index('cat /proc/sys/kernel/random/boot_id'))

if __name__=='__main__':unittest.main()
