import importlib.util
import json
from pathlib import Path
import socket
import tarfile
import tempfile
import threading
import unittest
from unittest import mock
import subprocess

spec=importlib.util.spec_from_file_location('hosted_runtime',Path(__file__).resolve().parents[1]/'scripts/hosted_image_test.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)


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

if __name__=='__main__':unittest.main()
