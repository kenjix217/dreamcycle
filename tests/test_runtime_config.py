import pytest

from dreamcycle.errors import ConfigurationError
from dreamcycle.server.auth import ClientIdentity
from dreamcycle.server.proxy import ProxyMode
from dreamcycle.server.runtime import SidecarSettings
from dreamcycle.types import DistanceMetric


def base_env():
    return {
        "DREAMCYCLE_POSTGRES_DSN": "postgresql://user:secret@localhost/dreamcycle",
        "DREAMCYCLE_EMBEDDING_MODEL": "/models/embedding",
        "DREAMCYCLE_API_KEY": "sidecar-secret",
        "DREAMCYCLE_NAMESPACE": "vendor",
        "DREAMCYCLE_USER_ID": "local-user",
    }


def test_settings_parse_without_exposing_credentials():
    env = {
        **base_env(),
        "DREAMCYCLE_DISTANCE_METRIC": "l2",
        "DREAMCYCLE_PROXY_MODE": "retrieve",
        "DREAMCYCLE_UPSTREAM_API_KEY": "upstream-secret",
    }
    settings = SidecarSettings.from_env(env)

    assert settings.distance_metric is DistanceMetric.L2
    assert settings.proxy_mode is ProxyMode.RETRIEVE
    assert settings.api_keys["sidecar-secret"] == ClientIdentity("vendor", "local-user")
    assert "sidecar-secret" not in repr(settings)
    assert "upstream-secret" not in repr(settings)
    assert "user:secret" not in repr(settings)


def test_settings_accept_multiple_server_bound_identities():
    env = base_env()
    env.pop("DREAMCYCLE_API_KEY")
    env.pop("DREAMCYCLE_NAMESPACE")
    env.pop("DREAMCYCLE_USER_ID")
    env["DREAMCYCLE_API_KEYS_JSON"] = (
        '{"key-a":{"namespace":"vendor","user_id":"a"},'
        '"key-b":{"namespace":"vendor","user_id":"b"}}'
    )

    settings = SidecarSettings.from_env(env)
    assert set(settings.api_keys.values()) == {
        ClientIdentity("vendor", "a"),
        ClientIdentity("vendor", "b"),
    }


def test_settings_reject_ambiguous_keys_and_partial_training_configuration():
    ambiguous = {**base_env(), "DREAMCYCLE_API_KEYS_JSON": "{}"}
    with pytest.raises(ConfigurationError, match="not both"):
        SidecarSettings.from_env(ambiguous)

    partial = {**base_env(), "DREAMCYCLE_BASE_MODEL": "/models/base"}
    with pytest.raises(ConfigurationError, match="configured together"):
        SidecarSettings.from_env(partial)


def test_client_identity_is_normalized_before_it_becomes_a_scope():
    assert ClientIdentity(" vendor ", " user ") == ClientIdentity("vendor", "user")
