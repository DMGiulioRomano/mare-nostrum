# samples/ — corpus audio

I file audio **non sono versionati** (vedi `.gitignore`): qui sta solo questo
manifest. Metti i tuoi sorgenti in questa cartella e referenziali per nome nello
`study.yml` (chiave `sample:` dello stream base) e negli stati.

Se il corpus vive in un altro repo (default `../PythonGranularEngine/refs`),
`make samples` ricrea tutti i symlink in un colpo — override con `make samples
REFS=/path/al/corpus`.

Lo study di esempio `base` referenzia `corpus.wav`: copia qui
un file con quel nome (mono o stereo, qualunque sample rate) per renderizzarlo,
oppure cambia il nome nello studio.

## Manifest

| file | descrizione | sorgente |
|------|-------------|----------|
| corpus.wav | (esempio) sorgente granulare | — |
