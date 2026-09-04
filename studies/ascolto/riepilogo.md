# Riepilogo — study01

Consolida i log giornalieri (`YYYY-MM-DD.md`) in regioni e transizioni.
Aggiornato su richiesta leggendo i log.

- **plateau** = range dove il percetto resta uguale (`density`/`grain.dur` come range)
- **transizione** = range dove cambia (bracket `a→b` sull'asse mosso)
- le frontiere si spostano col `sample`: sempre indicato

## Ascolto a uno stream

Un solo stream, si ascolta la modifica di un solo parametro su di esso
(`density` assoluta, `grain.dur`).

Le zone qui sotto sono definite come stream `zona_ombra_*` in
`studies/1-10ms/study.yml:49-105` (4 zone compartimentate,
ciascuna generata via `spread` in 7 cugini che differiscono solo per
`base.pointer.start`, secondi assoluti — mappa indice→secondi: `1=0.1
2=0.25 3=0.4 4=0.55 5=0.8 6=0.915 7=1.1`, vedi commento `study.yml:57-58`).
I vecchi stream generici `lettura_avanzata_*` sono stati **rimossi** dallo
YAML nel refactor: non esistono più nel file, le zone li sostituiscono del
tutto.

Le colonne `density`/`grain.dur` qui sotto riflettono i valori **ascoltati**
finora; dove lo YAML attuale ha esteso il range oltre l'ascolto, la riga è
marcata `⚠︎ da riascoltare` (le zone vanno rifatte da capo, vedi
`promemoria.md`).

| stream (study.yml) | tipo | density | grain.dur | percetto |
|---------------------|------|---------|-----------|----------|
| `zona_ombra_d01_10` (:66) | transizione | 5 | 0.001→0.0035 | ogni passo di 0.00025 si sente |
| `zona_ombra_d01_10` (:66) | plateau | 5 | 0.0035–0.005 | zona d'ombra (poca differenza percepita) |
| `zona_ombra_d10_20` (:74) | plateau | 10 | 0.00375–0.00475 | zona d'ombra |
| `zona_ombra_d10_20` (:74) | plateau | 15 | 0.00325–0.00425 e 0.0045–0.0055 | zona d'ombra (due fasce) |
| `zona_ombra_d10_20` (:74) | plateau | 20 | 0.00325–0.0045 | zona d'ombra |
| `zona_ombra_d25_50` (:85) | plateau | 25 | 0.00325–0.00475 | zona d'ombra |
| `zona_ombra_d25_50` (:85) | plateau | 30 | 0.00325–0.00475 | zona d'ombra |
| `zona_ombra_d25_50` (:85) | plateau | 35 | 0.003–0.005 | zona d'ombra |
| `zona_ombra_d25_50` (:85) | plateau | 40 | 0.00325–0.00475 | zona d'ombra |
| `zona_ombra_d25_50` (:85) | plateau | 45 | 0.003–0.00475 | zona d'ombra |
| `zona_ombra_d25_50` (:85) | plateau | 50 | 0.003–0.005 | zona d'ombra |
| `zona_ombra_d55_80` (:97) | plateau | 55 | 0.003–0.00775 | zona d'ombra, forse oltre (da verificare 0.008–0.01, ora coperto dalla ramp fino a 0.008) |
| `zona_ombra_d55_80` (:97) | plateau | 60 | 0.003–0.00775 | zona d'ombra (= density 55) |
| `zona_ombra_d55_80` (:97) | ⚠︎ da riascoltare | 80 | — | la ramp arriva a **80** (`study.yml:101 ramp {start: 55, stop: 80}`, 2 valori: 55 e 80); ascoltata finora solo fino a density 60 — density 80 ancora da sentire |

Scala `10-50ms` (ascolto 2026-07-18), sweep `grain.duration` 10-50 ms:

| stream (study.yml) | tipo | asse mosso | valore/range | percetto |
|---------------------|------|------------|---------------|----------|
| base (sweep step) | plateau | grain.duration step | ≈ 1 ms | differenza tra un valore e il successivo percepita ma minima, non ha carattere musicale (dettaglio timbrico) |
| base (sweep step) | transizione | grain.duration step | 1→2.5 ms | il salto tra valori diventa percettivamente rilevante |
| base (sweep step) | plateau | grain.duration step | ≈ 2.5 ms | differenze importanti tra un valore e il successivo |
| base | plateau/transizione | grain.duration | 10→30-50 ms, a density bassa (grain-rate ≲ 30 Hz) | a volte sensazione di sdoppiamento in due voci distinte (assente/più debole a grain.duration ≈ 10 ms); le due voci tendono a fondersi avvicinandosi a grain-rate ~30 Hz; soglia precisa in density/grain.duration ancora da individuare, da riascoltare |

> Nota `zona_ombra_d01_10`: l'override `axes.density.ramp.step: 1`
> (`study.yml:67`) sulla ramp globale `{start: 1, stop: 10, step: 5}`
> (`study.yml:42`) fa sì che lo stream ora spazzi density **1–10** a passo 1,
> non solo density 5. Le due righe qui sopra registrano il solo slice density 5
> già ascoltato; gli altri valori (1–4, 6–10) sono da coprire nel riascolto.

## Ascolto a due stream in stack (delta tra stream)

Due stream suonano verticalmente insieme; l'asse mosso non è il valore
assoluto di un parametro ma il **delta** dello stesso parametro tra i due
stream. Strumento: `versions` (sample `study_versions_test`), che permette
di stackare stem con onset/durata per-stream.

Nota: dal 2026-07-14 si esplora un primo asse così — la differenza in Hz tra
i due stream (battimento/roughness/soglia banda critica) — non ancora
ridotto a plateau/transizioni: la sessione ha solo elencato i valori provati
(0.1, 0.5, 1, 2, 3 Hz) senza annotare il percetto per ciascuno. Da completare,
poi riportare qui con una colonna `Δ Hz`.

Un secondo asse, sempre dal 2026-07-14 (sample `study_versions_test`): la
differenza di **density** tra i due stream in stack (non densità assoluta),
nel range density 30–50 Hz.

| sample | tipo | density (range) | Δdensity | percetto |
|--------|------|------------------|----------|----------|
| study_versions_test | plateau | 30–50 | 0.01–0.1 | percetto stabile: nessun battimento interno, solo lieve spostamento del peso spettrale (es. più/meno nasalità) |
| study_versions_test | transizione | 30–50 | 0.1→1 | compare battimento interno percepibile; punto esatto di soglia non ancora individuato |
