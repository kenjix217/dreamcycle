import json

from dreamcycle.hermes.cli import main
from dreamcycle.hermes.commands import HermesDreamCycleCommands, RollbackConfirmationRequired
from dreamcycle.sdk.models import AdapterState


class FakeClient:
    def __init__(self):
        self.rollback_calls = 0

    def active_adapter(self):
        return AdapterState(available=True, active_path="/models/current")

    def rollback_adapter(self):
        self.rollback_calls += 1
        return AdapterState(
            available=True,
            active_path="/models/previous",
            accepted=True,
            reason="previous adapter restored",
            previous_path="/models/current",
        )


class FakeClientContext:
    def __init__(self, client):
        self.client = client

    def __enter__(self):
        return self.client

    def __exit__(self, *args):
        return None


def test_hermes_status_reports_active_adapter():
    result = HermesDreamCycleCommands(FakeClient()).status()

    assert result.ok is True
    assert result.available is True
    assert result.active_path == "/models/current"
    assert "Active DreamCycle adapter" in result.message
    assert json.loads(json.dumps(result.to_dict()))["active_path"] == "/models/current"


def test_hermes_rollback_requires_confirmation_without_calling_backend():
    client = FakeClient()
    commands = HermesDreamCycleCommands(client)

    try:
        commands.rollback()
    except RollbackConfirmationRequired as exc:
        assert "requires explicit confirmation" in str(exc)
    else:
        raise AssertionError("rollback without confirmation should fail")

    assert client.rollback_calls == 0


def test_hermes_rollback_calls_backend_after_confirmation():
    client = FakeClient()
    result = HermesDreamCycleCommands(client).rollback(confirm=True)

    assert client.rollback_calls == 1
    assert result.ok is True
    assert result.accepted is True
    assert result.active_path == "/models/previous"
    assert result.previous_path == "/models/current"


def test_cli_refuses_rollback_without_confirmation(capsys):
    client = FakeClient()

    exit_code = main(
        ["--api-key", "key", "--json", "rollback"],
        client_factory=lambda *_args: FakeClientContext(client),
    )

    assert exit_code == 2
    assert client.rollback_calls == 0
    payload = json.loads(capsys.readouterr().err)
    assert payload["confirmation_required"] is True


def test_cli_status_uses_injected_client(capsys):
    exit_code = main(
        ["--api-key", "key", "--json", "status"],
        client_factory=lambda *_args: FakeClientContext(FakeClient()),
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["active_path"] == "/models/current"
