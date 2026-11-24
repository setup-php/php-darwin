"""Register a disposable, native macOS VM for one php-darwin job."""
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import tempfile

from managed_runner import serve_job
from runner_pool import child_environment, download_runner

PROFILES = {
    'intel15': ('x86_64', '15', 'macos-15-intel'),
    'intel26': ('x86_64', '26', 'macos-26-intel'),
    'arm15': ('arm64', '15', 'macos-15'),
    'arm26': ('arm64', '26', 'macos-26'),
}

def interrupt(*_):
    raise InterruptedError('Runner host interrupted')

def main():
    os.umask(0o077)
    key = os.environ.pop('PROFILE')
    machine, major, label = PROFILES[key]
    name = os.environ.pop('POOL')
    token = os.environ.pop('RUNNER_REGISTRATION_TOKEN')
    if not re.fullmatch(r'darwin-' + key + r'-[0-9a-f]{16}', name) or not re.fullmatch(r'[A-Za-z0-9_]+', token):
        raise ValueError('Invalid pool registration')
    version = platform.mac_ver()[0]
    if platform.system() != 'Darwin' or platform.machine() != machine or version.split('.')[0] != major:
        raise RuntimeError(f'Unexpected host: {platform.machine()}, macOS {version}')
    arch = 'x64' if machine == 'x86_64' else 'arm64'
    env = child_environment(os.environ)
    directory = Path(tempfile.mkdtemp(prefix='darwin-runner-', dir=os.environ['RUNNER_TEMP']))
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    try:
        # Both native macOS releases use the same checksum-pinned runner binary.
        download_runner(directory, arch, 'macos-15')
        with (directory / 'host.log').open('wb') as log:
            registration = subprocess.run(['./config.sh', '--unattended', '--ephemeral', '--url',
                            'https://github.com/shivammathur/php-darwin', '--name', name,
                            '--token', token, '--work', '_work', '--no-default-labels',
                            '--labels', ','.join(['self-hosted', 'macOS', arch.upper(), label])],
                           cwd=directory, env=env, stdout=log, stderr=log, timeout=120, check=False)
            if registration.returncode:
                raise RuntimeError(f'Runner registration failed with code {registration.returncode}')
            del registration, token
            print(f'Registered {name} on macOS {version} {machine} for {label}', flush=True)
            serve_job(directory, env, log)
    finally:
        subprocess.run(['sudo', 'rm', '-rf', '--', str(directory)], check=True)

if __name__ == '__main__':
    main()
