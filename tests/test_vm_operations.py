"""Prevent VM shutdown from breaking a configured Gateway endpoint."""
import importlib.util
from pathlib import Path
import sys

import pytest


@pytest.fixture
def vm_control(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location('demo_vm_control_test', scripts / 'demo_vm.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'deployment_config', lambda: ('demo-project', 'us-east4-c', 'demo-vm', '8084'))
    monkeypatch.setenv('DEMO_PUBLIC_HOST', '192.0.2.10')
    return module


def running_vm():
    return {'status': 'RUNNING', 'selfLink': 'vm-reference', 'networkInterfaces': [
        {'accessConfigs': [{'natIP': '192.0.2.10'}]},
    ]}


def test_stop_refuses_temporary_ip_before_any_mutation(vm_control, monkeypatch):
    calls = []
    def cloud(project, *args):
        calls.append(args)
        return running_vm() if args[:3] == ('compute', 'instances', 'describe') else []
    monkeypatch.setattr(vm_control, 'cloud', cloud)
    monkeypatch.setattr(sys, 'argv', ['demo_vm.py', 'stop'])
    with pytest.raises(ValueError, match='temporary'):
        vm_control.main()
    assert all('stop' not in args for args in calls)


def test_stop_refuses_wrong_configured_host(vm_control, monkeypatch):
    monkeypatch.setenv('DEMO_PUBLIC_HOST', '192.0.2.11')
    monkeypatch.setattr(vm_control, 'cloud', lambda *args: pytest.fail('No cloud mutation should occur'))
    with pytest.raises(ValueError, match='does not resolve'):
        vm_control.check_address('demo-project', running_vm())


def test_stop_requires_confirmed_stopped_state(vm_control, monkeypatch):
    info = running_vm()
    def cloud(project, *args):
        if args[:3] == ('compute', 'addresses', 'list'):
            return [{'users': [info['selfLink']]}]
        return info
    monkeypatch.setattr(vm_control, 'cloud', cloud)
    monkeypatch.setattr(sys, 'argv', ['demo_vm.py', 'stop'])
    with pytest.raises(RuntimeError, match='not confirmed'):
        vm_control.main()


def test_start_checks_app_and_retained_usage(vm_control, monkeypatch, capsys):
    def respond(request):
        if request.url.path == '/api/health':
            return vm_control.httpx.Response(200, json={'app': 'SkillsCentral', 'redis': True, 'status': 'ok'})
        assert request.url.path == '/api/usage'
        return vm_control.httpx.Response(200, json={'history': {'retained_turns': 30}})
    client = vm_control.httpx.Client(transport=vm_control.httpx.MockTransport(respond))
    monkeypatch.setattr(vm_control.httpx, 'Client', lambda **kwargs: client)
    vm_control.wait_for_demo('192.0.2.10', '8084')
    assert '30 retained activity records' in capsys.readouterr().out
