"""Regression test: migration 002 must not run before migration 003 on a fresh DB.

002 creates conversations with REFERENCES widgets(id).
003 creates the widgets table.
Both branch from 001 (parallel Owner B / Owner A slices), so without an
explicit depends_on the topological sort is non-deterministic.

This test is DB-free — it inspects Alembic script metadata only.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _script_dir() -> ScriptDirectory:
    alembic_ini = Path(__file__).parents[3] / "app" / "frameworks" / "db" / "alembic"
    cfg = Config()
    cfg.set_main_option("script_location", str(alembic_ini))
    return ScriptDirectory.from_config(cfg)


def test_002_declares_depends_on_003() -> None:
    sd = _script_dir()
    rev002 = sd.get_revision("002")
    assert rev002 is not None, "revision 002 not found"
    all_deps = set(rev002._all_down_revisions or []) | set(rev002.dependencies or [])
    assert "003" in all_deps, (
        "Migration 002 must declare depends_on=('003',) because it references "
        "widgets(id) which is created by 003. Without this Alembic may run 002 "
        "before 003 on a fresh database."
    )


def test_003_applies_before_002_in_upgrade_order() -> None:
    sd = _script_dir()
    # iterate_revisions walks from head to base; reverse → base-to-head order
    order = [
        rev.revision
        for rev in reversed(list(sd.iterate_revisions("heads", "base")))
    ]
    assert "002" in order and "003" in order, "Both revisions should appear in the upgrade chain"
    assert order.index("003") < order.index("002"), (
        f"003 must be applied before 002 but got order: {order}"
    )
