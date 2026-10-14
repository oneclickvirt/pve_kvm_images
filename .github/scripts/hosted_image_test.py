#!/usr/bin/env python3
"""Boot public images on disposable hosted runners, with bounded software fallback."""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
import uuid
import zipfile
import fcntl

CHECK = """set -eu
test -s /etc/os-release || test -s /usr/lib/os-release || test -s /etc/alpine-release || test -s /etc/openwrt_release
awk '$2 ~ /:0016$/ && $4 == "0A" {found=1} END {exit !found}' /proc/net/tcp /proc/net/tcp6
curl -fLsS --connect-timeout 10 --max-time 30 https://github.com -o /dev/null
cat /proc/sys/kernel/random/boot_id
"""


def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=kwargs.pop('timeout', 120), **kwargs)


def native_test(folder, metadata, rootfs, vm=False, cli='incus'):
    alias='image-'+uuid.uuid4().hex[:12]; name='test-'+uuid.uuid4().hex[:12]
    prefix=['sudo', cli]
    def execute(script):
        result=run(prefix+['exec',name,'--','/bin/sh','-c',script],capture_output=True,text=True,timeout=50)
        return result.stdout.strip()
    def ready(previous=None):
        deadline=time.monotonic()+(600 if vm else 180)
        while time.monotonic()<deadline:
            try:
                boot=execute(CHECK)
                if boot and boot!=previous: return boot
            except (subprocess.SubprocessError,OSError): pass
            time.sleep(5)
        subprocess.run(prefix+['info',name,'--show-log'],timeout=30)
        raise RuntimeError('guest boot, SSH listener or external network check timed out')
    try:
        run(prefix+['image','import',str(metadata),str(rootfs),'--alias',alias],timeout=180)
        command=prefix+['init',alias,name,'-c','limits.memory=1GiB']
        if vm: command+=['--vm','-c','security.secureboot=false']
        run(command)
        # Older images have init systems that need nesting for their own mount units.
        if not vm: run(prefix+['config','set',name,'security.nesting','true'])
        run(prefix+['start',name],timeout=180)
        boot=ready()
        run(prefix+['restart',name,'--force'],timeout=180)
        ready(boot)
        print('Runtime validation: native '+('VM' if vm else 'container')+' boot, SSH listener, network and restart passed')
    finally:
        subprocess.run(prefix+['delete',name,'--force'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
        subprocess.run(prefix+['image','delete',alias],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)


def qga_command(sock, command, arguments=None):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as stream:
        stream.settimeout(10);stream.connect(str(sock))
        stream.sendall((json.dumps({'execute':command,'arguments':arguments or {}})+'\n').encode())
        buffer=b''
        while True:
            buffer+=stream.recv(65536)
            if b'\n' not in buffer: continue
            line,buffer=buffer.split(b'\n',1)
            value=json.loads(line)
            if 'error' in value: raise RuntimeError('guest agent rejected command')
            if 'return' in value: return value['return']


def qga_check(sock):
    response=qga_command(sock,'guest-exec',{'path':'/bin/sh','arg':['-c',CHECK],'capture-output':True})
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        value=qga_command(sock,'guest-exec-status',{'pid':response['pid']})
        if value.get('exited'):
            if value.get('exitcode')!=0: raise RuntimeError('guest runtime assertion failed')
            return base64.b64decode(value.get('out-data','')).decode().strip()
        time.sleep(2)
    raise TimeoutError('guest assertion budget exhausted')


def firmware(arch, folder):
    candidates=[('/usr/share/AAVMF/AAVMF_CODE.fd','/usr/share/AAVMF/AAVMF_VARS.fd'),
                ('/usr/share/qemu-efi-aarch64/QEMU_EFI.fd',None)] if arch=='arm64' else [
                ('/usr/share/OVMF/OVMF_CODE_4M.fd','/usr/share/OVMF/OVMF_VARS_4M.fd'),
                ('/usr/share/OVMF/OVMF_CODE.fd','/usr/share/OVMF/OVMF_VARS.fd')]
    for code,variables in candidates:
        if Path(code).exists():
            if variables and Path(variables).exists():
                target=folder/'firmware-vars.fd';shutil.copyfile(variables,target)
                return ['-drive',f'if=pflash,format=raw,readonly=on,file={code}',
                        '-drive',f'if=pflash,format=raw,file={target}']
            return ['-bios',code]
    raise RuntimeError('hosted UEFI firmware is unavailable')


def qemu_test(folder, disk, console_only=False):
    arch='arm64' if os.uname().machine=='aarch64' else 'amd64'
    accelerated=False
    try:
        with open('/dev/kvm','rb') as kvm:
            vmfd=fcntl.ioctl(kvm,0xAE01,0)
            os.close(vmfd);accelerated=True
    except OSError:pass
    overlay=folder/'validation-overlay.qcow2'
    run(['qemu-img','create','-f','qcow2','-F','qcow2','-b',str(disk.resolve()),str(overlay)])
    run(['qemu-img','resize',str(overlay),'10G'])
    seed=folder/'seed.img';user=folder/'user-data';meta=folder/'meta-data'
    user.write_text('#cloud-config\nssh_pwauth: true\ndisable_root: false\n')
    meta.write_text('instance-id: hosted-'+uuid.uuid4().hex+'\nlocal-hostname: image-test\n')
    run(['cloud-localds',str(seed),str(user),str(meta)])
    serial=folder/'serial.log';sock=folder/'guest-agent.sock';monitor=folder/'monitor.sock'
    command=['qemu-system-aarch64' if arch=='arm64' else 'qemu-system-x86_64',
             '-machine','virt' if arch=='arm64' else 'q35','-accel','kvm' if accelerated else 'tcg,thread=multi',
             '-cpu','host' if accelerated else 'max','-m','2048','-smp','2',
             '-display','none','-serial',f'file:{serial}','-monitor',f'unix:{monitor},server=on,wait=off',
             '-drive',f'file={overlay},format=qcow2,if=virtio','-drive',f'file={seed},format=raw,if=virtio',
             '-netdev','user,id=net0','-device','virtio-net-pci,netdev=net0',
             '-device','virtio-serial-pci','-chardev',f'socket,path={sock},server=on,wait=off,id=qga',
             '-device','virtserialport,chardev=qga,name=org.qemu.guest_agent.0']+firmware(arch,folder)
    log=(folder/'qemu.log').open('wb');process=subprocess.Popen(command,stdout=log,stderr=log)
    def ready(previous=None, serial_offset=0):
        deadline=time.monotonic()+(1500 if not accelerated else 600)
        while time.monotonic()<deadline:
            if process.poll() is not None: raise RuntimeError('QEMU terminated before guest readiness')
            if console_only:
                if serial.exists():
                    with serial.open('rb') as output:
                        output.seek(serial_offset);text=output.read().decode(errors='replace')
                else: text=''
                if re.search(r'(?m)(login:|Please press Enter to activate this console|Welcome to .+Linux)',text):return 'console'
            else:
                try:
                    boot=qga_check(sock)
                    if boot and boot!=previous:return boot
                except (OSError,RuntimeError,TimeoutError,ValueError):pass
            time.sleep(5)
        if serial.exists():print(serial.read_text(errors='replace')[-12000:])
        print((folder/'qemu.log').read_text(errors='replace')[-3000:])
        raise RuntimeError('software or hardware VM readiness budget exhausted')
    try:
        boot=ready()
        if console_only:
            offset=serial.stat().st_size
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as stream:
                stream.settimeout(10);stream.connect(str(monitor));stream.recv(4096)
                stream.sendall(b'system_reset\n');stream.recv(4096)
            ready(serial_offset=offset)
            # Guest-agent-less ARM images can still prove kernel/rootfs boot on TCG.
            # This is explicitly recorded as console coverage, not SSH validation.
            print('Runtime validation: QEMU '+('KVM' if accelerated else 'TCG')+' kernel/rootfs console boot and reset passed; guest execution was not validated')
        else:
            qga_command(sock,'guest-shutdown',{'mode':'reboot'});time.sleep(15);ready(boot)
            print('Runtime validation: QEMU '+('KVM' if accelerated else 'TCG')+' guest agent, SSH listener, network and reboot passed')
    finally:
        process.terminate()
        try:process.wait(timeout=30)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()


def unpack(path, folder, runtime):
    if path.name.endswith('.qcow2'): return None,path
    if path.name.endswith('.zip'):
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:raise ValueError('corrupt image ZIP')
            expected=('lxd.tar.xz' if runtime=='lxd' else 'incus.tar.xz')
            paths={}
            for name in (expected,'rootfs.squashfs','disk.qcow2'):
                matches=[i for i in archive.infolist() if Path(i.filename).name==name and not i.is_dir()]
                if len(matches)>1:raise ValueError('ambiguous image member')
                if not matches:continue
                if not 0<matches[0].file_size<=2*1024**3:raise ValueError('invalid image member size')
                target=folder/name
                with archive.open(matches[0]) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst,1024**2)
                paths[name]=target
        if expected not in paths or not ({'rootfs.squashfs','disk.qcow2'}&paths.keys()):raise ValueError('incomplete image pair')
        return paths[expected],paths.get('disk.qcow2',paths.get('rootfs.squashfs'))
    if not path.name.endswith(('.tar.xz','.tar.zst')):raise ValueError('unknown image format')
    arch='aarch64' if os.uname().machine=='aarch64' else 'x86_64'
    metadata=folder/'metadata.tar.xz'
    value=f'architecture: {arch}\ncreation_date: {int(time.time())}\nproperties:\n  description: Hosted validation of public LXC rootfs\n'.encode()
    with tarfile.open(metadata,'w:xz') as archive:
        info=tarfile.TarInfo('metadata.yaml');info.size=len(value);archive.addfile(info,io.BytesIO(value))
    return metadata,path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--file',type=Path,required=True)
    parser.add_argument('--runtime',choices=['incus','lxd','qemu'],default='incus')
    args=parser.parse_args()
    if os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':raise RuntimeError('disposable hosted runner required')
    with tempfile.TemporaryDirectory(prefix='hosted-image-',dir=os.environ.get('RUNNER_TEMP')) as temporary:
        folder=Path(temporary);metadata,rootfs=unpack(args.file,folder,args.runtime)
        vm=rootfs.name.endswith('.qcow2')
        if args.runtime=='qemu' or (vm and not Path('/dev/kvm').exists()):
            qemu_test(folder,rootfs,console_only=metadata is not None)
        else:
            native_test(folder,metadata,rootfs,vm=vm,cli='/snap/bin/lxc' if args.runtime=='lxd' else 'incus')
    print('IMAGE_TEST_RESULT success=true image='+args.file.name)

if __name__=='__main__':main()
