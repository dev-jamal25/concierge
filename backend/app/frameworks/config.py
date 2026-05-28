"""Typed application settings (T011 — minimal [ALL] stub).

Reads from environment / .env. Secrets that live in Vault (e.g. the widget
JWT signing key) are fetched at runtime via the VaultClient, not here.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Postgres — three role-scoped DSNs (RLS only applies to non-superuser roles).
    # App role: bound by RLS. This is what request handlers use.
    database_url: str = Field(
        default="postgresql+asyncpg://concierge_app:concierge_app@localhost:5432/concierge",
        description="Async SQLAlchemy DSN bound to the concierge_app role (RLS-enforced).",
    )
    # Manager role: elevated reads on tenants + audit_entries + provisioning tables only.
    manager_database_url: str | None = Field(
        default="postgresql+asyncpg://concierge_manager:concierge_manager@localhost:5432/concierge",
        description="Async DSN bound to the concierge_manager Postgres role; "
        "falls back to database_url when unset.",
    )
    # Owner/migration role: runs DDL (Alembic). Must own the tables.
    migration_database_url: str = Field(
        default="postgresql+asyncpg://concierge:concierge@localhost:5432/concierge",
        description="Async DSN for Alembic migrations (table-owning role).",
    )

    # Redis (session memory — Owner B owns the adapter; A only needs the URL for erasure purge)
    redis_url: str = Field(default="redis://localhost:6379/0")
    session_ttl_seconds: int = Field(default=3600, description="Fixed TTL for session keys (T184).")
    session_max_messages: int = Field(default=20, description="Max clean turns stored per session (T190).")
    router_confidence_threshold: float = Field(
        default=0.75,
        alias="ROUTER_CONFIDENCE_THRESHOLD",
        description="Classify confidence below this value falls back to ambiguous → agent (T185).",
    )

    # MinIO (object storage — Owner D owns the adapter)
    minio_endpoint: str = Field(default="localhost:9000")

    # Vault
    vault_addr: str = Field(default="http://localhost:8200")
    vault_token: str = Field(default="dev-root-token", alias="VAULT_DEV_ROOT_TOKEN_ID")
    vault_kv_mount: str = Field(default="secret")

    # LLM (Owner B)
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    llm_model: str = Field(default="claude-sonnet-4-6")

    # Embeddings (Owner B)
    embedding_provider: str = Field(default="voyage", alias="EMBEDDING_PROVIDER")
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")
    embedding_model: str | None = Field(default=None)

    # Reranker (Owner B — optional)
    reranker_url: str | None = Field(default=None, alias="RERANKER_URL")
    reranker_api_key: str | None = Field(default=None, alias="RERANKER_API_KEY")
    reranker_model: str | None = Field(default=None, alias="RERANKER_MODEL")

    # Internal services (Owner C) — modelserver classifier + NeMo guardrails sidecar.
    # service_token is the shared X-Service-Token issued from Vault in T151;
    # the stub adapters accept an empty default so unit tests can construct them.
    classifier_url: str = Field(default="http://localhost:8001")
    guardrails_url: str = Field(default="http://localhost:8002")
    service_token: str = Field(default="")

    # Auth / session
    session_secret: str = Field(default="change-me-in-prod")
    invitation_ttl_hours: int = Field(default=72)
    public_base_url: str = Field(
        default="http://localhost:8000",
        description="Public origin used to build invitation accept links.",
    )

    log_level: str = Field(default="INFO")


@lru_cache
def get_settings() -> Settings:
    return Settings()
