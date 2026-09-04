# Diario di ascolto — study01

Sintesi cronologica delle sessioni di ascolto. Aggiornato dall'AI su richiesta leggendo tutti i log giornalieri.

---

## Temi emergenti

### Pitch come parametro dominante
`density alta + distribution ≈ 0`

Quando la density è alta in banda audio e la distribution è prossima a zero, il parametro percettivo che emerge è l'altezza. La granularità si dissolve: l'orecchio non percepisce più la grana singola ma un suono continuo con pitch definito. Osservato per la prima volta il **2026-06-30**.

### Density come unica altezza, accordi come rapporti di stream
Nessun parametro di pitch dedicato: l'altezza nasce dalla frequenza di emissione dei grani (density). Sotto ~20 Hz si sente come ritmo, sopra come altezza, in mezzo flutter. Armonia e polimetrie nascono dallo stesso gesto — impilare stream con density in rapporto tra loro — letto in banda audio (accordi) o sub-audio (polimetrie). Rapporti semplici = ridondanti/consonanti, rapporti complessi = informativi/ruvidi. Messo a fuoco il **2026-07-01**.

### Zona d'ombra di grain.duration al variare della density
La sensibilità percettiva a un passo fisso di variazione su `grain.duration` non è uniforme: esistono fasce ("zone d'ombra") dove il gradiente percepito è ≈ 0, robuste al punto di lettura del buffer. Mappate su density 5–60 il **2026-07-05**.

### Ascolto a due stream in stack: delta di un parametro, non valore assoluto
Con il sistema `versions` (stack multi-stem con onset/durata per-stream, export Sonic Visualiser) si apre un tipo di ascolto diverso da quello a uno stream: due stream suonano verticalmente insieme e l'asse mosso è il **delta** di un parametro tra i due, non il suo valore assoluto. Aperto il **2026-07-14** su due assi:
- **differenza in Hz** tra stream (0.1–3 Hz finora): attraversa più regioni percettive — battimento lento, poi roughness, poi due altezze distinte oltre la banda critica (~20 Hz, variabile con la frequenza centrale). Da mappare lungo tutta la banda.
- **differenza di density** tra stream (range density 30–50 Hz): tra 0.01 e 0.1 percetto stabile (lieve spostamento del peso spettrale, es. nasalità), a 1 compare battimento interno percepibile. Soglia esatta tra 0.1 e 1 da individuare.

---

## Cronologia

| Data | Parametri esplorati | Temi percettivi | Note |
|------|---------------------|-----------------|------|
| 2026-06-30 | density, distribution | pitch, altezza | Alta density + distribution≈0 → emergenza del pitch |
| 2026-07-01 | density, grain.duration (messa a fuoco, no ascolto) | ritmo↔pitch, accordi come rapporti | Vincolo a 2 parametri fissato; drammaturgia rimandata |
| 2026-07-05 | grain.duration × density | zona d'ombra, asimmetria di forma d'onda | Mappate zone d'ombra da density 5 a 60; asimmetria spiegata da fase/pointer fermo |
| 2026-07-14 | Δ Hz e Δ density tra due stream (stack a 2 stem, versions) | battimento, roughness, soglia banda critica, peso spettrale/nasalità | Ascolto a due stream in stack (delta, non valore assoluto); Δ Hz da estendere a tutta la banda, Δ density da affinare tra 0.1 e 1 |
