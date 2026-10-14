#!/usr/bin/env python3
"""Build a bounded test matrix from real published assets and verify downloads."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from release_assets import Publisher


def published(publisher):
    releases=[]
    for page in range(1,21):
        batch=publisher.request(publisher.base+f'/releases?per_page=100&page={page}')
        releases.extend(batch)
        if len(batch)<100:break
    else:raise RuntimeError('release pagination exceeded')
    assets={}
    for release in releases:
        if release['draft'] or release['prerelease'] or release['tag_name']=='processed':continue
        for asset in publisher.assets(release['id']).values():
            name=asset['name']
            if asset.get('state')!='uploaded' or not asset.get('size') or not re.fullmatch(r'[A-Za-z0-9_.-]+\.(qcow2|zip|tar\.xz|tar\.zst)',name):continue
            old=assets.get(name)
            if old is None or asset['updated_at']>old['updated_at']:
                assets[name]=dict(asset,tag=release['tag_name'])
    return list(assets.values())


def matrix(assets,repo,scope,kind):
    rows=[]
    if scope not in ('smoke','full'):raise ValueError('invalid suite scope')
    for asset in sorted(assets,key=lambda a:a['name']):
        name=asset['name'];vm=name.endswith('.qcow2') or name.endswith('_kvm.zip')
        if (kind=='vm')!=vm:continue
        arch='arm64' if re.search(r'_(arm64|aarch64)_',name) else 'amd64'
        if repo=='lxc_amd64_images' and arch!='amd64':continue
        if repo=='lxc_arm_images' and arch!='arm64':continue
        if scope=='smoke':
            if name.endswith('.qcow2'):
                if not re.fullmatch(r'debian(12|13)\.qcow2',name):continue
            elif not re.search(r'^(debian_(12_bookworm|13_trixie)|alpine_3\.24_3\.24)_',name):continue
            elif '_cloud.' in name:continue
        rows.append({'image':name,'tag':asset['tag'],'arch':arch,'runner':'ubuntu-24.04-arm' if arch=='arm64' else 'ubuntu-24.04'})
    if not rows:raise ValueError('no published images selected')
    if len(rows)>256:raise ValueError('suite exceeds GitHub matrix limit; select a smaller catalog')
    return {'include':rows}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['matrix','download'])
    parser.add_argument('--scope',choices=['smoke','full'],default='smoke');parser.add_argument('--kind',choices=['container','vm'],default='container')
    args=parser.parse_args();repo=os.environ['GITHUB_REPOSITORY']
    publisher=Publisher(repo,os.environ['GH_TOKEN'])
    if args.command=='matrix':
        value=matrix(published(publisher),repo.split('/')[-1],args.scope,args.kind)
        encoded=json.dumps(value,separators=(',',':'))
        with open(os.environ['GITHUB_OUTPUT'],'a') as stream:print('matrix='+encoded,file=stream)
        print('Published image test jobs:',len(value['include']))
    else:
        name=os.environ['IMAGE'];tag=os.environ['TAG']
        release=publisher.ensure_release(tag);asset=publisher.assets(release['id']).get(name)
        if not asset or asset.get('state')!='uploaded':raise RuntimeError('expected release asset is unavailable')
        if Path(name).name!=name or not re.fullmatch(r'[A-Za-z0-9_.-]+\.(qcow2|zip|tar\.xz|tar\.zst)',name):raise ValueError('unsafe asset path')
        path=Path(name);temp=Path(name+'.partial')
        subprocess.run(['curl','--fail','--location','--connect-timeout','15','--max-time','900','--retry','3',
                        '--retry-max-time','180','-o',str(temp),asset['browser_download_url']],check=True,timeout=1200)
        if temp.stat().st_size!=asset['size']:raise ValueError('asset size mismatch')
        if asset.get('digest') and asset['digest']!='sha256:'+publisher.digest(temp):raise ValueError('asset checksum mismatch')
        temp.rename(path)

if __name__=='__main__':main()
