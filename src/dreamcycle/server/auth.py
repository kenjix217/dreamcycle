"""Bearer-key authentication with server-owned memory identity binding."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass

from dreamcycle.errors import ConfigurationError


@dataclass(frozen=True, order=True)
class ClientIdentity:
    namespace: str
    user_id: str

    def __post_init__(self) -> None:
        namespace = self.namespace.strip()
        user_id = self.user_id.strip()
        if not namespace:
            raise ConfigurationError("client namespace is required")
        if not user_id:
            raise ConfigurationError("client user_id is required")
        object.__setattr__(self, "namespace", namespace)
        object.__setattr__(self, "user_id", user_id)


class AuthenticationError(Exception):
    """Raised when a sidecar credential is absent or invalid."""


class APIKeyAuthenticator:
    def __init__(self, bindings: Mapping[str, ClientIdentity]) -> None:
        if not bindings:
            raise ConfigurationError("at least one DreamCycle API key is required")
        if any(not key for key in bindings):
            raise ConfigurationError("DreamCycle API keys cannot be empty")
        self._bindings = tuple(bindings.items())

    @property
    def identities(self) -> tuple[ClientIdentity, ...]:
        return tuple(sorted({identity for _, identity in self._bindings}))

    def authenticate(self, authorization: str | None) -> ClientIdentity:
        scheme, separator, supplied = (authorization or "").partition(" ")
        if not separator or scheme.lower() != "bearer" or not supplied:
            raise AuthenticationError("a valid bearer API key is required")
        matched: ClientIdentity | None = None
        for expected, identity in self._bindings:
            if hmac.compare_digest(supplied, expected):
                matched = identity
        if matched is None:
            raise AuthenticationError("a valid bearer API key is required")
        return matched

    def __repr__(self) -> str:
        return f"APIKeyAuthenticator(bindings={len(self._bindings)})"
