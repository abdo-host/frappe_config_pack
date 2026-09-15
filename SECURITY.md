# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately to [abdo.host@gmail.com](mailto:abdo.host@gmail.com). Include a clear reproduction path, affected version, and impact when possible.

Do not open a public issue for an unpatched vulnerability.

## Security scope

Frappe Config Pack treats uploaded packages as untrusted input. It validates archive structure and payloads, does not execute package code while reading or inspecting, and requires explicit review before applying configuration changes.
