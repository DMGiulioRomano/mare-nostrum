# Stadi della pipeline che producono dati testuali (no audio).

.PHONY: sweep
sweep: _require-study $(MARKER)
	$(PY) -m granstudies sweep $(STUDY) $(if $(STREAM),--stream $(STREAM),)

.PHONY: stack
stack: _require-study $(MARKER)
	$(PY) -m granstudies stack $(STUDY)

.PHONY: versions
versions: _require-study $(MARKER)
	$(PY) -m granstudies versions $(STUDY)

.PHONY: percorso
percorso: _require-study $(MARKER)
	$(PY) -m granstudies percorso $(STUDY)

.PHONY: describe
describe: _require-study $(MARKER)
	$(PY) -m granstudies describe $(STUDY)

.PHONY: matrix
matrix: _require-study $(MARKER)
	$(PY) -m granstudies matrix $(STUDY) $(if $(THRESHOLD),--threshold $(THRESHOLD),)

.PHONY: compose
compose: _require-study $(MARKER)
	$(PY) -m granstudies compose $(STUDY) \
		$(if $(SEED),--seed $(SEED),) \
		$(if $(STEPS),--steps $(STEPS),) \
		$(if $(START),--start $(START),)

.PHONY: sv
sv: _require-study render
	$(PY) -m granstudies sv $(STUDY) $(if $(LAYOUT),--layout $(LAYOUT),) $(if $(STREAM),--stream $(STREAM),)

# Pipeline completa: sweep + stack + versions + percorso + render. versions e
# percorso sono attivati per presenza (cmd_versions/cmd_percorso sono no-op
# se lo study.yml non ha il blocco corrispondente), quindi girano sempre
# prima di render senza costo per gli study che non li usano.
.PHONY: all-study
all-study: sweep stack versions percorso render #describe matrix compose render-final
