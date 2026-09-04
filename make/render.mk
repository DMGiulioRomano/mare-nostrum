# Stadi della pipeline che producono audio/partiture (usano l'engine).

# STEM/CACHE sono attivi di default lato CLI (granstudies render): oltre al
# mix, viene fatta anche una pass STEMS con caching incrementale dell'engine.
# Disattiva esplicitamente con STEM=false / CACHE=false.
STEM  ?= true
CACHE ?= true

.PHONY: render
render: _require-study $(MARKER)
	$(PY) -m granstudies render $(STUDY) --no-score $(if $(FORCE),--force,) $(if $(JOBS),--jobs $(JOBS),) \
		$(if $(filter false,$(STEM)),--no-stem,) $(if $(filter false,$(CACHE)),--no-cache,) $(if $(CACHE_DIR),--cache-dir $(CACHE_DIR),)

.PHONY: render-final
render-final: _require-study $(MARKER)
	$(PY) -m granstudies render-final $(STUDY)

# --- Il brano ---
# Documento engine puro, fuori dal dominio `studies/`: si renderizza chiamando
# direttamente la CLI dell'engine, senza passare da granstudies. Tutto cio' che
# produce sta sotto generated/brano/, accanto (non dentro) alle cartelle degli
# studi, che seguono generated/<study>/.
BRANO ?= mare-nostrum
BRANO_DIR ?= generated/brano
BRANO_EXT := $(if $(filter wav,$(FORMAT)),.wav,$(if $(filter flac,$(FORMAT)),.flac,.aif))
BRANO_OUT ?= $(BRANO_DIR)/$(BRANO)$(BRANO_EXT)

# La cache incrementale per stream esiste solo in --per-stream, ed e' la
# modalita' utile su un brano lungo che si ritocca uno stream per volta.
# --export-sv vuole invece il mix: l'engine lo ignora sotto --per-stream
# (cli.py:582), quindi SV=1 rende in mix.
BRANO_MODE = $(if $(SV),--export-sv,--per-stream --cache --cache-dir $(BRANO_DIR)/cache)

# Tutti i core: l'`auto` dell'engine ne lascia uno libero (core-1, cli.py:112).
# getconf e' POSIX, funziona su macOS e Linux; se manca si ricade su 'auto'.
BRANO_JOBS ?= $(shell getconf _NPROCESSORS_ONLN 2>/dev/null || echo auto)

.PHONY: brano
brano: $(MARKER)
	@mkdir -p $(BRANO_DIR)/logs
	$(PY) engine/src/main.py $(BRANO).yml $(BRANO_OUT) \
		--renderer $(if $(RENDERER),$(RENDERER),numpy) \
		--samples-dir samples \
		--log-dir $(BRANO_DIR)/logs \
		$(BRANO_MODE) \
		--jobs $(if $(JOBS),$(JOBS),$(BRANO_JOBS)) \
		$(if $(FORMAT),--format $(FORMAT),) \
		$(if $(VISUALIZE),--visualize,)
