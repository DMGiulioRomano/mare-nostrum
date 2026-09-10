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


def parse_coords(basename: str) -> Dict[str, float]:
    """Coordinate lette dal nome del file. Ignora prefissi (studio, stream).

    Il separatore fra coppie e' ``__`` (``sweep._name``); i nomi degli assi
    contengono sia punti che underscore singoli (``pointer.speed_ratio``),
    quindi si divide sul separatore e non su un pattern del nome. I segmenti
    senza ``=`` — il prefisso ``001-41_o2`` — cadono da soli.
    """
    out: Dict[str, float] = {}
    for part in basename.split("__"):
        if "=" not in part:
            continue
        name, _, raw = part.partition("=")
        try:
            out[name] = float(raw)
        except ValueError:
            continue
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
    return {
        "axX": ax_x,
        "axY": ax_y,
        "xs": sorted({n["coords"][ax_x] for n in nodes}) if ax_x else [],
        "ys": sorted({n["coords"][ax_y] for n in nodes}) if ax_y else [0],
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


def build_html(study: str, combos: List[Dict[str, Any]]) -> str:
    keys = _sel_keys(combos)
    data = {
        "study": study,
        "keys": keys,
        "values": _sel_values(combos, keys),
        "combos": combos,
    }
    return _TEMPLATE.replace("__TITLE__", html.escape(f"{study} — rete")) \
                    .replace("__DATA__", json.dumps(data))


def write_graph(study: str, gen_root: str, out_path: str,
                orders: Dict[str, List[str]] | None = None) -> Tuple[int, int]:
    """Scrive ``out_path``. Ritorna ``(combinazioni, nodi)``; (0, 0) = niente audio.

    L'HTML sta alla radice dell'output (``generated/<study>/graph.html``)
    perche' i ``src`` sono relativi a li': una sola pagina raggiunge l'audio di
    tutte le combinazioni.
    """
    combos = collect_combos(gen_root, orders)
    if not combos:
        return (0, 0)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as fh:
        fh.write(build_html(study, combos))
    return (len(combos), sum(len(c["nodes"]) for c in combos))


_TEMPLATE = """<!doctype html>
<meta charset="utf-8"><title>__TITLE__</title>
<style>
 :root { color-scheme: light dark; --bg:#fff; --fg:#111; --line:#bbb; --dim:#888; --on:#c33; }
 @media (prefers-color-scheme: dark) { :root { --bg:#141414; --fg:#eee; --line:#444; --dim:#888; } }
 body { background:var(--bg); color:var(--fg); font:13px/1.5 ui-monospace,monospace; margin:24px; }
 h1 { font-size:14px; font-weight:600; margin:0 0 14px; }
 .sel { display:grid; grid-template-columns:max-content 1fr; gap:4px 10px; align-items:center;
        margin-bottom:18px; }
 .sel .k { color:var(--dim); text-align:right; }
 .sel button { font:inherit; color:inherit; background:none; border:1px solid var(--line);
               padding:1px 8px; margin-right:4px; cursor:pointer; }
 .sel button.on { border-color:var(--fg); background:var(--fg); color:var(--bg); }
 .sel button:disabled { opacity:.25; cursor:default; }
 table { border-collapse:collapse; }
 th { font-weight:400; color:var(--dim); padding:2px 8px 2px 0; text-align:right; white-space:nowrap; }
 td { padding:0; }
 /* La colonna e' larga quanto serve alla piu' lunga delle etichette X, uguale
    per tutte: i numeri sotto la griglia restano equidistanziati e leggibili.
    --cw lo calcola drawGrid in caratteri (font monospace, unita' ch). */
 #grid { overflow-x:auto; }
 .cell { width:32px; height:32px; border:1px solid var(--line); background:none;
         color:inherit; font:inherit; cursor:pointer; padding:0; }
 td { text-align:center; }
 col.v { width:calc(var(--cw) * 1ch + 10px); }
 .cell:hover { border-color:var(--fg); }
 .cell.on { background:var(--on); border-color:var(--on); }
 .cell.void { border-style:dotted; opacity:.25; cursor:default; }
 .xlab { font-size:10px; color:var(--dim); text-align:center; padding-top:5px;
         white-space:nowrap; }
 #now { margin-top:18px; min-height:3em; }
 #now .file { color:var(--dim); }
 audio { margin-top:6px; width:340px; }
 #miss { color:var(--dim); margin-top:18px; }
</style>
<h1 id="h"></h1>
<div class="sel" id="sel"></div>
<div id="grid"></div>
<div id="now"></div>
<audio id="a" controls></audio>
<script>
const D = __DATA__;
const byLabel = {};
for (const c of D.combos) byLabel[c.label] = c;

// Selezione corrente: gli assi esterni della prima combinazione renderizzata.
let sel = Object.assign({}, D.combos[0].sel);
let cur = D.combos[0];
let cx = 0, cy = 0;

function match(s) {
  return D.combos.find(c => D.keys.every(k => c.sel[k] === s[k]));
}

function drawSel() {
  const box = document.getElementById("sel");
  box.innerHTML = "";
  for (const k of D.keys) {
    const kd = document.createElement("div");
    kd.className = "k"; kd.textContent = k;
    const vd = document.createElement("div");
    for (const v of D.values[k]) {
      const b = document.createElement("button");
      b.textContent = v;
      if (sel[k] === v) b.classList.add("on");
      // Disabilitato se cambiando SOLO questa chiave non esiste una
      // combinazione renderizzata: il disco decide cosa e' raggiungibile.
      const probe = Object.assign({}, sel); probe[k] = v;
      if (!match(probe)) b.disabled = true;
      else b.onclick = () => { sel[k] = v; show(match(sel)); };
      vd.appendChild(b);
    }
    box.appendChild(kd); box.appendChild(vd);
  }
}

function key(x, y) { return x + "|" + y; }

// Etichette: cinque decimali, senza zeri di coda. `0.000020833333333333333`
// diventa `0.00002` — il valore esatto resta nel nome del file, che e' la
// fonte di verita'. Sotto i cinque decimali si passa all'esponenziale invece
// di mostrare uno zero che sarebbe falso.
function fmt(v) {
  if (v === 0) return "0";
  const r = Number(v.toFixed(5));
  return r === 0 ? v.toExponential(1) : String(r);
}

function drawGrid() {
  const at = {};
  for (const n of cur.nodes) at[key(n.coords[cur.axX], cur.axY ? n.coords[cur.axY] : 0)] = n;
  cur.at = at;
  const t = document.createElement("table");
  const labels = cur.xs.map(fmt);
  t.style.setProperty("--cw", Math.max(...labels.map(l => l.length)));
  // Una <col> per colonna: la larghezza vale sia per le celle sia per le
  // etichette, cosi' le due file restano allineate.
  const cg = document.createElement("colgroup");
  cg.appendChild(document.createElement("col"));
  for (let i = 0; i < cur.xs.length; i++) {
    const c = document.createElement("col");
    c.className = "v";
    cg.appendChild(c);
  }
  t.appendChild(cg);
  // Riga per riga dall'alto: y cresce verso l'alto, come su un grafico.
  for (let j = cur.ys.length - 1; j >= 0; j--) {
    const tr = t.insertRow();
    const th = document.createElement("th");
    th.textContent = cur.axY ? fmt(cur.ys[j]) : "";
    tr.appendChild(th);
    for (let i = 0; i < cur.xs.length; i++) {
      const b = document.createElement("button");
      b.className = "cell";
      const n = at[key(cur.xs[i], cur.ys[j])];
      if (!n) { b.classList.add("void"); b.disabled = true; }
      else { b.title = n.name; b.onclick = () => go(i, j); }
      b.dataset.i = i; b.dataset.j = j;
      tr.insertCell().appendChild(b);
    }
  }
  const foot = t.insertRow();
  foot.appendChild(document.createElement("th"));
  for (const l of labels) {
    const td = foot.insertCell();
    td.className = "xlab";
    td.textContent = l;
  }
  const box = document.getElementById("grid");
  box.innerHTML = "";
  box.appendChild(t);
}

const audio = document.getElementById("a");

function go(i, j, play) {
  const n = cur.at[key(cur.xs[i], cur.ys[j])];
  cx = i; cy = j;
  for (const b of document.querySelectorAll(".cell")) b.classList.remove("on");
  const b = document.querySelector(`.cell[data-i="${i}"][data-j="${j}"]`);
  if (b) b.classList.add("on");
  if (!n) { document.getElementById("now").textContent = "(non renderizzato)"; return; }
  document.getElementById("now").innerHTML =
    "<b>" + cur.axX + " = " + fmt(cur.xs[i]) + "</b>" +
    (cur.axY ? " &nbsp; <b>" + cur.axY + " = " + fmt(cur.ys[j]) + "</b>" : "") +
    "<br><span class='file'>" + n.name + "</span>";
  audio.src = n.src;
  if (play !== false) audio.play();
}

function show(c) {
  if (!c) return;
  cur = c;
  document.getElementById("h").textContent =
    D.study + "   " + cur.axX + (cur.axY ? " x " + cur.axY : "");
  drawSel();
  drawGrid();
  // La cella resta dov'era, clampata alla nuova griglia: cambiare un asse
  // esterno e' un A/B sullo stesso punto, non un salto altrove.
  go(Math.min(cx, cur.xs.length - 1), Math.min(cy, cur.ys.length - 1), false);
}

addEventListener("keydown", e => {
  const d = {ArrowRight:[1,0], ArrowLeft:[-1,0], ArrowUp:[0,1], ArrowDown:[0,-1]}[e.key];
  if (!d) return;
  e.preventDefault();
  go(Math.min(cur.xs.length - 1, Math.max(0, cx + d[0])),
     Math.min(cur.ys.length - 1, Math.max(0, cy + d[1])));
});

show(cur);
</script>
"""
