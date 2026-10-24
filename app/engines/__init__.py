"""The engine boundary.

An engine is whatever supplies the intelligence and the tool loop. The client
supplies the desktop: approvals, threads, the work panel, changes, schedules,
memory. Nothing above this package may name an engine, its files, its
protocol or its environment variables — that rule is what makes the app a
desktop *for* agents rather than a client *of* one vendor.

Adapters are selected by name through `MANTEL_ENGINE` (see `app/engine.py`)
and must implement `EngineAdapter`:

    name          a short identifier used in the About panel and logs
    capabilities  what the engine can do, as a frozenset of Capability values
    available     is the engine installed and usable right now?
    models()      [(id, label)] for the model picker
    run(...)      start one turn and return a Turn whose signals stream it

A Turn is engine-neutral: it emits text, thinking, tool events and one final
result. The transcript, work panel and approval UI bind to those signals only.

`tests/test_engine_adapter.py` runs the same expectations against every
adapter, and the fake engine in `tests/fixtures/fake_pi.py` keeps that suite
runnable without any real engine installed.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.engines.base import DEFAULT_TIMEOUT, EngineAdapter, Turn

__all__ = ["DEFAULT_TIMEOUT", "EngineAdapter", "Turn", "registry", "create"]


def registry() -> dict[str, str]:
    """Adapter name -> dotted path. Imported lazily so a missing engine's
    dependencies never break the app."""
    return {
        "legacy": "app.engines.legacy_agy:AgyAdapter",
        "pi": "app.engines.pi_rpc:PiAdapter",
        "gemini": "app.engines.gemini_api:GeminiAdapter",
    }


def create(name: str, **kwargs):
    """Instantiate an adapter by registry name."""
    import importlib  # noqa: PLC0415

    try:
        path = registry()[name]
    except KeyError:
        raise ValueError(
            f"unknown engine {name!r}; known: {', '.join(sorted(registry()))}"
        ) from None
    module_name, _, class_name = path.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)(**kwargs)


def known() -> list[str]:
    return sorted(registry())
