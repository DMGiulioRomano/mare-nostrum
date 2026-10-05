"""La pagina del laboratorio: un solo stream, composto e sentito al volo.

La pagina e' una sola, in ``generated/<study>/graph.html``, e non guarda piu'
il disco: la griglia delle varianti gia' rese non c'e' piu' (git la ricorda),
e quello che resta e' il banco su cui si compone UN documento engine — i
parametri sono le tacche dichiarate nello ``study.yml``, l'audio nasce da
``POST /render`` (vedi ``serve.py``).

Nessuna dipendenza: l'HTML sta alla radice dell'output e carica l'audio con
path relativi.
"""
from __future__ import annotations

import html
import json
import os
from typing import Any, Callable, Dict, List


def lab_data(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    """Il corredo del laboratorio: lo stream a riposo e le tacche di ogni parametro.

    Le liste sono quelle gia' scelte nello ``study.yml`` — gli assi interni e
    gli assi esterni ``base.*`` sono, dal punto di vista di uno stream solo, la
    stessa cosa: valori di quel parametro che vale la pena sentire. Il
    laboratorio non li moltiplica in una griglia, li usa come tacche fra cui
    scegliere il valore di un breakpoint.

    Porta anche il ``seed:`` del documento: non e' una tacca, e' l'altra
    meta' dell'identita' di uno stream insieme all'id (#5).
    """
    raw = raw or {}
    params: List[Dict[str, Any]] = []
    def add(path: str, values: List[Any]) -> None:
        # Categoriale = il valore e' un nome, non un numero. Restano manopole
        # fisse per lo stream, con un'eccezione: `grain.envelope`, che la
        # pagina automatizza scrivendo {states, curve} invece di una lista di
        # breakpoint — l'engine rifiuta la seconda ("Window non trovata") ma
        # conosce la prima (MultiStateWindowStrategy).
        kind = "num" if all(isinstance(v, (int, float)) for v in values) else "cat"
        params.append({"path": path, "values": values, "kind": kind})

    for name, node in (raw.get("axes") or {}).items():
        if isinstance(node, dict) and node.get("values"):
            add(name, node["values"])
    for key, node in (raw.get("for_each") or {}).items():
        # Solo le patch su `base.`: `stack.seed` o `percorso.arco` non sono
        # parametri di uno stream e nel laboratorio non hanno posto.
        if key.startswith("base.") and isinstance(node, dict) and node.get("values"):
            add(key[len("base."):], node["values"])
    # Il `seed:` dello studio (#5). Serve al laboratorio perche' l'RNG
    # dell'engine e' (seed, rng_group o stream_id, componente): un documento
    # senza seed pesca un seed di sessione, e due render dello stesso file
    # suonano diversi. Si passa COSI' COM'E', `None` compreso: uno studio che
    # non lo dichiara non ha un seed, e il laboratorio non deve inventarne uno
    # (vedi `seedDoc` nella pagina).
    return {"base": raw.get("base") or {}, "params": params,
            "seed": raw.get("seed")}


def lab_completo(raw: Dict[str, Any] | None, campioni: List[str],
                 finestre: Dict[str, Any],
                 limiti: Callable[[str], Any],
                 predefiniti: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Il corredo intero, come lo vede la pagina: ``lab_data`` piu' quello
    che lo ``study.yml`` non dice.

    Sta qui, e non dentro ``cmd_graph``, perche' i test della pagina devono
    caricarla con lo stesso corredo che riceve servita da ``make serve``:
    una copia scritta a mano nel test diverge alla prima manopola aggiunta.
    Le dipendenze dal disco e dall'engine — i file dei sample, i profili
    delle finestre, i limiti dei parametri, i default dell'engine per path
    (``engine_bridge.parameter_path_defaults``) — arrivano da chi chiama.
    """
    lab = lab_data(raw)
    lab["envelopes"] = finestre
    noti = {p["path"] for p in lab["params"]}
    # Il sample e' una manopola fissa come le altre categoriali, ma le sue
    # tacche non stanno nello study.yml: sono i file della cartella dei sample.
    if campioni and "sample" not in noti:
        lab["params"].append({"path": "sample", "values": list(campioni), "kind": "cat"})
    # Volume, pan e pan_range non hanno tacche: sono aggiustamenti continui e
    # si scrivono a mano. `pan` serve anche come punto da cui partono gli
    # offset delle voci (voice 0 sta li'), `pan_range` come dispersione del
    # singolo grano. I limiti li sa l'engine (bounds.bounds_for), non li
    # riscriviamo qui; dove non li conosce (pan_range) restano None.
    for path in ("volume", "pan", "pan_range"):
        if path in noti:
            continue
        lo, hi = limiti(path) or (None, None)
        lab["params"].append({"path": path, "values": [], "kind": "num",
                              "free": True, "min": lo, "max": hi})
    # Cosa suona un parametro che il documento aperto non dichiara: il default
    # dell'engine, che la pagina mostra li' (`assente`). Il foglio bianco parte
    # invece dai suoi DEFAULTS, che per `grain.duration` e `grain.envelope`
    # sono altri valori.
    for p in lab["params"]:
        if p["path"] in (predefiniti or {}):
            p["engine"] = predefiniti[p["path"]]
    return lab


def build_html(study: str, lab: Dict[str, Any] | None = None) -> str:
    data = {"study": study,
            "lab": lab or {"base": {}, "params": [], "seed": None}}
    return _template().replace("__TITLE__", html.escape(f"{study} — laboratorio")) \
                    .replace("__DATA__", json.dumps(data))


def write_graph(study: str, out_path: str,
                lab: Dict[str, Any] | None = None) -> int:
    """Scrive ``out_path``. Ritorna il numero di parametri del laboratorio.

    La pagina si scrive sempre: il laboratorio compone da zero e non ha
    bisogno di niente su disco.
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as fh:
        fh.write(build_html(study, lab))
    return len((lab or {}).get("params") or [])


_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "graph_page.html")


def _template() -> str:
    """Il guscio della pagina.

    Sta in un file suo e non in una stringa qui: e' HTML/CSS/JS vero, e dentro
    un .py perderebbe evidenziazione, indentazione e ``node --check``.
    """
    with open(_TEMPLATE_PATH) as fh:
        return fh.read()


_AUDIO = (".wav", ".flac", ".aif", ".aiff")


def campioni(samples_dir: str) -> List[str]:
    """I sample della cartella dello studio, come li scrive `sample:`.

    Nel laboratorio il sample e' una manopola fissa per lo stream come le
    altre categoriali: cambiarlo e' un ascolto diverso, non un asse. I nomi
    sono relativi a ``samples_dir`` — e' cosi' che l'engine li risolve.
    """
    out: List[str] = []
    for root, _dirs, files in os.walk(samples_dir):
        for f in files:
            if f.lower().endswith(_AUDIO):
                out.append(os.path.relpath(os.path.join(root, f), samples_dir))
    return sorted(out)
