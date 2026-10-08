"""Il brano come lo legge chi lo rende: il master con gli stream risolti (#8).

Dalla #8 `configs/mare-nostrum.yml` e' un master che importa ogni stream da
`configs/streams/<id>.yml` (`- file:`). I test che leggevano gli stream del
brano dal vecchio `mare-nostrum.yml` li leggono da qui, scritti dentro, come
prima: e' la stessa lista che il motore vede dopo `resolve_stream_files`.

`scritto_dentro` e' la promessa del piano (`docs/plans/stream-come-file.md`)
messa per esteso, senza passare dal motore: lo usano anche i test che girano
senza submodule, e i test col motore lo confrontano con lui.
"""
import os

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIGS = os.path.join(ROOT, "configs")
MASTER = os.path.join(CONFIGS, "mare-nostrum.yml")

# Le chiavi che il master tiene per se' accanto a `file:` (regola 4 della
# PythonGranularEngine#290); lo `stream_id` a parte, perche' ha un default.
PIAZZAMENTO = ("onset", "mute", "solo")


def leggi(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def id_del_file(file):
    """Lo `stream_id` di default di una voce `file:`: il nome senza estensione."""
    return os.path.splitext(os.path.basename(file))[0]


def scritto_dentro(master, cartella):
    """Lo stesso master, con ogni stream importato scritto dentro.

    Dal file viene lo stream; dal master il piazzamento e lo `stream_id`, che
    di default e' il nome del file senza estensione. Il resto del file non
    arriva: ne' la sua testa (`seed`, `duration`, `bpm`) ne' il piazzamento
    scritto dentro il suo stream.
    """
    streams = []
    for voce in master["streams"]:
        if "file" not in voce:
            streams.append(voce)
            continue
        (st,) = leggi(os.path.join(cartella, voce["file"]))["streams"]
        sid = voce.get("stream_id", id_del_file(voce["file"]))
        st = {"stream_id": sid,
              **{k: v for k, v in st.items()
                 if k not in PIAZZAMENTO and k != "stream_id"}}
        st.update({k: voce[k] for k in PIAZZAMENTO if k in voce})
        streams.append(st)
    return dict(master, streams=streams)


def brano():
    """Il brano col master risolto: `streams` scritti dentro, come prima della #8."""
    return scritto_dentro(leggi(MASTER), CONFIGS)
