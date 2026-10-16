"""Inspect only an overlay of a size/SHA256-verified public release asset."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from hosted_image_test import guestfs_command,isolated_environment
from native_pve_smoke import download,digest,select_assets

with tempfile.TemporaryDirectory(prefix='pve-initramfs-inspect-',dir=os.environ['RUNNER_TEMP']) as temporary:
    folder=Path(temporary)
    asset=select_assets(os.environ['GH_TOKEN'],'vm')[0]
    source=folder/asset['name']
    download(asset['browser_download_url'],source)
    assert source.stat().st_size==asset['size'] and 'sha256:'+digest(source,'sha256')==asset['digest']
    print('PVE_INITRAMFS_DIAGNOSTIC_INPUT '+json.dumps({k:asset[k] for k in ('id','name','size','digest')}),flush=True)
    overlay=folder/'inspection-overlay.qcow2'
    subprocess.run(['qemu-img','create','-f','qcow2','-F','qcow2','-b',str(source),str(overlay)],
                   check=True,timeout=30,env=isolated_environment())
    def cat(path):
        return subprocess.run(guestfs_command('virt-cat',False)+['-a',str(overlay),path],
                              check=True,capture_output=True,timeout=600,env=isolated_environment()).stdout
    status=cat('/var/lib/dpkg/status').decode()
    versions={}
    for paragraph in status.split('\n\n'):
        fields=dict(line.split(': ',1) for line in paragraph.splitlines() if ': ' in line and not line.startswith(' '))
        if fields.get('Package') in ('udev','systemd','initramfs-tools','initramfs-tools-core','klibc-utils'):
            versions[fields['Package']]=fields.get('Version')
    print('PVE_INITRAMFS_DIAGNOSTIC_PACKAGES '+json.dumps(versions),flush=True)
    assert {'udev','initramfs-tools-core','klibc-utils'}<=versions.keys()
    text=cat('/usr/share/initramfs-tools/scripts/init-bottom/udev').decode()
    print('PVE_INITRAMFS_INSTALLED_UDEV_BEGIN\n'+text+'\nPVE_INITRAMFS_INSTALLED_UDEV_END',flush=True)
    listing=subprocess.run(guestfs_command('virt-ls',False)+['-a',str(overlay),'/boot'],
                           check=True,capture_output=True,text=True,timeout=600,env=isolated_environment()).stdout
    names=sorted(name for name in listing.splitlines() if name.startswith('initrd.img-') and '/' not in name)
    assert names,'Published image has no initrd in /boot'
    for index,name in enumerate(names):
        initrd=folder/('initrd-'+str(index))
        initrd.write_bytes(cat('/boot/'+name))
        destination=folder/('unpacked-'+str(index))
        subprocess.run(['unmkinitramfs',str(initrd),str(destination)],check=True,timeout=120,env=isolated_environment())
        candidates=list(destination.glob('**/scripts/init-bottom/udev'))
        assert len(candidates)==1
        embedded=candidates[0].read_text()
        print('PVE_INITRAMFS_EMBEDDED_UDEV_BEGIN '+name+'\n'+embedded+'\nPVE_INITRAMFS_EMBEDDED_UDEV_END',flush=True)
        assert '#!/bin/sh -e' in embedded and 'udevadm control --exit' in embedded
        assert embedded.index('udevadm control --exit')<embedded.index('mount -n -o move /dev')
        inits=list(destination.glob('**/init'))
        inits=[p for p in inits if p.is_file() and 'validate_init()' in p.read_text(errors='replace')]
        assert len(inits)==1
        init=inits[0].read_text()
        start=init.index('validate_init()')
        end=init.index('maybe_break init',start)
        print('PVE_INITRAMFS_INIT_CHECK_BEGIN\n'+init[start:end]+'\nPVE_INITRAMFS_INIT_CHECK_END',flush=True)
        print('PVE_INITRAMFS_DIAGNOSTIC_RESULT '+json.dumps({'initrd':name,'size':initrd.stat().st_size,
              'sha256':hashlib.sha256(initrd.read_bytes()).hexdigest(),
              'embedded_udev_sha256':hashlib.sha256(candidates[0].read_bytes()).hexdigest(),
              'installed_equals_embedded':embedded==text,'exit_before_dev_move':True,'success':True}),flush=True)
    assert source.stat().st_size==asset['size'] and 'sha256:'+digest(source,'sha256')==asset['digest']
    print('PVE_INITRAMFS_DIAGNOSTIC_COMPLETE read_only=true libguestfs=tcg success=true',flush=True)
