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
# direttamente la CLI dell'engine, senza passare da granstudies.
BRANO ?= mare-nostrum
BRANO_OUT ?= generated/$(BRANO)$(if $(filter wav,$(FORMAT)),.wav,$(if $(filter flac,$(FORMAT)),.flac,.aif))

.PHONY: brano
brano: $(MARKER)
	@mkdir -p $(dir $(BRANO_OUT))
	$(PY) engine/src/main.py $(BRANO).yml $(BRANO_OUT) \
		--renderer $(if $(RENDERER),$(RENDERER),numpy) \
		--samples-dir samples \
		$(if $(FORMAT),--format $(FORMAT),) \
		$(if $(VISUALIZE),--visualize,) \
		$(if $(SV),--export-sv,) \
		$(if $(JOBS),--jobs $(JOBS),)
