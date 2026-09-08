# Modalita' take: ogni rigenerazione va in una cartella nuova invece di
# sovrascrivere l'audio gia' ascoltato. Interruttore di sessione: `export TAKE=1`.
# Senza TAKE tutto resta com'era, in generated/<study>/.
#
# Una take nasce come `cp -al` della precedente: hardlink, quindi istantanea e a
# costo zero di disco. Il render e' incrementale, salta le varianti immutate
# (che restano condivise) e riscrive solo quelle toccate dalla modifica --
# `render.py` sgancia l'hardlink prima di scrivere, cosi' la take precedente
# non viene toccata.

TAKES_DIR = takes/$(STUDY)
KEEP ?= 3

# Cartella di output corrente: la risolve granstudies, non lo shell, cosi' la
# regola di TAKE vive in un posto solo (la usa anche la funzione zsh `study`).
.PHONY: where
where: _require-study $(MARKER)
	@$(PY) -m granstudies where $(STUDY)

# Solo `audio/` viene hardlinkato: e' li' che stanno i gigabyte, ed e' l'unica
# cosa che scrive l'engine (con lo sgancio dell'hardlink fatto da render.py).
# Tutto il resto -- yaml/, cache/, sv/, lo snapshot study.yml -- e' testo, viene
# copiato davvero: quei file li riscrivono in place scritture che troncano
# l'inode, e condividerli corromperebbe la take precedente.
#
# Apre una take nuova, ma solo se study.yml e' cambiato rispetto allo snapshot
# della take corrente: rilanciare senza aver toccato nulla resta nella stessa
# take, niente cartelle gemelle. E' il gesto dell'utente -- ho cambiato un
# parametro, riascolto -- a segnare il confine fra una take e l'altra.
.PHONY: take
take: _require-study
	@cur="$(TAKES_DIR)/latest"; \
	src=""; \
	if [ -d "$$cur" ]; then src="$$cur"; elif [ -d "generated/$(STUDY)" ]; then src="generated/$(STUDY)"; fi; \
	if [ -d "$$cur" ] && [ -f "$$cur/study.yml" ] && \
	   cmp -s "$$cur/study.yml" "studies/$(STUDY)/study.yml"; then \
		echo "[take] study.yml invariato: resto in $(TAKES_DIR)/$$(readlink $$cur)"; \
		exit 0; \
	fi; \
	ts=$$(date +%Y-%m-%d_%H%M); new=$$ts; n=1; \
	while [ -e "$(TAKES_DIR)/$$new" ]; do n=$$((n+1)); new=$$ts-$$n; done; \
	mkdir -p "$(TAKES_DIR)/$$new"; \
	if [ -n "$$src" ]; then \
		for e in "$$src"/*; do \
			case "$$(basename $$e)" in \
				audio) cp -al "$$e" "$(TAKES_DIR)/$$new/audio" ;; \
				latest) ;; \
				*) cp -a "$$e" "$(TAKES_DIR)/$$new/" ;; \
			esac; \
		done; \
		echo "[take] $$new (audio in hardlink da $$src, il render rifa' solo cio' che cambia)"; \
	else \
		echo "[take] $$new (vuota: primo render da zero)"; \
	fi; \
	ln -sfn "$$new" "$(TAKES_DIR)/latest"

# Storico: data, peso, e il diff dello study.yml rispetto alla take precedente.
# Il peso per take conta due volte i file condivisi via hardlink; il totale in
# fondo li conta una volta sola ed e' l'occupazione vera.
.PHONY: takes
takes: _require-study
	@[ -d "$(TAKES_DIR)" ] || { echo "nessuna take per '$(STUDY)' (aprine una con 'make take STUDY=$(STUDY)')"; exit 0; }; \
	list() { for x in $(TAKES_DIR)/*/; do x=$${x%/}; [ -L "$$x" ] || echo "$$x"; done | sort; }; \
	cur=$$(readlink "$(TAKES_DIR)/latest" 2>/dev/null); prev=""; \
	for d in $$(list); do \
		label=$$(basename "$$d"); \
		size=$$(du -sh "$$d" 2>/dev/null | cut -f1); \
		mark=""; [ "$$label" = "$$cur" ] && mark="  <- latest"; \
		printf "  %-22s %6s%s\n" "$$label" "$$size" "$$mark"; \
		if [ -n "$$prev" ] && [ -f "$$prev/study.yml" ] && [ -f "$$d/study.yml" ]; then \
			diff "$$prev/study.yml" "$$d/study.yml" | grep "^[<>]" | head -6 | sed "s/^/        /"; \
		elif [ ! -f "$$d/study.yml" ]; then \
			echo "        (nessuno snapshot: take mai renderizzata)"; \
		else \
			echo "        (prima take)"; \
		fi; \
		prev="$$d"; \
	done; \
	echo "  ---"; \
	printf "  %-22s %6s\n" "totale su disco" "$$(du -sh $(TAKES_DIR) | cut -f1)"

# Tiene le KEEP take piu' recenti (default 3) piu' quella corrente, cancella il
# resto. Cancellare una take non libera lo spazio condiviso via hardlink con
# quelle piu' recenti: e' il comportamento giusto, non un bug.
.PHONY: takes-clean
takes-clean: _require-study
	@[ -d "$(TAKES_DIR)" ] || { echo "nessuna take per '$(STUDY)'"; exit 0; }; \
	list() { for x in $(TAKES_DIR)/*/; do x=$${x%/}; [ -L "$$x" ] || echo "$$x"; done | sort; }; \
	cur=$$(readlink "$(TAKES_DIR)/latest" 2>/dev/null); \
	keep=$$(list | tail -$(KEEP)); \
	for d in $$(list); do \
		label=$$(basename "$$d"); \
		[ "$$label" = "$$cur" ] && continue; \
		echo "$$keep" | grep -qx "$$d" && continue; \
		echo "[takes-clean] rimuovo $$d"; \
		rm -rf "$$d"; \
	done
