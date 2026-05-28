"""Persona injection end-to-end unit test (T152).

Verifies that two tenants with different persona_config["persona_summary"] values
produce different system prompts. Uses the Jinja2 rendering path introduced in T188.
"""

from __future__ import annotations

import pytest

from app.frameworks.api.routes.chat import _load_system_prompt


def test_distinct_personas_produce_distinct_prompts() -> None:
    prompt_a = _load_system_prompt("You are Aria, a luxury car sales assistant.")
    prompt_b = _load_system_prompt("You are Max, a budget travel booking assistant.")

    assert "Aria" in prompt_a
    assert "Max" not in prompt_a

    assert "Max" in prompt_b
    assert "Aria" not in prompt_b


def test_empty_persona_renders_without_error() -> None:
    prompt = _load_system_prompt("")
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_persona_injected_at_correct_location() -> None:
    persona = "You specialise in enterprise SaaS onboarding."
    prompt = _load_system_prompt(persona)
    # Persona content must appear somewhere in the rendered prompt
    assert persona in prompt


def test_jinja2_special_chars_in_persona_are_safe() -> None:
    persona = "Support for O'Brien & Associates — specialists in <data> pipelines."
    prompt = _load_system_prompt(persona)
    # Jinja2 auto-escaping is OFF for plain Template (non-HTML env), so raw text preserved
    assert "O'Brien" in prompt
