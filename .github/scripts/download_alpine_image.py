#!/usr/bin/env python3
"""Fetch current cloud images, with a verified official Alpine fallback."""
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.extend(value for key, value in attrs if key == 'href' and value)


def read(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def candidates(version):
    base = f'https://images.linuxcontainers.org/images/alpine/{version}/amd64/cloud/'
    try:
        links = Links(read(base).decode()).links
    except (urllib.error.URLError, TimeoutError):
        links = []
    timestamps = sorted({s for s in links if re.fullmatch(r'\d{8}_\d{2}(?:%3A|:)\d{2}/', s)}, reverse=True)
    for stamp in timestamps[:10]:
        yield base + stamp.replace(':', '%3A') + 'disk.qcow2', None
    official = f'https://dl-cdn.alpinelinux.org/alpine/v{version}/releases/cloud/'
    links = Links(read(official).decode()).links
    pattern = re.compile(r'generic_alpine-' + re.escape(version) + r'\.(\d+)-x86_64-bios-cloudinit-r(\d+)\.qcow2')
    names = [(tuple(map(int, match.groups())), name) for name in links if (match := pattern.fullmatch(name))]
    for _, name in sorted(set(names), reverse=True)[:3]:
        yield official + name, official + name + '.sha512'


def main():
    version, destination = sys.argv[1:]
    if not re.fullmatch(r'3\.\d+', version):
        raise ValueError('invalid Alpine version')
    target = Path(destination)
    partial = target.with_suffix(target.suffix + '.partial')
    for url, checksum_url in candidates(version):
        try:
            print('Downloading cloud image:', url, flush=True)
            expected = None
            if checksum_url:
                checksum = read(checksum_url).decode().strip().split()[0]
                if not re.fullmatch('[0-9a-fA-F]{128}', checksum):
                    raise ValueError('invalid official checksum')
                expected = checksum.lower()
            digest = hashlib.sha512()
            with urllib.request.urlopen(url, timeout=60) as response, partial.open('wb') as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
                    digest.update(block)
            if partial.stat().st_size <= 10 * 1024 * 1024:
                raise ValueError('cloud image is too small')
            with partial.open('rb') as image:
                if image.read(4) != b'QFI\xfb':
                    raise ValueError('download is not QCOW2')
            if expected and digest.hexdigest() != expected:
                raise ValueError('official SHA512 mismatch')
            partial.replace(target)
            print('Cloud image downloaded' + ('; official SHA512 verified' if expected else ''), flush=True)
            return 0
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print('Cloud image candidate failed:', type(exc).__name__, file=sys.stderr)
            partial.unlink(missing_ok=True)
    print('No verified Alpine cloud image is available', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
