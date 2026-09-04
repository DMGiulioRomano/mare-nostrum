# granulation-studies — interfaccia di alto livello.
# Ogni target wrappa la CLI `python -m granstudies` dentro il venv.
#
# Uso tipico:
#   make setup
#   make sweep   STUDY=1-10ms
#   make render  STUDY=1-10ms
#   make describe STUDY=1-10ms
#   make matrix  STUDY=1-10ms
#   make compose STUDY=1-10ms
#   make render-final STUDY=1-10ms

# Interprete di sistema per creare il venv: preferisci 3.11 (versione del
# progetto), poi python3/python. Override esplicito: make setup PYTHON=...
PYTHON := $(shell command -v python3.11 || command -v python3 || command -v python)
VENV   := .venv
VENV_BIN := $(VENV)/bin
PY     := $(VENV_BIN)/python
PIP    := $(VENV_BIN)/pip
MARKER := $(VENV)/.installed

STUDY ?=

.DEFAULT_GOAL := help

include make/venv.mk
include make/studies.mk
include make/render.mk
include make/clean.mk

.PHONY: help
help:
	@echo "granulation-studies — target disponibili:"
	@echo "  make setup                 venv + submodule engine + dipendenze"
	@echo "  make tests                 esegue pytest, suite veloce (gate pre-commit)"
	@echo "  make e2e-tests             end-to-end: CLI + render reale (lento, serve engine)"
	@echo "  make sweep STUDY=...        genera le varianti YAML  (STUDY = nome cartella in studies/, es. 1-10ms)"
	@echo "  make stack STUDY=...        genera il documento multi-stream (stack, puro)"
	@echo "  make versions STUDY=...     genera il documento delle versioni (prodotto cartesiano)"
	@echo "  make percorso STUDY=...     genera il documento del percorso (orchestrazione temporale)"
	@echo "  make render STUDY=...       renderizza audio (incrementale, parallelo; FORCE=1 rifa' tutto, JOBS=n worker)"
	@echo "  make describe STUDY=...     descrittori audio -> results.yml"
	@echo "  make matrix STUDY=...       matrice di parentela -> kinship.json"
	@echo "  make compose STUDY=...      genera final.yml dal percorso/grafo"
	@echo "  make render-final STUDY=... renderizza il brano finale"
	@echo "  make sv STUDY=...            CSV envelope per Sonic Visualiser"
	@echo "  make all-study STUDY=...    pipeline completa (sweep→stack→render)"
	@echo "  make clean / clean-all      pulizia output / output+venv"
	@echo "  make kill-sonic             chiude tutte le istanze di Sonic Visualiser (senza salvare)"

.PHONY: kill-sonic
kill-sonic:
	@pkill -x "Sonic Visualiser" 2>/dev/null && echo "Sonic Visualiser chiuso." || echo "Nessuna istanza di Sonic Visualiser in esecuzione."

.PHONY: _require-study
_require-study:
	@if [ -z "$(STUDY)" ]; then \
		echo "Errore: specifica STUDY=<nome cartella in studies/>"; exit 1; \
	fi
