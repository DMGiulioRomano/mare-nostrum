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

# Cartella (o cartelle) di output correnti: le risolve granstudies, non lo
# shell, cosi' la regola di `for_each:` e del filtro COMBO vive in un posto
# solo (la usa anche la funzione zsh `study`). Una riga per combinazione.
.PHONY: where
where: _require-study $(MARKER)
	@$(PY) -m granstudies where $(STUDY)

# La rete delle varianti discrete: un HTML per combinazione, accanto all'audio.
# Va dopo render: legge i .aif esistenti, non gli YAML.
.PHONY: graph
graph: _require-study $(MARKER)
	$(PY) -m granstudies graph $(STUDY)

# Audio rimasto senza YAML: succede quando si CAMBIA il valore di un asse
# invece di aggiungerne uno. Di default elenca soltanto; APPLY=1 cancella.
# STEMS=1 aggiunge al bersaglio gli stem (<mix>__<stream>.aif), che altrimenti
# sono tenuti perche' seguono il mix da cui nascono.
.PHONY: prune
prune: _require-study $(MARKER)
	$(PY) -m granstudies prune $(STUDY) $(if $(APPLY),--apply,) $(if $(STEMS),--stems,)

# Il giro completo per lo studio della grana: YAML, audio, pagina. Senza stem,
# che per queste varianti sono una seconda copia identica del mix (un solo
# stream) e raddoppiano lo spazio senza servire a niente: `graph` li scarta.
# STEM resta sovrascrivibile da riga di comando (`make explore STEM=true`).
# Il tempo totale lo puo' misurare solo chi vede inizio e fine: con
# `sweep render graph` come prerequisiti la ricetta parte a lavoro gia' finito.
# Quindi un sub-make in una ricetta sola. STEM resta target-specific: da riga
# di comando `make explore STEM=true` vince e si propaga al sub-make.
.PHONY: explore
explore: STEM := false
explore: _require-study
	@t0=$$(date +%s); \
	 $(MAKE) --no-print-directory sweep render graph STUDY=$(STUDY) STEM=$(STEM); \
	 d=$$(( $$(date +%s) - t0 )); \
	 printf "[explore] fatto in %d:%02d — 'make serve STUDY=%s' per aprirla\n" \
	   $$((d / 60)) $$((d % 60)) "$(STUDY)"

# La pagina legge i campioni con fetch + decodeAudioData per disegnare
# sonogramma e forma d'onda: da `file://` il browser lo vieta (origine opaca),
# quindi la si serve. Non e' piu' `http.server` perche' il laboratorio del
# singolo stream fa `POST /render`: vedi `granstudies.serve`.
PORT ?= 8000
.PHONY: serve
serve: graph
	@($(PY) -m granstudies serve $(STUDY) --port $(PORT) & \
	  sleep 1; open -a Safari "http://localhost:$(PORT)/graph.html"; wait)

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

# Niente `render` fra i prerequisiti: `all-study` lo ha gia' fatto, e nel giro
# di `study` la seconda passata era solo rumore nel log. Se l'audio manca,
# cmd_sv lo dice variante per variante ("esegui prima 'render'").
.PHONY: sv
sv: _require-study $(MARKER)
	$(PY) -m granstudies sv $(STUDY) $(if $(LAYOUT),--layout $(LAYOUT),) $(if $(STREAM),--stream $(STREAM),)

# Pipeline completa: sweep + stack + versions + percorso + render. versions e
# percorso sono attivati per presenza (cmd_versions/cmd_percorso sono no-op
# se lo study.yml non ha il blocco corrispondente), quindi girano sempre
# prima di render senza costo per gli study che non li usano.
.PHONY: all-study
all-study: sweep stack versions percorso render #describe matrix compose render-final
