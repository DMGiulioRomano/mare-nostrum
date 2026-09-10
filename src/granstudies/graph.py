"""Rete navigabile delle varianti discrete: un HTML autonomo per combinazione.

In ``mode: discrete`` lo sweep produce un file per punto della griglia e il
nome porta le coordinate (``o2__grain.duration=0.001__pitch.ratio=0.447``).
Qui quei nomi si rileggono e diventano una griglia cliccabile: ogni cella
suona il suo file, le frecce si spostano fra celle vicine, e i link in fondo
portano alle altre combinazioni di ``for_each:``.

Nessuna dipendenza e nessun server: l'HTML sta accanto all'audio e lo carica
con path relativi.
"""
from __future__ import annotations

import html
import json
import os
from typing import Any, Dict, List


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


def collect_nodes(audio_dir: str) -> List[Dict[str, Any]]:
    """Un nodo per ogni .aif sotto ``audio_dir``, con coordinate e path relativo.

    Scende ricorsivamente perche' il layout sotto ``discrete/`` puo' avere un
    livello di stream_id (vedi ``render.render_variants``).
    """
    nodes: List[Dict[str, Any]] = []
    for root, _dirs, files in os.walk(audio_dir):
        for f in sorted(files):
            if not f.endswith(".aif"):
                continue
            coords = parse_coords(os.path.splitext(f)[0])
            if not coords:
                continue
            nodes.append({
                "name": os.path.splitext(f)[0],
                "src": os.path.relpath(os.path.join(root, f), audio_dir),
                "coords": coords,
            })
    return nodes


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


def build_html(study: str, label: str, nodes: List[Dict[str, Any]],
               siblings: List[str], order: List[str] | None = None) -> str:
    axes = axes_of(nodes, order)
    ax_x = axes[0] if axes else ""
    ax_y = axes[1] if len(axes) > 1 else ""
    xs = sorted({n["coords"][ax_x] for n in nodes if ax_x in n["coords"]})
    ys = sorted({n["coords"].get(ax_y, 0) for n in nodes}) if ax_y else [0]
    data = {
        "study": study, "label": label,
        "axX": ax_x, "axY": ax_y, "xs": xs, "ys": ys,
        "nodes": nodes,
        "siblings": siblings,
    }
    return _TEMPLATE.replace("__TITLE__", html.escape(f"{study} — {label or 'rete'}")) \
                    .replace("__DATA__", json.dumps(data))


def write_graph(study: str, label: str, audio_dir: str, out_path: str,
                siblings: List[str], order: List[str] | None = None) -> int:
    """Scrive ``out_path``. Ritorna il numero di nodi (0 = niente audio).

    L'HTML sta accanto all'audio (``audio/sweep/discrete/graph.html``) perche'
    i ``src`` sono relativi a li': aprendolo da ``file://`` suona senza server.
    """
    nodes = collect_nodes(audio_dir)
    if not nodes:
        return 0
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as fh:
        fh.write(build_html(study, label, nodes, siblings, order))
    return len(nodes)


_TEMPLATE = """<!doctype html>
<meta charset="utf-8"><title>__TITLE__</title>
<style>
 :root { color-scheme: light dark; --bg:#fff; --fg:#111; --line:#ccc; --on:#c33; }
 @media (prefers-color-scheme: dark) { :root { --bg:#141414; --fg:#eee; --line:#444; } }
 body { background:var(--bg); color:var(--fg); font:13px/1.4 ui-monospace,monospace; margin:20px; }
 h1 { font-size:14px; font-weight:600; margin:0 0 2px; }
 .sub { opacity:.6; margin-bottom:16px; word-break:break-all; }
 table { border-collapse:collapse; }
 th { font-weight:400; opacity:.7; padding:2px 6px; text-align:right; white-space:nowrap; }
 td { padding:0; }
 .cell { width:34px; height:34px; border:1px solid var(--line); background:none;
         color:inherit; font:inherit; cursor:pointer; }
 .cell:hover { border-color:var(--fg); }
 .cell.on { background:var(--on); border-color:var(--on); color:#fff; }
 .cell.void { border-style:dotted; opacity:.3; cursor:default; }
 #now { margin-top:16px; min-height:2.4em; }
 #now b { font-weight:600; }
 audio { margin-top:8px; width:340px; }
 .sib { margin-top:24px; border-top:1px solid var(--line); padding-top:10px; opacity:.75; }
 .sib a { display:block; color:inherit; }
</style>
<h1 id="h"></h1>
<div class="sub" id="s"></div>
<table id="grid"></table>
<div id="now">clicca una cella, o muoviti con le frecce</div>
<audio id="a" controls></audio>
<div class="sib" id="sib"></div>
<script>
const D = __DATA__;
const at = {};
for (const n of D.nodes) at[key(n.coords[D.axX], D.axY ? n.coords[D.axY] : 0)] = n;
function key(x, y) { return x + "|" + y; }
document.getElementById("h").textContent = D.study + (D.axY ? "  " + D.axX + " x " + D.axY : "  " + D.axX);
document.getElementById("s").textContent = D.label || "(nessun asse esterno)";

let cx = 0, cy = 0;
const t = document.getElementById("grid");
// Riga per riga dall'alto: y cresce verso l'alto, come su un grafico.
for (let j = D.ys.length - 1; j >= 0; j--) {
  const tr = t.insertRow();
  const th = document.createElement("th");
  th.textContent = D.axY ? D.ys[j] : "";
  tr.appendChild(th);
  for (let i = 0; i < D.xs.length; i++) {
    const td = tr.insertCell();
    const b = document.createElement("button");
    b.className = "cell";
    const n = at[key(D.xs[i], D.ys[j])];
    if (!n) { b.classList.add("void"); b.disabled = true; }
    else { b.title = n.name; b.onclick = () => go(i, j); }
    b.dataset.i = i; b.dataset.j = j;
    td.appendChild(b);
  }
}
const foot = t.insertRow();
foot.appendChild(document.createElement("th"));
for (const x of D.xs) {
  const td = foot.insertCell();
  td.style.cssText = "font-size:9px;opacity:.6;text-align:center;padding-top:3px";
  td.textContent = x;
}

const audio = document.getElementById("a");
function go(i, j) {
  const n = at[key(D.xs[i], D.ys[j])];
  if (!n) return;
  cx = i; cy = j;
  for (const b of document.querySelectorAll(".cell")) b.classList.remove("on");
  document.querySelector(`.cell[data-i="${i}"][data-j="${j}"]`).classList.add("on");
  document.getElementById("now").innerHTML =
    "<b>" + D.axX + " = " + D.xs[i] + "</b>" + (D.axY ? " &nbsp; <b>" + D.axY + " = " + D.ys[j] + "</b>" : "") +
    "<br><span style='opacity:.6'>" + n.name + "</span>";
  audio.src = n.src;
  audio.play();
}
addEventListener("keydown", e => {
  const d = {ArrowRight:[1,0], ArrowLeft:[-1,0], ArrowUp:[0,1], ArrowDown:[0,-1]}[e.key];
  if (!d) return;
  e.preventDefault();
  const i = Math.min(D.xs.length - 1, Math.max(0, cx + d[0]));
  const j = Math.min(D.ys.length - 1, Math.max(0, cy + d[1]));
  go(i, j);
});
const sib = document.getElementById("sib");
if (D.siblings.length) {
  sib.innerHTML = "<div style='margin-bottom:4px'>altre combinazioni:</div>";
  for (const s of D.siblings) {
    const a = document.createElement("a");
    a.href = "../" + s + "/graph.html";
    a.textContent = s;
    sib.appendChild(a);
  }
}
</script>
"""
