# Security Policy

## Supported Versions

DreamCycle is currently alpha software. Security fixes target the newest
released minor version.

## Reporting a Vulnerability

Please report vulnerabilities privately to Kenny Jin at
`kenjix217@gmail.com`. Include the affected version, reproduction steps,
impact, and any suggested mitigation. Do not include live database credentials,
private model weights, or training data.

## Security Boundary

DreamCycle validates SQL identifiers, binds record values, scopes memory access,
and constrains adapter activation paths. Applications remain responsible for
database authentication, network policy, PostgreSQL role permissions, data
retention, encryption, backup, model licensing, and authorization to train on
stored content.

The sidecar binds to loopback by default. API keys map to server-owned memory
identities and are not forwarded to the upstream model. Operators exposing the
sidecar beyond a trusted host must add TLS, external access controls, rate
limits, credential rotation, and appropriate network isolation.
