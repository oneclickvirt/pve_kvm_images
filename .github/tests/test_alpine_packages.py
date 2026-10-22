import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/install_alpine_packages.sh'


class AlpinePackagesTests(unittest.TestCase):
    def install(self, failures):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'apk').write_text('''#!/bin/sh
printf '%s\\n' "$1" >> "$CALLS"
if [ "$1" = add ]; then
    count=$(cat "$COUNT" 2>/dev/null || echo 0)
    count=$((count + 1))
    echo "$count" > "$COUNT"
    [ "$count" -gt "$FAILURES" ]
fi
''')
            (folder / 'sleep').write_text('#!/bin/sh\nexit 0\n')
            for name in ('apk', 'sleep'):
                (folder / name).chmod(0o755)
            calls = folder / 'calls'
            result = subprocess.run(['sh', str(SCRIPT)], capture_output=True, text=True,
                                    env=dict(os.environ, PATH=str(folder) + os.pathsep + os.environ['PATH'],
                                             CALLS=str(calls), COUNT=str(folder / 'count'), FAILURES=str(failures)),
                                    timeout=10)
            return result, calls.read_text().splitlines()

    def test_refreshes_index_after_a_replaced_package(self):
        result, calls = self.install(1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ['update', 'add', 'update', 'add'])

    def test_persistent_failure_stops_after_three_attempts(self):
        result, calls = self.install(3)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(calls, ['update', 'add'] * 3)


if __name__ == '__main__':
    unittest.main()
