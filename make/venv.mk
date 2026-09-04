# Gestione virtualenv, submodule e test.

$(VENV):
	$(PYTHON) -m venv $(VENV)

# Marker di installazione: ricreato se pyproject cambia.
$(MARKER): pyproject.toml | $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@touch $(MARKER)

.PHONY: setup
setup: submodule $(MARKER)
	@zsh setup.sh
	@echo "Setup completato. Engine: $$(git -C engine rev-parse --short HEAD 2>/dev/null || echo 'non inizializzato')"

.PHONY: submodule
submodule:
	@git submodule update --init --recursive

.PHONY: tests
tests: $(MARKER)
	$(PY) -m pytest

# End-to-end (issue #4): study.yml su disco -> CLI -> YAML -> audio. Piu' lenti
# della suite veloce perche' renderizzano davvero, e servono il submodule
# engine (senza, i test che passano dall'engine si skippano da soli).
# MPLBACKEND=Agg: nessun display in CI ne' sotto make.
.PHONY: e2e-tests
e2e-tests: $(MARKER)
	MPLBACKEND=Agg $(PY) -m pytest -m e2e

.PHONY: venv
venv: $(MARKER)
