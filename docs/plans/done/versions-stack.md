# Processo `versions` — repliche dello stack concatenate nel tempo

## Problema

Lo sweep enumera configurazioni ma produce varianti single-stream; lo stack
somma stream verticali ma non enumera niente; spread distribuisce valori sulla
popolazione ma i valori sono fissi per tutto lo studio. Mancava l'asse di
enumerazione sulle **relazioni tra stream**: ascoltare la stessa coppia (o lo
stesso stack) piu' volte in cascata, dove tra una versione e l'altra cambia
solo una variabile condivisa — es. due stream con lo stesso inviluppo di
density, il secondo traslato di `d`, con `d` che vale 1, poi 2, poi 3.

## Decisioni

- **Le relazioni sono nodi-expr esistenti**: nessuna grammatica nuova. Il
  processo inietta le variabili negli scope `let` (ombreggiando i default),
  come spread inietta `i`/`n` — seconda istanza dello stesso pattern.
- **L'inviluppo condiviso e' l'ereditarieta' di sempre**: dichiarato nel
  default di `axes:`, uno stream che ridefinisce solo `expr` eredita il `let`
  via deep-merge (verificato: i dict si fondono, il nodo-expr e' un dict).
- **Concatenazione per onset, non rimappatura degli envelope**: ogni versione
  replica gli stream con `onset += k * duration`; ogni stream conserva il suo
  `time_mode: normalized` sulla propria durata e passa per il builder dello
  stack identico (`build_stack_stream`, estratto da
  `generate_stack_document`). L'engine dimensiona il buffer su
  `max(onset + duration)` (`numpy_audio_renderer`), quindi niente da toccare
  a valle.
- **Seed invariati tra versioni**: camminate e bande identiche in ogni
  replica — tra le versioni cambia *solo* la variabile (confrontabilita').
- **Prodotto cartesiano di proprieta' del processo di enumerazione** (mai
  dello stack), lessicografico nell'ordine di dichiarazione, come gli
  `orderings` dello sweep.
- **Output invariato** (`yaml/stack/stack.yml`): versions e' un modificatore
  del processo stack; render e sv export non cambiano.
- **Guardie di parse**: nomi riservati (`i`/`n`/`pi`/`e`) rifiutati;
  variabile non referenziata da nessuna expr = errore; banda variabile senza
  `n` = errore; richiede `stack:` e `duration:`.
- Il branch CLI parte **prima** di `_load_specs`: il documento grezzo puo'
  essere incompleto per costruzione (variabile senza default nel `let`), il
  parse valido e' quello per-versione dopo l'iniezione.

## Rimandato

- Transizioni interpolate tra versioni (il bordo e' un confine di stream;
  ammorbidire via envelope di volume se serve).
- Variabili-Env (delta che evolve *dentro* una versione): richiederebbe
  Env ⊙ Env in expr; il caso d'uso attuale e' interamente scalare-per-versione.

## File

`src/granstudies/versions.py` (nuovo), `stack.py` (estrazione
`build_stack_stream`), `render.py` (`write_versions_stack`), `__main__.py`
(branch in `cmd_stack`), `tests/test_versions.py`, `tests/test_cli_load.py`,
`studies/study_versions_test/`, reference aggiornato.
