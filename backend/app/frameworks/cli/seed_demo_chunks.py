"""Embed all published CMS pages into chunks for the demo tenants.

Idempotent: deletes existing chunks for each page before re-inserting.

All page texts are batched into a single embedding API call to stay within
rate limits on free-tier providers (e.g. Voyage AI: 3 req/min).

Usage (from project root via Makefile):
    make seed-demo-chunks

Or directly (with .env exported):
    cd backend && uv run python -m app.frameworks.cli.seed_demo_chunks
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Load .env from project root when running locally (backend/ as CWD).
# docker-compose passes env vars directly so this is a no-op there.
_env_candidates = [
    Path(".env"),
    Path(__file__).parents[4] / ".env",
]
for _p in _env_candidates:
    if _p.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(_p, override=False)
        except ImportError:
            pass
        break


async def seed_chunks() -> None:
    # Import after .env load so get_settings() picks up the key.
    from app.adapters.embeddings.hosted_embeddings import HostedEmbeddings
    from app.frameworks.config import get_settings
    from app.frameworks.db.models import ChunkModel, CMSPageModel
    from app.use_cases._chunkers import paragraph_aware  # noqa: PLC2701

    settings = get_settings()

    if not settings.embedding_api_key:
        raise SystemExit(
            "EMBEDDING_API_KEY is not set.\n"
            "  - Via Makefile: 'make seed-demo-chunks' (includes .env automatically)\n"
            "  - Directly: export EMBEDDING_API_KEY=<key> before running\n"
            "\n"
            "Supported models (set EMBEDDING_MODEL in .env):\n"
            "  voyage-3 (default), voyage-4-lite\n"
            "Invalid: voyage-3s — that model name does not exist."
        )
    # Warn if the configured model looks wrong before making a network call.
    _model_name = settings.embedding_model or (
        settings.embedding_provider if settings.embedding_provider.startswith("voyage-") else "voyage-3"
    )
    _invalid_suffixes = ("-3s", "-3S")
    if any(_model_name.endswith(s) for s in _invalid_suffixes):
        raise SystemExit(
            f"Invalid embedding model: {_model_name!r}\n"
            "voyage-3s is not a valid Voyage model. Use voyage-3 or voyage-4-lite.\n"
            "Fix EMBEDDING_MODEL (or EMBEDDING_PROVIDER) in your .env file."
        )

    engine = create_async_engine(
        settings.migration_database_url,
        poolclass=NullPool,
        future=True,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    embedder = HostedEmbeddings(
        provider=settings.embedding_provider,
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
    )

    # 1. Fetch all published pages.
    async with session_factory() as session:
        async with session.begin():
            pages = (
                await session.execute(
                    select(CMSPageModel).where(CMSPageModel.state == "published")
                )
            ).scalars().all()

    if not pages:
        print("No published CMS pages found — run seed-demo-tenant first.")
        await engine.dispose()
        return

    print(f"Found {len(pages)} published pages. Chunking…")

    # 2. Chunk every page and track which text belongs to which page/chunk-index.
    page_chunks: list[tuple[CMSPageModel, list[str]]] = []
    all_texts: list[str] = []
    for page in pages:
        texts = paragraph_aware.chunk(page.body)
        page_chunks.append((page, texts))
        all_texts.extend(texts)

    if not all_texts:
        print("All pages produced 0 chunks (empty bodies?). Nothing to embed.")
        await engine.dispose()
        return

    print(f"Embedding {len(all_texts)} chunks in one batch call…")
    print(f"  provider={settings.embedding_provider!r}  model={_model_name!r}")
    # Single API request for all texts — stays within rate limits.
    try:
        all_vectors = await embedder.embed(all_texts)
    except Exception as exc:
        err = str(exc)
        hint = ""
        if "401" in err or "unauthorized" in err.lower():
            hint = "\nHint: EMBEDDING_API_KEY is set but rejected — verify the key is valid."
        elif "model" in err.lower() or "invalid" in err.lower():
            hint = (
                f"\nHint: embedding model {_model_name!r} may be unsupported."
                "\nSupported Voyage models: voyage-3, voyage-4-lite"
                "\nFix EMBEDDING_MODEL in your .env file."
            )
        elif "429" in err or "rate" in err.lower():
            hint = "\nHint: rate limit hit — wait a minute and retry."
        raise SystemExit(f"Embedding API error: {exc}{hint}") from exc
    print("Embedding done.")

    # 3. Distribute vectors back and write to DB.
    vector_cursor = 0
    total_inserted = 0

    async with session_factory() as session:
        async with session.begin():
            for page, texts in page_chunks:
                # Delete existing chunks for this page (idempotent).
                await session.execute(
                    delete(ChunkModel).where(
                        ChunkModel.cms_page_id == UUID(str(page.id)),
                        ChunkModel.tenant_id == UUID(str(page.tenant_id)),
                    )
                )
                # Insert new chunks.
                for i, text in enumerate(texts):
                    session.add(
                        ChunkModel(
                            id=uuid.uuid4(),
                            tenant_id=UUID(str(page.tenant_id)),
                            cms_page_id=UUID(str(page.id)),
                            chunk_index=i,
                            content=text,
                            embedding=all_vectors[vector_cursor + i],
                        )
                    )
                print(f"  [{str(page.tenant_id)[:8]}…] {page.title!r}: {len(texts)} chunk(s)")
                total_inserted += len(texts)
                vector_cursor += len(texts)

    await engine.dispose()
    print(f"Done — {total_inserted} chunks seeded across {len(pages)} pages.")


def main() -> None:
    asyncio.run(seed_chunks())


if __name__ == "__main__":
    main()
