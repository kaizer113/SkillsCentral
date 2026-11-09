"""Stop the shared VM, or resume it and verify the existing demo."""
import argparse
import json
import os
import socket
import subprocess
import sys
import time

import httpx

from deployment_config import deployment_config


def cloud(project, *args):
    result = subprocess.run(
        ['gcloud', *args, '--project', project, '--quiet', '--format=json'],
        text=True, capture_output=True, check=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def check_address(project, info):
    """Refuse shutdown if it could release the endpoint used by the Gateway."""
    addresses = [access['natIP'] for nic in info.get('networkInterfaces', [])
                 for access in nic.get('accessConfigs', []) if access.get('natIP')]
    expected = os.getenv('DEMO_PUBLIC_HOST', '')
    if not expected or socket.gethostbyname(expected) not in addresses:
        raise ValueError('DEMO_PUBLIC_HOST does not resolve to the VM address. Check the private configuration before continuing.')
    for ip in addresses:
        reserved = cloud(project, 'compute', 'addresses', 'list', '--filter', f'address={ip}')
        if not any(info['selfLink'] in address.get('users', []) for address in reserved):
            raise ValueError('The VM public address is temporary. Reserve its existing address with the required owner and skip_deletion labels before stopping it.')
    return expected


def wait_for_demo(host, port, timeout=120):
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=5, trust_env=False) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(f'http://{host}:{port}/api/health')
                response.raise_for_status()
                health = response.json()
                if health.get('app') == 'SkillsCentral' and health.get('redis') is True and health.get('status') == 'ok':
                    usage = client.get(f'http://{host}:{port}/api/usage')
                    usage.raise_for_status()
                    turns = usage.json()['history']['retained_turns']
                    print(f'Demo and Redis are healthy; {turns} retained activity records.')
                    print(f'Open http://{host}:{port}')
                    return
            except (httpx.HTTPError, ValueError, KeyError):
                pass
            time.sleep(2)
    raise RuntimeError('The VM is running, but the demo did not become healthy. Inspect it with scripts/demo-service.sh status and logs.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status'])
    action = parser.parse_args().action
    project, zone, instance, port = deployment_config()
    info = cloud(project, 'compute', 'instances', 'describe', instance, '--zone', zone)
    state = info['status']
    if action == 'status':
        print(f'VM: {"stopped" if state == "TERMINATED" else state.lower()}')
        return
    if action == 'stop' and state == 'TERMINATED':
        print('VM is already stopped.')
        return
    if state not in ('RUNNING', 'TERMINATED'):
        raise ValueError(f'The VM is currently {state.lower()}; wait for that operation to finish.')
    host = check_address(project, info)
    if action == 'stop':
        # Leave running containers enabled so Docker resumes them at the next boot.
        cloud(project, 'compute', 'instances', 'stop', instance, '--zone', zone)
        stopped = cloud(project, 'compute', 'instances', 'describe', instance, '--zone', zone)
        if stopped['status'] != 'TERMINATED':
            raise RuntimeError('Compute Engine has not confirmed that the VM is stopped.')
        print('VM stopped. Its disk, reserved address, configuration, and Redis history are preserved.')
        return
    if state == 'TERMINATED':
        print('Starting the shared VM...', flush=True)
        cloud(project, 'compute', 'instances', 'start', instance, '--zone', zone)
    # Normal boot uses Docker's restart policy and needs no SSH connection.
    try:
        wait_for_demo(host, port, timeout=30)
        return
    except RuntimeError:
        pass
    # Explicitly start only this app, including if someone previously stopped it.
    for attempt in range(12):
        try:
            subprocess.run(
                ['gcloud', 'compute', 'ssh', instance, '--project', project, '--zone', zone,
                 '--quiet', '--ssh-flag=-oConnectTimeout=10', '--command', 'sudo docker start skillscentral'],
                capture_output=True, text=True, check=True, timeout=30,
            )
            break
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if attempt == 11:
                raise RuntimeError('The VM started, but the existing app container could not be started. Inspect the VM and scripts/demo-service.sh status.')
            time.sleep(3)
    wait_for_demo(host, port)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        print(detail, file=sys.stderr)
        raise SystemExit(1)
