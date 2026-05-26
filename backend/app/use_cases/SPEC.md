# use_cases — SPEC (stub — Owner A, T059)

To be populated (T162). Covers tenant provisioning / erasure / invitation /
authentication flows and the use-case ↔ protocol contracts.

Protocols published by Owner A (the cross-slice seam):
- `protocols/tenant_repository.py` (T019)
- `protocols/user_repository.py` (T020)
- `protocols/audit_repository.py` (T021)
- `protocols/vault_client.py` (T032)

Use cases (Owner A): `provision_tenant`, `invite_admin`, `erase_tenant`.
