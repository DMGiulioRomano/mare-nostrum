"""Il server della pagina: file statici piu' un render on demand.

``http.server`` bastava finche' la pagina serviva solo a scegliere fra audio
gia' renderizzati. Il laboratorio del singolo stream chiede l'inverso: si
compone uno stream nella pagina — i breakpoint pescati dalle liste di valori
dello studio — e lo si vuole *sentire*, cioe' scritto in YAML e reso, senza
passare dalla griglia combinatoria (che per 001-41 sarebbe un milione di
render).

Il server non sa niente di stream: riceve il **documento engine gia' fatto**
come JSON, lo scrive in YAML e chiama l'engine. Tutta la conoscenza del
dominio resta nella pagina, che e' dove si compone, e qui non c'e' un secondo
posto dove la sintassi puo' divergere.

    POST /render  {"name": "prova1", "doc": {...}}
    -> {"src": "live/prova1.aif", "yaml": "live/prova1.yml"}

Solo su 127.0.0.1: scrive file ed esegue un processo, non e' roba da esporre.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import yaml

LIVE = "live"          # sottocartella degli stream composti a mano
_SAFE = re.compile(r"[^A-Za-z0-9._-]")


class _Dumper(yaml.SafeDumper):
    """Come SafeDumper, ma le liste di numeri restano su una riga.

    Un inviluppo a breakpoint in block style diventa quaranta righe di
    trattini: `[[0, 0.001], [0.5, 0.02]]` e' la forma in cui questi documenti
    si leggono a colpo d'occhio, ed e' quella che hanno scritti a mano.
    """


def _flow_if_flat(dumper, data):
    flat = all(isinstance(v, (int, float)) for v in data)
    nested = all(isinstance(v, list) and len(v) <= 3 for v in data) and bool(data)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data,
                                     flow_style=flat or nested)


_Dumper.add_representer(list, _flow_if_flat)


def render_doc(doc: dict, name: str, gen_root: str, repo_root: str,
               renderer: str = "numpy") -> dict:
    """Scrive ``<gen_root>/live/<name>.yml`` e lo rende accanto, in .aif.

    Il percorso dell'engine e dei sample e' relativo alla radice del repo:
    ``main.py`` risolve ``samples-dir`` da dove gira, non da dove sta lo YAML.
    """
    stem = _SAFE.sub("_", name) or "senza-nome"
    live = os.path.join(gen_root, LIVE)
    os.makedirs(os.path.join(live, "logs"), exist_ok=True)
    doc_path = os.path.join(live, stem + ".yml")
    out_path = os.path.join(live, stem + ".aif")
    with open(doc_path, "w") as fh:
        yaml.dump(doc, fh, Dumper=_Dumper, sort_keys=False, allow_unicode=True)
    cmd = [sys.executable, os.path.join(repo_root, "engine", "src", "main.py"),
           doc_path, out_path,
           "--renderer", renderer,
           "--samples-dir", os.path.join(repo_root, "samples"),
           "--log-dir", os.path.join(live, "logs")]
    p = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    if p.returncode != 0:
        # Le ultime righe: l'errore dell'engine sta in fondo, e la pagina lo
        # mostra in una riga di stato, non in un pannello.
        tail = (p.stderr or p.stdout).strip().splitlines()[-12:]
        return {"ok": False, "error": "\n".join(tail)}
    return {"ok": True,
            "src": f"{LIVE}/{stem}.aif",
            "yaml": f"{LIVE}/{stem}.yml"}


class Handler(SimpleHTTPRequestHandler):
    """GET come ``http.server``; l'unico POST e' il render."""

    repo_root = ""

    def do_POST(self):                      # noqa: N802  (nome dell'API stdlib)
        if self.path.rstrip("/") != "/render":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            doc, name = body["doc"], body.get("name", "live")
        except (ValueError, KeyError) as e:
            self._json({"ok": False, "error": f"richiesta non valida: {e}"}, 400)
            return
        self._json(render_doc(doc, name, self.directory, self.repo_root))

    def _json(self, payload: dict, code: int = 200):
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass                                 # la console del terminale resta pulita


def serve(gen_root: str, repo_root: str, port: int = 8000):
    handler = partial(Handler, directory=gen_root)
    Handler.repo_root = os.path.abspath(repo_root)
    # Threading: un render dura minuti e con il server a thread singolo
    # bloccherebbe anche il caricamento dell'audio gia' pronto.
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
