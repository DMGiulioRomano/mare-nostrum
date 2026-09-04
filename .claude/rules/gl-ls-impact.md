# Impact analysis su gl-ls per modifiche di sintassi YAML

Questo repo definisce la superficie YAML (`study.yml`) che
[gl-ls](https://github.com/DMGiulioRomano/gl-ls) — il language server — deve
validare e diagnosticare. Le due cose divergono facilmente se una cambia senza
l'altra.

## Quando si applica

Ogni volta che una feature o un fix in questo repo cambia la **sintassi** dello
`study.yml`: chiavi nuove o rimosse, chiavi riservate, generatori (`values` |
`ramp` | banda), unit del walk, default/ereditarietà tra chiavi, bounds dei
parametri, o qualunque altra regola che un editor dovrebbe poter validare in
tempo reale.

Non si applica a modifiche che non toccano la sintassi osservabile dello YAML
(refactoring interni, render, fixture di test, ascolto/diario).

## Cosa fare

1. Prima di chiudere il lavoro sul branch (prima del merge, non ad ogni commit
   intermedio), fai un'analisi di impatto su gl-ls: quali diagnostiche
   esistenti diventano obsolete o sbagliate, quali nuove regole andrebbero
   aggiunte, quali bounds/generatori/chiavi cambiano.
2. Apri una issue nel repo `gl-ls` (via `gh issue create --repo
   DMGiulioRomano/gl-ls`) che descrive: cosa è cambiato in granulation-studies
   (con riferimento a commit/PR), quale comportamento di gl-ls oggi non
   riflette più la nuova sintassi, e cosa andrebbe fatto lato language server.
3. Prima di aprire la issue, avvisa l'utente e chiedi conferma (è un'azione
   visibile su un repo remoto diverso da quello su cui si sta lavorando).
