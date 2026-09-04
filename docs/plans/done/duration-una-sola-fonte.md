# `duration`: una sola fonte, e che dica la verità — documento di design

Discussione del 2026-07-29, nata da un caso concreto: in `stack_1-50smp` tre
gruppi (`fratelli`/`cugini`/`cugini_old`) occupano 0-50, 50-100, 100-150 sulla
stessa timeline, e per farli concatenare senza sovrapposizioni si è dovuto
scrivere `duration: 150` in testa al documento — un numero che non è la durata
di niente. Il documento generato dura 3600 s.

Ogni affermazione sul comportamento attuale è marcata **[eseguito]** (verificata
lanciando il codice o ispezionando lo YAML generato) o **[dedotto]** (letta nel
sorgente, non eseguita).

> **Revisione del 2026-07-29** (issue #42, prima di scrivere codice). Il disegno
> e le cinque decisioni reggono e non cambiano. Cambiano: il conteggio dei
> lavori del top-level (sono **tre**, più un uso interno), la fase 2 (il
> condizionale proposto sarebbe un bug), l'ordine delle fasi (l'errore secco in
> fase 1 lascerebbe la suite rossa), e si aggiunge una fase per `percorso.py`.
> I riferimenti file:line sfasati sono stati corretti. Le verifiche fatte in
> review sono marcate **[eseguito]** come le altre.

Prerequisito di lettura: `docs/plans/done/duration-onset-override.md` (issue
#26), che ha introdotto l'override per-stream e le chiavi riservate di
`versions:`. Questo documento non lo contraddice: ne completa un pezzo rimasto
a metà.

---

## Il problema in una riga

Il `duration:` top-level si chiama "durata del documento" e **non lo è mai**.

## I tre sintomi

1. **La durata del documento è sempre dedotta, mai dichiarata.** [eseguito]
   - stack: `duration = max(onset + duration)` sugli stream — `stack.py:203`
   - versions: idem — `versions.py:640`
   - percorso: idem — `percorso.py:741`
   - envelope sweep: `N*plateau + (N-1)*transition`, e `spec.duration` non
     viene proprio guardata — `envelope_sweep.py:165-177`

   L'unico ramo in cui `spec.duration` finisce davvero come durata di un
   documento è **discrete** (`sweep.py:52`): file statici, senza envelope, dove
   non c'è niente da cui dedurla. E lì `render.py:54` la chiama già
   `base.duration`.

   Precisazione della review: in discrete le due chiavi convivono e sono
   **indipendenti**. Con `duration: 30` top-level e `base: {duration: 6}` esce
   un documento con `duration: 30` e uno stream da 6 s. [eseguito]

2. **`base.duration` è una trappola silenziosa nel ramo `streams:`.**
   `stack.py:134` fa `base["duration"] = spec.duration` senza guardare cosa
   c'era: una `base: {duration: 50}` scritta dentro una entry non fa nulla e
   non avvisa. [eseguito — è esattamente l'errore commesso scrivendo i
   `fratelli`, scoperto solo portando il top-level da 50 a 100]

   Non è ipotetico: `studies/stack/study.yml:18` ha `base: {duration: 6}`
   accanto a `duration: 30` top-level. Il dubbio del plan originale è sciolto:
   **entrambe sono inerti**, e per una ragione che non è quella prevista — quello
   studio non genera nessun documento. I suoi due stream disattivano lo sweep
   (`orders: []`, `orderings: []`) su un `mode: envelope`, e nel ramo envelope
   la durata la calcola comunque `plateau`/`transition`. [eseguito]

3. **La stessa chiave significa cose diverse in rami diversi.**
   `base.duration` = "durata dei file discrete" in un ramo (`render.py:54`,
   con tanto di warning dedicato), inerte nell'altro.

## La causa

Il top-level `duration:` fa **tre lavori**, nessuno dei quali è quello che il
nome promette:

- **default della durata di stream**, ereditato da chi non ne dichiara una;
- **passo di concatenazione di `versions:`**, come fallback quando
  `versions.duration` manca (`versions.py:561-578`);
- **durata del documento engine nel ramo discrete** (`sweep.py:52`), dove
  convive con `base.duration` (la durata dello *stream*) senza sovrapporsi.
  [eseguito]

Il secondo è quello che ha prodotto il numero-bugia: `duration: 150` non
descrive né il documento né uno stream, descrive il passo della griglia.

E c'è un quarto uso, che non è sintassi ma **API interna**: il top-level
`duration:` è il canale con cui i processi passano la durata d'istanza al
parse. `versions.py:595` e `percorso.py:712` scrivono `data_k["duration"] =
...` subito prima di chiamare `resolve_streams`. È la ragione per cui il
divieto secco (D3) non può essere l'ultima riga di codice scritta: prima quel
canale va spostato altrove, in entrambi i processi.

---

## Il disegno proposto

Ogni `duration` sta accanto alla cosa di cui è la durata.

| Cos'è | Dove si scrive | Chi la legge |
|---|---|---|
| durata di **uno stream** (default di documento) | `base: {duration: N}` | tutti i rami |
| durata di **uno stream** (override) | `duration:` di entry | `stack.py` |
| durata di una **versione** | `versions: {duration: N}` | `versions.py` |
| durata di una **istanza** di percorso | `percorso: {duration: ...}` | `percorso.py` (già così) |
| durata del **documento** | non si scrive | dedotta, `max(onset + duration)` |

Simmetrico con `onset`, che già funziona così: `base.onset` è il default di
documento (il top-level è vietato per scelta, `study_spec.py:470`), `onset:` di
entry è l'override.

Il top-level `duration:` non ha più un lavoro e sparisce.

**`percorso:` è il precedente che regge la proposta**: ha già la sua `duration`
dentro il proprio blocco, con unit propria (`percorso.py:173-196`). `versions:`
farebbe lo stesso, e `base:` farebbe quello che già fa per `onset`.

---

## Le decisioni

Nessuna di queste è ovvia, e nessuna va decisa dall'implementazione. **Prese
tutte** nella issue #42; qui restano con la motivazione, più l'esito che la
review ha aggiunto.

**D1 — `versions.duration` scalare. → SÌ.** Oggi pretende un generatore
(`values`/`ramp`/banda) e rifiuta lo scalare: `versions: {duration: 100}` dà
`'duration' deve avere un generatore (dict), trovato 100`. [eseguito] Va fatta
accettare uno scalare broadcastato sulle N versioni — è il caso di gran lunga
più comune e oggi è l'unico che non si può scrivere.

**D2 — `versions.duration` fa anch'essa doppio lavoro. → RESTA DOPPIA (a).** È il passo *e* viene
iniettata come `duration:` del documento della versione (`versions.py:595`),
cioè come default per i suoi stream. Stessa conflazione, un livello più in
basso. Tre opzioni:
  - (a) lasciarla doppia — una versione è un contenitore, ha senso che detti la
    durata di default di chi ci sta dentro;
  - (b) renderla solo passo, e i default degli stream vengono da `base.duration`;
  - (c) due chiavi separate.

  Scelta la **(a)**: una versione è un contenitore, ha senso che detti la durata
  di default di chi ci sta dentro. Va detto esplicitamente, perché è la stessa
  ambiguità che stiamo togliendo sopra — la differenza è che qui la chiave sta
  già accanto alla cosa di cui parla. Conseguenza d'implementazione:
  l'iniezione di `versions.py:595` diventa `data_k["base"]["duration"]`, non più
  la chiave top-level.

**D3 — deprecazione o rimozione del top-level `duration:`. → ERRORE SECCO.** Con
warning per una release, o errore secco con messaggio che indica dove spostarla?
Sono 14 studi, tutti tuoi, nessun consumatore esterno: l'errore secco è
praticabile e si migra in un pomeriggio. Il messaggio deve dire *dove* spostare
la chiave.

**D4 — `onset` top-level resta vietato? → SÌ.** Il divieto
(`study_spec.py:498-505`, "un onset globale che sposta tutti gli stream insieme
è ambiguo") è coerente con `base.onset` come default, e la sua struttura è il
modello da imitare per `duration`: il rifiuto vive in `resolve_streams` sul
documento **originale**, mentre `parse_study_spec` legge senza obiettare la
chiave che il merge di una entry ha appena promosso a top-level.

**D5 — il ramo discrete. → RESTA, cambia la fonte.** Lì `base.duration` è già la
chiave giusta e `spec.duration` è già la durata reale del documento prodotto.
Precisazione della review: le due chiavi oggi convivono e sono indipendenti
(sintomo 1), quindi il cambio non è solo di *fonte* — documento e stream
**collassano sulla stessa chiave**, e un documento discrete più lungo del suo
stream (coda di silenzio) diventa inesprimibile. Nessuno dei 14 studi lo usa:
nessuno produce discrete. Costo accettato, non scoperto a valle.

---

## Fasi

**L'ordine è vincolato, non arbitrario.** Il divieto secco del top-level (D3)
è l'*ultima* modifica di comportamento, non la prima: finché i 14 studi non
sono migrati, finché `versions`/`percorso` usano ancora il top-level come
canale interno e finché i test lo scrivono a mano, un errore anticipato
lascerebbe la suite rossa fra una fase e l'altra. Fino alla fase 5 il fallback
al top-level resta attivo e ogni fase chiude con la suite verde.

### Fase 1 — `study_spec.py`: la fonte di `spec.duration`

Test (`tests/test_study_spec.py`):
- documento con `base: {duration: N}` e nessun `duration:` top-level →
  `spec.duration == N` per ogni stream che non ne dichiara una propria;
- entry con `duration:` propria → vince su `base.duration`;
- nessuna delle due → `spec.duration is None`, e l'errore "stack: lo stream non
  risolve nessuna duration" (`study_spec.py:791`) scatta col messaggio
  aggiornato che indica `base.duration`;
- validazioni `> 0` e di tipo, oggi su `data["duration"]`
  (`study_spec.py:669-676`), estese a `base.duration`;
- fallback: col solo `duration:` top-level il comportamento non cambia (è la
  rete che tiene verdi test e studi fino alla fase 5).

Implementazione: `parse_study_spec` legge la duration da
`data["base"]["duration"]` con fallback al top-level fino alla rimozione.
Attenzione: dopo il merge la entry *diventa* il documento, quindi la catena
entry > base va risolta sul documento merged, come già fa `onset`.

### Fase 2 — `stack.py`: non-regressione e docstring

Test (`tests/test_stack.py`):
- `base.duration` di entry sopravvive alla costruzione dello stream;
- `duration:` di entry vince su `base.duration`;
- durata documento invariata: `max(onset + duration)`.

Implementazione: **niente**, e non è una svista. Il plan originale voleva
rendere `stack.py:134` condizionale «come già è la riga gemella per `onset`»
(`stack.py:135-138`): sarebbe un bug. Il condizionale su `onset` esiste perché
`spec.onset is None` significa "non dichiarato" e un `base.onset` ereditato va
lasciato intatto; ma dopo la fase 1 `spec.duration` **è già** il risultato
della catena entry > base, e non riscriverla quando `base` ne ha una farebbe
perdere silenziosamente l'override di entry — cioè romperebbe `stack_1-50smp`.
La scrittura incondizionata resta corretta e il sintomo 2 è già risolto dalla
fase 1: qui restano i test di non-regressione e la docstring, che oggi
descrive il top-level come default.

### Fase 3 — `versions.py`: passo esplicito

Test (`tests/test_versions.py`):
- `versions: {duration: 100}` scalare → N versioni concatenate a passo 100
  (oggi errore);
- generatore invariato (retrocompatibilità della forma esistente);
- senza `versions.duration` e senza top-level → errore che dice dove scriverla;
- (D2) `versions.duration` continua a fare da default degli stream della
  versione, ma passando per `base.duration`: uno stream con `duration:` propria
  vince, uno senza la eredita.

Implementazione: `_timeline_sequence` accetta lo scalare e lo broadcasta su N;
l'iniezione di `versions.py:595` passa da `data_k["duration"]` a
`data_k["base"]["duration"]`; il messaggio di `versions.py:567-574` va
riscritto (oggi suggerisce `'duration:' top-level`, che dopo non esisterà).

### Fase 3-bis — `percorso.py`: la duration d'istanza

Fase che il plan originale non prevedeva (metteva `percorso` fuori scope
perché la sua `percorso.duration` è già coerente — vero, ma non è il punto).
`percorso.py:712` inietta la durata d'istanza come `duration:` top-level del
documento prima di `resolve_streams`: esattamente il canale che la fase 5
chiuderà. Senza questa fase, `test_percorso.py` diventa rosso alla fase 5.

Test (`tests/test_percorso.py`): la duration d'istanza continua a fare da
default per gli stream dell'istanza; una `duration:` per-stream vince.

Implementazione: `data_k["base"]["duration"] = durations[k]`, gemella di
quella di `versions`.

### Fase 4 — migrazione dei 14 studi

[eseguito] Inventario: **tutti e 14** dichiarano `duration:` top-level e
`base.onset`; **nessuno** ha `base.duration` tranne `stack` (che ha entrambi);
solo `stack_1-50smp` usa `duration:` di entry; 6 usano `versions:`.

- 5 studi sweep/envelope (`1-10ms`, `1-50smp`, `10-50ms`, `50-300ms`,
  `300-1000ms`): `duration: 30` → dentro `base:`. Meccanico.
- 2 studi stack senza `versions:` (`brano01`, `brano01_v2`): il plan originale
  li elencava fra i "sweep/envelope", ma hanno il blocco `stack:` e nessun
  `sweep:`. La migrazione resta la stessa: top-level → `base:`.
- 6 studi stack con `versions:` (`stack_1-10ms`, `stack_10-50ms`,
  `stack_50-300ms`, `stack_100-300ms`, `stack_300-1000ms`, `stack_1-50smp`):
  il top-level si scinde in `base.duration` (durata dello stream) +
  `versions.duration` (passo). Per i cinque gemelli i due numeri coincidono
  (50 e 50); per `stack_1-50smp` no ed è il caso interessante: 50 e 150 — e lì
  `base.duration` non serve nemmeno, perché tutti e tre gli stream hanno già la
  propria `duration:` di entry.
- `stack`: malgrado il nome **non** ha il blocco `stack:` — è uno studio sweep
  multi-stream. Entrambe le sue duration sono inerti (v. sintomo 2): si toglie
  il top-level e si tiene `base: {duration: 6}`, il numero pensato per i file
  discrete.

Ogni studio va rigenerato e **diffato contro il documento prodotto prima della
migrazione**: il target è zero differenze nell'audio. Il `.sv` è il modo più
rapido per accorgersi di uno slittamento.

### Fase 5 — il divieto secco (D3)

L'unica fase che cambia comportamento a valle, e per questo l'ultima.

- `resolve_streams` rifiuta `duration:` top-level nel documento **originale**,
  con la stessa struttura del divieto di `onset` (`study_spec.py:498-505`): il
  documento *merged* continua ad averla, perché è la `duration:` di entry
  appena promossa. Il messaggio dice dove spostare la chiave — `base.duration`
  per la durata di stream, `versions.duration` per il passo delle versioni;
- il fallback al top-level di `parse_study_spec` sparisce;
- migrazione dei test: ~19 file costruiscono documenti col top-level. Meccanico,
  ma è il grosso del diff.

### Fase 6 — documentazione

- `docs/study-yml-reference.md`: la tabella delle quattro `duration`;
- docstring di `stack.py`, `versions.py`, `study_spec.py` (parlano tutte del
  `duration:` top-level come default);
- `CLAUDE.md` di progetto se la regola merita di stare lì.

---

## Rischi

- **Slittamenti silenziosi.** Uno studio migrato male non esplode: produce
  audio di durata diversa. La difesa è il diff dei documenti generati, fase 4,
  non i test unitari.
- **`sv_export`** ha `doc.get("duration", 1.0)` come fallback in quattro punti
  (`sv_export.py:435,470,716,729`). [dedotto] Il documento generato continuerà
  ad avere il suo `duration:` calcolato, quindi non dovrebbe cambiare nulla —
  ma è il posto dove un fallback a `1.0` maschererebbe un bug.
- **`gainmap.py:199`** calcola le finestre di sovrapposizione da
  `onset + duration` per-stream. Non cambia, ma dipende dal fatto che ogni
  stream *abbia* una duration risolta: la fase 1 non deve poter produrre
  `None` silenziosi.
- **La cache degli stem** è per-stream: cambiare la fonte della duration senza
  cambiarne il valore non deve invalidare nulla. Verificato in review, ed è
  **già sussunto dal criterio della fase 4**: il fingerprint dell'engine è uno
  SHA-256 con `sort_keys=True` sul dict dello stream del *documento generato*
  (`engine/src/pge/rendering/stream_cache_manager.py:51-72`), e il render
  incrementale di granstudies gira su mtime con `_dump` che non tocca i file a
  contenuto identico. Zero diff nei documenti ⇒ zero invalidazione, anche a
  chiavi riordinate. Non serve una verifica separata.
- **Il volume dei test** (rischio non previsto): ~19 file di test costruiscono
  documenti col `duration:` top-level e vanno tutti migrati alla fase 5. È
  meccanico, ma è lì che il diff diventa grande e una svista si nasconde bene.

## Impatto cross-repo

**Scatta `.claude/rules/gl-ls-impact.md`**: questo cambia la sintassi
osservabile dello `study.yml`. A fine lavoro serve una issue su
`DMGiulioRomano/gl-ls`, previa conferma, che copra: `base.duration` diventa
significativa nel ramo `streams:`; `versions.duration` accetta uno scalare;
il `duration:` top-level è deprecato/rimosso; la catena di precedenza
entry > `base` per `duration` e `onset`.

Nessun impatto su PGE: il documento engine prodotto continua ad avere
`onset`/`duration` per-stream e `duration:` di documento, che è quello che
l'engine richiede (`engine/docs/reference/yaml.md:197-205`).

## Fuori scope

- La discussione sui rapporti armonici di density (`(x+i)/x`) — è materiale
  musicale, non tocca questo.
- La **sintassi** di `percorso.duration`: già coerente, non si tocca. Quello
  che si tocca in `percorso.py` è solo il canale interno d'iniezione
  (fase 3-bis), non la chiave che l'utente scrive.
- Il ramo discrete: resta com'è (D5), a parte la fusione documento/stream che
  la decisione dichiara.
