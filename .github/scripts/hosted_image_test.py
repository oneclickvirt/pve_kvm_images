#!/usr/bin/env python3
"""Boot public images on disposable hosted runners, with bounded software fallback."""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import re
import secrets
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
test -s /etc/os-release || test -s /usr/lib/os-release || test -s /etc/alpine-release || test -s /etc/openwrt_release || { echo 'Missing guest OS identity' >&2; exit 1; }
awk '$2 ~ /:0016$/ && $4 == "0A" {found=1} END {exit !found}' /proc/net/tcp /proc/net/tcp6 || { echo 'Guest SSH port 22 is not listening' >&2; exit 1; }
curl -fLsS --connect-timeout 10 --max-time 30 https://github.com -o /dev/null || { echo 'Guest HTTPS/DNS network check failed' >&2; exit 1; }
cat /proc/sys/kernel/random/boot_id
"""


def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=kwargs.pop('timeout', 120), **kwargs)


def kvm_available():
    try:
        with open('/dev/kvm','rb') as kvm:
            vmfd=fcntl.ioctl(kvm,0xAE01,0)
            os.close(vmfd)
        return True
    except OSError:return False


def native_test(folder, metadata, rootfs, vm=False, cli='incus'):
    alias='image-'+uuid.uuid4().hex[:12]; name='test-'+uuid.uuid4().hex[:12]
    prefix=['sudo', cli]
    def execute(script):
        result=run(prefix+['exec',name,'--','/bin/sh','-c',script],capture_output=True,text=True,timeout=50)
        return result.stdout.strip()
    def ready(previous=None):
        deadline=time.monotonic()+(600 if vm else 180)
        last_error='guest execution unavailable'
        while time.monotonic()<deadline:
            try:
                boot=execute(CHECK)
                if boot and boot!=previous: return boot
            except subprocess.CalledProcessError as error:
                last_error=(error.stderr or str(error))[-1500:]
            except (subprocess.SubprocessError,OSError) as error:
                last_error=type(error).__name__
            time.sleep(5)
        subprocess.run(prefix+['info',name,'--show-log'],timeout=30)
        print('Last guest readiness error: '+last_error)
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


def qga_command(sock, command, arguments=None, expect_response=True):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as stream:
        stream.settimeout(10);stream.connect(str(sock))
        identifier=uuid.uuid4().hex
        stream.sendall((json.dumps({'execute':command,'arguments':arguments or {},'id':identifier})+'\n').encode())
        # QGA guest-shutdown deliberately returns no response. Readiness after
        # the request proves the reboot; a missing response is not a timeout.
        if not expect_response:return None
        buffer=b''
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            stream.settimeout(max(0.001,deadline-time.monotonic()))
            chunk=stream.recv(65536)
            if not chunk:raise ConnectionError('guest agent disconnected before its response')
            buffer+=chunk
            if len(buffer)>1024*1024:raise ValueError('guest agent response exceeded size limit')
            while b'\n' in buffer:
                line,buffer=buffer.split(b'\n',1)
                if not line.strip():continue
                value=json.loads(line)
                if value.get('id')!=identifier:continue
                if 'error' in value:raise RuntimeError('guest agent rejected command: '+str(value['error'])[:500])
                if 'return' in value:return value['return']
        raise TimeoutError('guest agent response budget exhausted')


def qga_check(sock):
    response=qga_command(sock,'guest-exec',{'path':'/bin/sh','arg':['-c',CHECK],'capture-output':True})
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        value=qga_command(sock,'guest-exec-status',{'pid':response['pid']})
        if value.get('exited'):
            if value.get('exitcode')!=0:
                detail=base64.b64decode(value.get('err-data','')).decode(errors='replace')[-1500:]
                raise RuntimeError('guest runtime assertion failed: '+detail)
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


def ssh_command(port, key, script, password=None):
    command=['ssh','-p',str(port),'-i',str(key),'-o','IdentitiesOnly=yes',
             '-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null',
             '-o','ConnectTimeout=5','-o','ConnectionAttempts=1','-o','LogLevel=ERROR']
    environment=dict(os.environ)
    if password:
        # These are the documented public legacy image credentials. Never put
        # a password in a command line or include it in diagnostic output.
        environment['SSHPASS']=password
        command=['sshpass','-e']+command+['-o','PreferredAuthentications=password']
    else:command+=['-o','BatchMode=yes']
    result=run(command+['root@127.0.0.1',script],capture_output=True,text=True,env=environment,timeout=50)
    return result.stdout.strip()


def qemu_test(folder, disk, provision_key=False):
    arch='arm64' if os.uname().machine=='aarch64' else 'amd64'
    accelerated=kvm_available()
    overlay=folder/'validation-overlay.qcow2'
    run(['qemu-img','create','-f','qcow2','-F','qcow2','-b',str(disk.resolve()),str(overlay)])
    info=json.loads(run(['qemu-img','info','--output=json',str(disk)],capture_output=True,text=True).stdout)
    run(['qemu-img','resize',str(overlay),str(max(info['virtual-size'],10*1024**3))])
    key=folder/'test-key'
    run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],capture_output=True)
    public=key.with_suffix('.pub').read_text().strip()
    seed=folder/'seed.img';user=folder/'user-data';meta=folder/'meta-data';network=folder/'network-config'
    user.write_text('#cloud-config\nssh_pwauth: false\ndisable_root: false\nusers:\n  - default\n  - name: root\n    lock_passwd: false\n    ssh_authorized_keys:\n      - '+public+'\n')
    meta.write_text('instance-id: hosted-'+uuid.uuid4().hex+'\nlocal-hostname: image-test\n')
    network.write_text('version: 2\nethernets:\n  hosted:\n    match:\n      name: "e*"\n    dhcp4: true\n')
    run(['cloud-localds','--network-config='+str(network),str(seed),str(user),str(meta)])
    if provision_key:
        # Supply the consumer's login key on the disposable overlay. Do not
        # install packages, enable missing SSH/network services or change QGA
        # policy: the original image still has to provide those capabilities.
        try:
            run(['sudo','virt-customize','-a',str(overlay),'--ssh-inject','root:file:'+str(key.with_suffix('.pub')),
                 '--root-password','password:'+secrets.token_urlsafe(32),'--no-network'],capture_output=True,timeout=600,
                env=dict(os.environ,LIBGUESTFS_BACKEND='direct'))
        except subprocess.CalledProcessError:
            raise RuntimeError('consumer key provisioning failed on the disposable overlay') from None
    serial=folder/'serial.log';sock=folder/'guest-agent.sock';monitor=folder/'monitor.sock'
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    command=['qemu-system-aarch64' if arch=='arm64' else 'qemu-system-x86_64',
             '-machine','virt' if arch=='arm64' else 'q35','-accel','kvm' if accelerated else 'tcg,thread=multi',
             '-cpu','host' if accelerated else 'max','-m','2048','-smp','2',
             '-display','none','-serial',f'file:{serial}','-monitor',f'unix:{monitor},server=on,wait=off',
             '-drive',f'file={overlay},format=qcow2,if=virtio','-drive',f'file={seed},format=raw,if=virtio',
             '-netdev',f'user,id=net0,hostfwd=tcp:127.0.0.1:{port}-:22','-device','virtio-net-pci,netdev=net0',
             '-device','virtio-serial-pci','-chardev',f'socket,path={sock},server=on,wait=off,id=qga',
             '-device','virtserialport,chardev=qga,name=org.qemu.guest_agent.0']
    log=(folder/'qemu.log').open('wb');process=None;mode='UEFI';transport='QGA';ssh_password=None
    repository=os.environ.get('GITHUB_REPOSITORY','')
    legacy_password='oneclickvirt' if repository.endswith('/pve_kvm_images') else 'password' if repository.endswith('/kvm_images') else None
    def stop():
        if process is not None:
            process.terminate()
            try:process.wait(timeout=30)
            except subprocess.TimeoutExpired:process.kill();process.wait()
    def start(bios=False):
        nonlocal process,mode
        for path in [serial,sock,monitor]:path.unlink(missing_ok=True)
        mode='BIOS' if bios else 'UEFI'
        process=subprocess.Popen(command+([] if bios else firmware(arch,folder)),stdout=log,stderr=log)
    def ready(previous=None, allow_bios=False):
        nonlocal transport,ssh_password
        deadline=time.monotonic()+(1500 if not accelerated else 600)
        last_error='guest execution unavailable';agent_disabled=False
        began=time.monotonic()
        while time.monotonic()<deadline:
            if process.poll() is not None: raise RuntimeError('QEMU terminated before guest readiness')
            if not agent_disabled:
                try:
                    boot=qga_check(sock)
                    if boot and boot!=previous:transport='QGA';return boot
                except (OSError,RuntimeError,TimeoutError,ValueError) as error:
                    last_error=str(error)[-1500:]
                    agent_disabled='guest-exec' in last_error and ('disabled' in last_error or 'not found' in last_error)
            for password in [None]+([legacy_password] if legacy_password else []):
                try:
                    boot=ssh_command(port,key,CHECK,password)
                    if boot and boot!=previous:transport='SSH';ssh_password=password;return boot
                except subprocess.CalledProcessError as error:last_error=(error.stderr or str(error))[-1500:]
                except (subprocess.SubprocessError,OSError) as error:last_error=type(error).__name__
            # A confirmed firmware shell has no guest kernel. Retry once with
            # SeaBIOS on AMD64; keep the same guest assertions and overlay.
            if allow_bios and arch=='amd64' and time.monotonic()-began>45 and serial.exists():
                if 'UEFI Interactive Shell' in serial.read_text(errors='replace'):
                    print('UEFI has no boot entry; retrying the legacy image with SeaBIOS')
                    return None
            time.sleep(5)
        if serial.exists():print(serial.read_text(errors='replace')[-12000:])
        print((folder/'qemu.log').read_text(errors='replace')[-3000:])
        print('Last guest readiness error: '+last_error)
        raise RuntimeError('software or hardware VM readiness budget exhausted')
    try:
        start();boot=ready(allow_bios=True)
        if boot is None:
            stop();start(bios=True);boot=ready()
        if transport=='SSH':
            # reboot commonly disconnects SSH before returning a status.
            # The changed kernel boot_id is the success condition.
            try:ssh_command(port,key,'reboot',ssh_password)
            except subprocess.CalledProcessError as error:
                if error.returncode!=255:raise
        else:
            qga_command(sock,'guest-shutdown',{'mode':'reboot'},expect_response=False)
        time.sleep(15);ready(boot)
        print('Runtime validation: QEMU '+('KVM' if accelerated else 'TCG')+' '+mode+' '+transport+' guest execution, SSH listener, network and reboot passed')
    finally:
        stop()
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
    value=f'architecture: {arch}\ncreation_date: {int(time.time())}\nproperties:\n  description: Hosted validation of public LXC rootfs\n'
    templates={}
    if '_cloud.' in path.name:
        # Raw LXC/PVE rootfs has no Incus cloud-init template manifest. Supply
        # the NoCloud instance/network data a real consumer must provision.
        templates={'/var/lib/cloud/seed/nocloud-net/meta-data':('meta-data.tpl','instance-id: hosted-'+uuid.uuid4().hex+'\nlocal-hostname: image-test\n'),
                   '/var/lib/cloud/seed/nocloud-net/user-data':('user-data.tpl','#cloud-config\nssh_pwauth: true\ndisable_root: false\n'),
                   '/var/lib/cloud/seed/nocloud-net/network-config':('network-config.tpl','version: 2\nethernets:\n  eth0:\n    dhcp4: true\n')}
        value+='templates:\n'
        for target,(name,content) in templates.items():
            value+=f'  {target}:\n    when: [create]\n    template: {name}\n'
    elif path.name.endswith('.tar.zst') or os.environ.get('GITHUB_REPOSITORY')=='oneclickvirt/pve_lxc_images':
        # Proxmox templates intentionally contain static placeholder network
        # data. Proxmox replaces it when creating a guest. Apply the equivalent
        # DHCP provisioning on this disposable Incus test host.
        templates={'/etc/network/interfaces':('interfaces.tpl','auto lo\niface lo inet loopback\nauto eth0\niface eth0 inet dhcp\n'),
                   '/etc/sysconfig/network-scripts/ifcfg-eth0':('ifcfg.tpl','DEVICE=eth0\nBOOTPROTO=dhcp\nONBOOT=yes\nTYPE=Ethernet\n'),
                   '/etc/systemd/network/10-hosted-eth0.network':('network.tpl','[Match]\nName=eth0\n[Network]\nDHCP=yes\n')}
        value+='templates:\n'
        for target,(name,content) in templates.items():
            value+=f'  {target}:\n    when: [create]\n    template: {name}\n'
        print('Provisioning legacy Proxmox template network for the disposable test guest')
    value=value.encode()
    with tarfile.open(metadata,'w:xz') as archive:
        info=tarfile.TarInfo('metadata.yaml');info.size=len(value);archive.addfile(info,io.BytesIO(value))
        for name,content in templates.values():
            data=content.encode();info=tarfile.TarInfo('templates/'+name);info.size=len(data);archive.addfile(info,io.BytesIO(data))
    return metadata,path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--file',type=Path,required=True)
    parser.add_argument('--runtime',choices=['incus','lxd','qemu'],default='incus')
    args=parser.parse_args()
    if os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':raise RuntimeError('disposable hosted runner required')
    with tempfile.TemporaryDirectory(prefix='hosted-image-',dir=os.environ.get('RUNNER_TEMP')) as temporary:
        folder=Path(temporary);metadata,rootfs=unpack(args.file,folder,args.runtime)
        vm=rootfs.name.endswith('.qcow2')
        if args.runtime=='qemu' or (vm and not kvm_available()):
            qemu_test(folder,rootfs,provision_key=metadata is not None)
        else:
            native_test(folder,metadata,rootfs,vm=vm,cli='/snap/bin/lxc' if args.runtime=='lxd' else 'incus')
    print('IMAGE_TEST_RESULT success=true image='+args.file.name)

if __name__=='__main__':main()
