#!/usr/bin/env python3
"""Run real qm/pct in an isolated PVE guest on a GitHub-hosted runner."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time

from hosted_image_test import CHECK, isolated_environment, kvm_available
from release_assets import Publisher


SCRIPTS = Path(__file__).resolve().parent
BASE_URL = 'https://cloud.debian.org/images/cloud/trixie/latest/'
BASE_NAME = 'debian-13-genericcloud-amd64.qcow2'


def command(args, **kwargs):
    return subprocess.run(args, check=True, timeout=kwargs.pop('timeout', 120),
                          env=isolated_environment(), **kwargs)


def download(url, destination):
    command(['curl', '--fail', '--location', '--silent', '--show-error', '--connect-timeout', '15',
             '--max-time', '900', '--retry', '3', '--retry-max-time', '180', '-o', str(destination), url], timeout=1100)


def digest(file, algorithm):
    value = hashlib.new(algorithm)
    with file.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def select_assets(token):
    selected = []
    for repo, tag, patterns, kind in [
        ('pve_kvm_images', 'debian', [r'debian13\.qcow2'], 'vm'),
        ('pve_lxc_images', 'maintained', [r'debian_12_.*_amd64\.tar\.zst', r'debian_13_.*_amd64\.tar\.zst',
                                       r'ubuntu_24\.04_.*_amd64\.tar\.zst', r'ubuntu_26\.04_.*_amd64\.tar\.zst'], 'container'),
    ]:
        publisher = Publisher('oneclickvirt/' + repo, token)
        release = publisher.request(publisher.base + '/releases/tags/' + tag)
        if release['draft'] or release['prerelease']:
            raise ValueError('unpublished native PVE input')
        assets = list(publisher.assets(release['id']).values())
        for pattern in patterns:
            candidates = [a for a in assets if re.fullmatch(pattern, a['name']) and a.get('state') == 'uploaded' and a.get('size')]
            if not candidates:
                raise ValueError('native PVE input is unavailable: ' + repo + '/' + pattern)
            asset = max(candidates, key=lambda a: (a['updated_at'], a['id']))
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', asset['name']) or not re.fullmatch(r'sha256:[0-9a-f]{64}', asset.get('digest') or ''):
                raise ValueError('native PVE input needs a safe filename and SHA256 digest')
            selected.append({k: asset[k] for k in ('id', 'name', 'size', 'digest', 'browser_download_url')} | {'kind': kind, 'repo': repo})
    return selected


def run(folder, acceleration):
    accelerated = acceleration == 'auto' and kvm_available()
    print('NATIVE_PVE_OUTER_ACCELERATION ' + ('kvm' if accelerated else 'tcg'), flush=True)
    manifest = select_assets(os.environ['GH_TOKEN'])
    for asset in manifest:
        path = folder / asset['name']
        download(asset['browser_download_url'], path)
        if path.stat().st_size != asset['size'] or 'sha256:' + digest(path, 'sha256') != asset['digest']:
            raise ValueError('native PVE input identity mismatch: ' + asset['name'])
        print('NATIVE_PVE_INPUT ' + json.dumps({k: asset[k] for k in ('repo', 'name', 'id', 'size', 'digest')}), flush=True)
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    checksums = folder / 'SHA512SUMS'
    base = folder / BASE_NAME
    download(BASE_URL + 'SHA512SUMS', checksums)
    matches = [line.split()[0] for line in checksums.read_text().splitlines()
               if len(line.split()) == 2 and line.split()[1].lstrip('*./') == BASE_NAME]
    if len(matches) != 1 or not re.fullmatch('[0-9a-f]{128}', matches[0]):
        raise ValueError('missing Debian host image SHA512')
    download(BASE_URL + BASE_NAME, base)
    if digest(base, 'sha512') != matches[0]:
        raise ValueError('Debian host image SHA512 mismatch')
    disk = folder / 'pve-host.qcow2'
    command(['qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2', '-b', str(base), str(disk)])
    command(['qemu-img', 'resize', str(disk), '32G'])
    key = folder / 'ssh-key'
    command(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)])
    public = key.with_suffix('.pub').read_text().strip()
    user = folder / 'user-data'
    user.write_text('#cloud-config\nhostname: pve-ci\npreserve_hostname: false\nssh_pwauth: false\nusers:\n'
                    '  - name: ci\n    groups: [sudo]\n    shell: /bin/bash\n    lock_passwd: true\n'
                    '    sudo: ["ALL=(ALL) NOPASSWD:ALL"]\n    ssh_authorized_keys:\n      - ' + public + '\n')
    metadata = folder / 'meta-data'
    metadata.write_text('instance-id: pve-ci\nlocal-hostname: pve-ci\n')
    seed = folder / 'seed.img'
    command(['cloud-localds', str(seed), str(user), str(metadata)])
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    ssh_options = ['-F', '/dev/null', '-i', str(key), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
                   '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=' + str(folder / 'known_hosts'),
                   '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=4']
    target = 'ci@127.0.0.1'

    def ssh(script, **kwargs):
        return command(['ssh'] + ssh_options + ['-p', str(port), target, script], **kwargs)

    def wait_host(previous=None, require_pve=False):
        deadline = time.monotonic() + (1200 if not accelerated else 600)
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('disposable PVE host exited')
            try:
                result = ssh('cat /proc/sys/kernel/random/boot_id; uname -r', capture_output=True, text=True, timeout=20)
                lines = result.stdout.strip().splitlines()
                if len(lines) == 2 and re.fullmatch('[0-9a-f-]{36}', lines[0]) and lines[0] != previous and (not require_pve or lines[1].endswith('-pve')):
                    return lines[0]
            except (subprocess.SubprocessError, OSError):
                pass
            time.sleep(5)
        raise RuntimeError('disposable PVE host readiness or kernel reboot budget exhausted')

    qemu = ['qemu-system-x86_64', '-machine', 'q35', '-accel', 'kvm' if accelerated else 'tcg,thread=multi',
            '-cpu', 'host' if accelerated else 'max', '-m', '4096', '-smp', '2', '-display', 'none',
            '-serial', 'file:' + str(folder / 'host-serial.log'),
            '-drive', 'file=' + str(disk) + ',format=qcow2,if=virtio',
            '-drive', 'file=' + str(seed) + ',format=raw,if=virtio,readonly=on',
            '-netdev', 'user,id=net0,hostfwd=tcp:127.0.0.1:' + str(port) + '-:22',
            '-device', 'virtio-net-pci,netdev=net0',
            '-object', 'rng-random,id=rng,filename=/dev/urandom', '-device', 'virtio-rng-pci,rng=rng']
    accepted = False
    with (folder / 'host-qemu.log').open('wb') as log:
        process = subprocess.Popen(qemu, stdout=log, stderr=log, env=isolated_environment())
        try:
            boot = wait_host()
            ssh('sudo cloud-init status --wait', timeout=300)
            paths = [SCRIPTS / 'native_pve_provision.sh', SCRIPTS / 'native_pve_guest.sh', folder / 'manifest.json']
            check = folder / 'guest-check.sh'
            check.write_text('set -eu\ntest "$(id -u)" = 0\n' + CHECK)
            paths.append(check)
            paths.extend(folder / a['name'] for a in manifest)
            command(['scp'] + ssh_options + ['-P', str(port)] + [str(p) for p in paths] + [target + ':/home/ci/'], timeout=600)
            ssh('sudo -n bash /home/ci/native_pve_provision.sh', timeout=2100)
            try:
                ssh('sudo -n reboot', timeout=30)
            except subprocess.CalledProcessError as error:
                if error.returncode != 255:
                    raise
            wait_host(boot, require_pve=True)
            # Stream native progress and diagnostics while keeping the acceptance
            # records separate from console noise. This host is disposable.
            ssh('sudo -n bash /home/ci/native_pve_guest.sh', timeout=2400)
            result = ssh('cat /home/ci/native-results.jsonl', capture_output=True, text=True)
            records = [json.loads(line.split(' ', 1)[1]) for line in result.stdout.splitlines() if line.startswith('NATIVE_PVE_IMAGE_RESULT ')]
            expected = {(a['kind'], a['name']) for a in manifest}
            if len(records) != len(expected) or {(r['kind'], r['image']) for r in records if r.get('success') is True} != expected:
                raise ValueError('incomplete native PVE image results')
            accepted = True
            print('NATIVE_PVE_SMOKE_RESULT success=true images=' + str(len(records)), flush=True)
        except subprocess.CalledProcessError as error:
            if error.stdout:
                print(error.stdout[-24000:], flush=True)
            if error.stderr:
                print(error.stderr[-16000:], flush=True)
            raise RuntimeError('native PVE command failed with exit ' + str(error.returncode)) from None
        finally:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            if not accepted:
                for name in ('host-serial.log', 'host-qemu.log'):
                    path = folder / name
                    if path.is_file():
                        print('Disposable PVE host diagnostics: ' + name + '\n' + path.read_text(errors='replace')[-18000:], flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--outer-accel', choices=['auto', 'tcg'], default='auto')
    args = parser.parse_args()
    if os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted' or os.environ.get('RUNNER_ARCH') != 'X64':
        raise RuntimeError('a disposable GitHub-hosted AMD64 runner is required')
    with tempfile.TemporaryDirectory(prefix='native-pve-', dir=os.environ.get('RUNNER_TEMP')) as temporary:
        run(Path(temporary), args.outer_accel)


if __name__ == '__main__':
    main()
