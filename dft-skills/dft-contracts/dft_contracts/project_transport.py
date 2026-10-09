"""Small SSH/file transport. The same stdlib worker runs locally in integration tests."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def safe(root, relative):
    root = Path(root).expanduser().absolute()
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Expected a relative path without traversal')
    target = root / relative
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError('Transfer paths must not contain symlinks')
    target.resolve().relative_to(root.resolve())
    return target


def info(path):
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise ValueError('Expected a regular file')
    return {'sha256': digest(path), 'size': path.stat().st_size}


def worker(root, operation, relative, expected='', wanted='', guards='{}'):
    target = safe(root, relative)
    if operation == 'stat':
        print(json.dumps(info(target)))
    elif operation == 'get':
        if info(target) is None:
            raise ValueError('Source file missing')
        with target.open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                sys.stdout.buffer.write(block)
    elif operation == 'put':
        before = info(target)
        actual = before['sha256'] if before else ''
        if actual not in {expected, wanted}:
            raise ValueError('Destination conflict; contents preserved')
        target.parent.mkdir(parents=True, exist_ok=True)
        # ponytail: one file per SSH transaction; batch only if connection latency matters.
        fd, name = tempfile.mkstemp(prefix='.dft-transfer-', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as output:
                for block in iter(lambda: sys.stdin.buffer.read(1024 * 1024), b''):
                    output.write(block)
            if digest(name) != wanted:
                raise ValueError('Transfer checksum mismatch')
            import fcntl
            lock = safe(root, '.dft/records.lock')
            lock.parent.mkdir(parents=True, exist_ok=True)
            with lock.open('a') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                for guard_name, sha in json.loads(guards).items():
                    checked = info(safe(root, guard_name))
                    if (checked['sha256'] if checked else None) != sha:
                        raise ValueError('Related record changed during review')
                now = info(target)
                if (now['sha256'] if now else '') not in {expected, wanted}:
                    raise ValueError('Destination changed during transfer')
                if not now or now['sha256'] != wanted:
                    os.replace(name, target)
            print(json.dumps(info(target)))
        finally:
            if os.path.exists(name):
                os.unlink(name)
    elif operation == 'dirs':
        print(json.dumps(sorted(p.name for p in target.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith('.')) if target.is_dir() else []))
    elif operation == 'workflows':
        # Inspect ledgers, not wavefunctions or arbitrary file contents.
        paths = []
        if target.exists():
            for folder, dirs, files in os.walk(target, followlinks=False):
                dirs[:] = sorted(d for d in dirs if d not in {'attempts', 'tmp', 'software', 'shared', 'scripts', 'docs', 'data', 'figures'}
                                 and not d.startswith('.') and not d.endswith('.save')
                                 and not (Path(folder) / d).is_symlink())
                if 'workflow.json' in files:
                    path = safe(root, (Path(folder) / 'workflow.json').relative_to(root))
                    paths.append(path.relative_to(root).as_posix())
        print(json.dumps(paths))
    else:
        raise ValueError('Unknown transport operation')


class Endpoint:
    """An explicit project root, either mounted locally or reached through an SSH alias."""

    def __init__(self, root, ssh=None):
        if not Path(root).is_absolute():
            raise ValueError('Endpoint root must be absolute')
        if ssh is not None and (not isinstance(ssh, str) or not ssh or ssh.startswith('-')
                                or any(c.isspace() for c in ssh)):
            raise ValueError('Use an SSH host alias without options')
        self.root, self.ssh = str(root), ssh

    def command(self, operation, relative, expected='', wanted='', guards=None):
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Unsafe transfer path')
        args = [self.root, operation, str(relative), expected, wanted, json.dumps(guards or {})]
        if self.ssh:
            program = Path(__file__).read_text()
            return ['ssh', '-oBatchMode=yes', '-oConnectTimeout=15', self.ssh,
                    shlex.join(['python3', '-c', program, *args])]
        return [sys.executable, str(Path(__file__).resolve()), *args]

    def _run(self, operation, relative, *, source=None, expected='', wanted=''):
        result = subprocess.run(self.command(operation, relative, expected, wanted), stdin=source,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if result.returncode:
            # Do not echo remote paths, commands, banners or credential-bearing stderr.
            raise RuntimeError(f'{operation} failed: connection, path, checksum or destination conflict; retry after inspection')
        return result.stdout

    def stat(self, relative):
        return json.loads(self._run('stat', relative))

    def read(self, relative, *, optional=False):
        metadata = self.stat(relative)
        if metadata is None:
            if optional:
                return None
            raise ValueError('Remote record missing')
        if metadata['size'] > 16 * 1024 * 1024:
            raise ValueError('Record too large; use streaming transfer')
        content = self._run('get', relative)
        if hashlib.sha256(content).hexdigest() != metadata['sha256']:
            raise ValueError('Record changed while reading')
        return content

    def json(self, relative, default=None):
        content = self.read(relative, optional=True)
        return default if content is None else json.loads(content)

    def put(self, relative, source, *, expected=None, guards=None):
        wanted = digest(source)
        if not guards and self.stat(relative) == {'sha256': wanted, 'size': Path(source).stat().st_size}:
            return wanted
        with Path(source).open('rb') as stream:
            result = subprocess.run(self.command('put', relative, expected or '', wanted, guards), stdin=stream,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1800)
        if result.returncode:
            raise RuntimeError('Upload incomplete or conflicting; verified files may be reused on retry')
        if json.loads(result.stdout)['sha256'] != wanted:
            raise ValueError('Upload verification failed')
        return wanted

    def write(self, relative, content, *, expected=None, guards=None):
        with tempfile.TemporaryDirectory(prefix='dft-record-') as temporary:
            path = Path(temporary) / 'record'
            path.write_bytes(content)
            return self.put(relative, path, expected=expected, guards=guards)

    def fetch(self, relative, destination, metadata, *, expected=None):
        destination = Path(destination)
        current = info(destination)
        if current and current['sha256'] == metadata['sha256']:
            return
        if (current['sha256'] if current else None) != expected:
            raise ValueError('Local copy was edited; reconcile before downloading')
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.dft-download-', dir=destination.parent)
        try:
            with os.fdopen(fd, 'wb') as output:
                result = subprocess.run(self.command('get', relative), stdout=output,
                                        stderr=subprocess.PIPE, timeout=1800)
            if result.returncode or info(Path(name)) != metadata:
                raise RuntimeError('Download incomplete or source changed; destination preserved')
            current = info(destination)
            if (current['sha256'] if current else None) != expected:
                raise ValueError('Local copy changed during download')
            os.replace(name, destination)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def dirs(self, relative):
        return json.loads(self._run('dirs', relative))

    def workflows(self, route):
        return json.loads(self._run('workflows', route))


if __name__ == '__main__':
    try:
        worker(*sys.argv[1:])
    except (ValueError, OSError) as error:
        print(type(error).__name__, file=sys.stderr)
        sys.exit(1)
