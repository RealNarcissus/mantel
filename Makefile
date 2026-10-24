# Convenience targets. Everything here assumes `agy` is on PATH for the
# engine-backed tests; the offline ones need nothing but Python and GTK.

PYTHON ?= python3

.PHONY: help run demo install test test-offline screens clean

help:
	@echo "make run        run the client"
	@echo "make demo       run with sample data, no account needed"
	@echo "make install    per-user install (launcher + desktop entry)"
	@echo "make test       every test (engine-backed ones skip if absent)"
	@echo "make test-offline  only the tests that need no engine"
	@echo "make screens    regenerate docs/screenshots from the widget tree"
	@echo "make clean      remove caches and rendered output"

run:
	$(PYTHON) -m app.main

demo:
	$(PYTHON) -m app.main --demo

install:
	./packaging/install.sh

test-offline:
	@set -e; for t in test_schedules test_changes test_context_fallback \
	          test_extras test_signin test_memory test_todos test_focus \
	          test_palette test_plugins test_gemini_api test_calendar \
	          test_engine_adapter; do \
	          echo "== $$t"; $(PYTHON) tests/$$t.py; done

test: test-offline
	@set -e; for t in test_engine test_agent_flow test_scheduler_run; do \
	          echo "== $$t"; $(PYTHON) tests/$$t.py || true; done

screens:
	GSK_RENDERER=cairo $(PYTHON) tools/make_screenshots.py

clean:
	rm -rf .cache .data tests/out
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
