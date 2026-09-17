"""Rete navigabile delle varianti discrete: UNA pagina per tutto lo studio.

In ``mode: discrete`` lo sweep produce un file per punto della griglia e il
nome porta le coordinate (``o2__grain.duration=0.001__pitch.ratio=0.447``).
Qui quei nomi si rileggono e diventano una griglia cliccabile.

La pagina e' una sola, in ``generated/<study>/graph.html``, e tiene dentro
**tutte** le combinazioni di ``for_each:`` gia' renderizzate: gli assi esterni
diventano selettori in cima, la griglia sotto cambia quando li muovi, e la
cella su cui stai resta la stessa — cosi' cambiare ``distribution`` e' un A/B
sullo stesso punto, non un giro fra quattro schede del browser.

Nessuna dipendenza e nessun server: l'HTML sta alla radice dell'output e
carica l'audio con path relativi.
"""
from __future__ import annotations

import html
import json
import os
from typing import Any, Dict, List, Tuple

DISCRETE = os.path.join("audio", "sweep", "discrete")


def parse_coords(basename: str) -> Dict[str, Any]:
    """Coordinate lette dal nome del file. Ignora prefissi (studio, stream).

    Il separatore fra coppie e' ``__`` (``sweep._name``); i nomi degli assi
    contengono sia punti che underscore singoli (``pointer.speed_ratio``),
    quindi si divide sul separatore e non su un pattern del nome. I segmenti
    senza ``=`` — il prefisso ``001-41_o2`` — cadono da soli.

    Il valore e' un float quando e' un numero e la stringa cosi' com'e'
    altrimenti: ``grain.envelope=hanning`` e' un asse categoriale a tutti gli
    effetti, scartarlo faceva collassare la griglia su un envelope solo.
    """
    out: Dict[str, Any] = {}
    for part in basename.split("__"):
        if "=" not in part:
            continue
        name, _, raw = part.partition("=")
        try:
            out[name] = float(raw)
        except ValueError:
            out[name] = raw
    return out


def parse_label(label: str) -> Dict[str, str]:
    """Gli assi esterni di una label ``for_each``, come stringhe.

    Restano stringhe: ``coppia=duration-pitch`` non e' un numero, e per i
    selettori conta l'etichetta, non il valore.
    """
    out: Dict[str, str] = {}
    for part in label.split("__"):
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        out[k] = v
    return out


def collect_nodes(audio_dir: str, rel_to: str) -> List[Dict[str, Any]]:
    """Un nodo per ogni .aif sotto ``audio_dir``, con ``src`` relativo a ``rel_to``.

    Scende ricorsivamente perche' il layout sotto ``discrete/`` puo' avere un
    livello di stream_id (vedi ``render.render_variants``).
    """
    best: Dict[Any, Dict[str, Any]] = {}
    for root, _dirs, files in os.walk(audio_dir):
        for f in sorted(files):
            if not f.endswith(".aif"):
                continue
            name = os.path.splitext(f)[0]
            coords = parse_coords(name)
            if not coords:
                continue
            node = {
                "name": name,
                "src": os.path.relpath(os.path.join(root, f), rel_to),
                "coords": coords,
            }
            # Un punto = un nodo. Con ``render --stem`` accanto al mix c'e' lo
            # stem per stream (``...__stream.aif``), stesse coordinate: nella
            # griglia sarebbero la stessa cella. Vince il nome piu' corto, che
            # e' sempre il mix.
            k = (root, tuple(sorted(coords.items())))
            if k not in best or len(name) < len(best[k]["name"]):
                best[k] = node
    return sorted(best.values(), key=lambda n: n["name"])


def axes_of(nodes: List[Dict[str, Any]], order: List[str] | None = None) -> List[str]:
    """Nomi degli assi presenti.

    ``sweep._name`` ordina le coppie alfabeticamente, quindi l'ordine letto dai
    nomi file non e' quello dichiarato: ``order`` (gli assi dello spec) rimette
    sull'asse X quello che nello ``study.yml`` viene per primo.
    """
    seen: List[str] = []
    for n in nodes:
        for k in n["coords"]:
            if k not in seen:
                seen.append(k)
    if order:
        seen.sort(key=lambda k: order.index(k) if k in order else len(order))
    return seen


def _grid(nodes: List[Dict[str, Any]], order: List[str] | None) -> Dict[str, Any]:
    axes = axes_of(nodes, order)
    ax_x = axes[0] if axes else ""
    ax_y = axes[1] if len(axes) > 1 else ""
    # ``key=str`` perche' un asse categoriale ordina alfabeticamente e
    # ``sorted`` su valori misti numero/stringa alzerebbe TypeError.
    vals = {a: sorted({n["coords"][a] for n in nodes},
                      key=lambda v: v if isinstance(v, float) else str(v))
            for a in (ax_x, ax_y) if a}
    # L'asse piu' lungo va in verticale: una colonna che scorre si legge,
    # una riga che sborda orizzontalmente no. A pari lunghezza vince
    # l'ordine dichiarato nello study.yml.
    if ax_y and len(vals[ax_x]) > len(vals[ax_y]):
        ax_x, ax_y = ax_y, ax_x
    return {
        "axX": ax_x,
        "axY": ax_y,
        "xs": vals[ax_x] if ax_x else [],
        "ys": vals[ax_y] if ax_y else [0],
        "nodes": nodes,
    }


def collect_combos(gen_root: str,
                   orders: Dict[str, List[str]] | None = None) -> List[Dict[str, Any]]:
    """Una voce per combinazione renderizzata, piu' la radice se ha audio.

    Guarda il disco, non lo ``study.yml``: la pagina mostra cio' che e' stato
    renderizzato, e le combinazioni non ancora rese semplicemente non ci sono.

    ``orders`` e' label -> ordine degli assi dichiarato nello ``study.yml``:
    con gli assi esterni ogni combinazione ha i suoi (``coppia`` decide quali
    parametri sono assi), quindi non c'e' un ordine unico per lo studio.
    """
    combos: List[Dict[str, Any]] = []
    candidates: List[Tuple[str, str]] = [("", gen_root)]
    if os.path.isdir(gen_root):
        candidates += [
            (d, os.path.join(gen_root, d))
            for d in sorted(os.listdir(gen_root))
            if os.path.isdir(os.path.join(gen_root, d, DISCRETE))
        ]
    for label, base in candidates:
        audio_dir = os.path.join(base, DISCRETE)
        if not os.path.isdir(audio_dir):
            continue
        nodes = collect_nodes(audio_dir, gen_root)
        if not nodes:
            continue
        combo = {"label": label, "sel": parse_label(label)}
        combo.update(_grid(nodes, (orders or {}).get(label)))
        combos.append(combo)
    return combos


def lab_data(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    """Il corredo del laboratorio: lo stream a riposo e le tacche di ogni parametro.

    Le liste sono quelle gia' scelte nello ``study.yml`` — gli assi interni e
    gli assi esterni ``base.*`` sono, dal punto di vista di uno stream solo, la
    stessa cosa: valori di quel parametro che vale la pena sentire. Il
    laboratorio non li moltiplica in una griglia, li usa come tacche fra cui
    scegliere il valore di un breakpoint.
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
    return {"base": raw.get("base") or {}, "params": params}


def _sel_keys(combos: List[Dict[str, Any]]) -> List[str]:
    keys: List[str] = []
    for c in combos:
        for k in c["sel"]:
            if k not in keys:
                keys.append(k)
    return keys


def _sel_values(combos: List[Dict[str, Any]], keys: List[str]) -> Dict[str, List[str]]:
    def as_num(v: str):
        try:
            return (0, float(v))
        except ValueError:
            return (1, v)

    return {k: sorted({c["sel"][k] for c in combos if k in c["sel"]}, key=as_num)
            for k in keys}


def build_html(study: str, combos: List[Dict[str, Any]],
               lab: Dict[str, Any] | None = None) -> str:
    keys = _sel_keys(combos)
    data = {
        "study": study,
        "keys": keys,
        "values": _sel_values(combos, keys),
        "combos": combos,
        "lab": lab or {"base": {}, "params": []},
    }
    return _template().replace("__TITLE__", html.escape(f"{study} — rete")) \
                    .replace("__DATA__", json.dumps(data))


def write_graph(study: str, gen_root: str, out_path: str,
                orders: Dict[str, List[str]] | None = None,
                lab: Dict[str, Any] | None = None) -> Tuple[int, int]:
    """Scrive ``out_path``. Ritorna ``(combinazioni, nodi)``; (0, 0) = niente audio.

    L'HTML sta alla radice dell'output (``generated/<study>/graph.html``)
    perche' i ``src`` sono relativi a li': una sola pagina raggiunge l'audio di
    tutte le combinazioni.
    """
    combos = collect_combos(gen_root, orders)
    # Senza audio la pagina si scrive lo stesso: il laboratorio compone da zero
    # e non ha bisogno di niente su disco — anzi, e' il caso normale su uno
    # studio appena ripulito. E' la griglia che resta vuota.
    if not combos and not (lab or {}).get("params"):
        return (0, 0)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as fh:
        fh.write(build_html(study, combos, lab))
    return (len(combos), sum(len(c["nodes"]) for c in combos))


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
