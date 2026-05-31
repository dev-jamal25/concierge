# Future Improvements

Confirmed security or reliability concerns deferred from the current release.
Each item includes the evidence files so a future implementer can locate the
exact code without re-auditing.

---

## 1. SESSION_SECRET — boot-time guard for production

**Risk:** `config.py:80` defaults `session_secret` to `"change-me-in-prod"`.
`docker-compose.yml:85` passes `${SESSION_SECRET:-change-me-in-prod}` to the
container. `session_auth.py:59/65` signs and verifies HS256 admin JWTs with
this value. Anyone who knows the default (or guesses it) can forge a valid
admin token.

**Recommended fix:**
1. Add `ENVIRONMENT: Literal["development","staging","production"] = "development"`
   to `Settings` in `config.py`.
2. Add a `model_validator(mode="after")` that raises `ValueError` when
   `environment in {"staging","production"}` and `session_secret` is the
   sentinel / empty / shorter than 32 characters.
3. No change needed to `docker-compose.yml` dev defaults or CI `SESSION_SECRET`
   values — they are not production environments.

**Impact when implemented:** prod/staging containers fail at startup rather than
silently accepting the weak key; dev/demo/CI are unaffected.

---

## 2. Service-token fail-open (modelserver + guardrails)

**Risk:** `services/modelserver/app.py` and `services/guardrails/app.py` both
contain:
```python
def _require_service_token(x_service_token: str | None) -> None:
    if not SERVICE_TOKEN:
        return          # auth disabled when token unset
```
Any container started without `SERVICE_TOKEN` in the environment (or when Vault
is unreachable and the env var is absent) accepts unauthenticated requests.

**Recommended fix:** Fail at startup rather than fail-open at request time:
raise `RuntimeError` in the startup handler when `SERVICE_TOKEN` is still
empty after the Vault fetch attempt.

---

## 3. Raw PII reaches classifier and Redis session memory before redaction

**Risk:** `chat.py:270` passes the raw visitor message to
`ClassifyMessageUseCase.execute`, and `session_memory.py:58` stores the raw
user message verbatim in Redis. The `PIIRedactionMiddleware` in
`pii_redaction.py:72-73` is pass-through (it only wires log/trace regex
redactors) — it does not intercept request bodies before they reach these paths.

**Recommended fix:** Run the `RedactionService` (or at minimum the sync
`regex_redactor`) on `body.message` in `chat.py` before the classify call and
before the `memory.append_turn` call. Owner C owns the full guardrails-backed
path; Owner B owns the session store write.
