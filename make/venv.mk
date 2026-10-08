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

# Il brano (#8): il master coi `file:` e il master con gli stream scritti
# dentro danno gli stessi grani e lo stesso audio, e ogni file reso da solo
# suona come nel brano. Rendono il brano intero piu' volte: minuti, non secondi.
# Coi sample veri in samples/ confrontano il brano com'e'; senza, sintetici.
.PHONY: brano-tests
brano-tests: $(MARKER)
	MPLBACKEND=Agg $(PY) -m pytest -m brano tests/test_brano.py

.PHONY: venv
venv: $(MARKER)
