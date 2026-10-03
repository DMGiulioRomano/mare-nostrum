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
posto dove la sintassi puo' divergere. L'unica cosa che il server CHIEDE
all'engine e' cosa lo stream ha davvero fatto (``engine_bridge.
stream_analysis``: le curve realizzate e i grani), che torna nella risposta
del render — nel documento non c'e', la sa solo chi l'ha caricato.

    POST /pick    {"mode": "open"|"save", "name": "..."}
    -> {"path": "/Users/.../stream.yml"}   pannello nativo del Finder
    POST /open    {"path": "..."}   -> {"doc": {...}}
    POST /render  {"doc": {...}, "path": "...", "render": true, "ascolto": {...}}
    -> {"yaml": "...", "src": "...", "inviluppi": [...], "grani": {...}}
                  (``ascolto``, facoltativo: il documento da rendere, se non
                  e' quello da salvare — vedi ``render_doc``)

Il "file di progetto" e' lo YAML stesso: un documento engine puro, che si
riapre qui, si incolla nel brano o si apre in PGE-ui. Un secondo formato per
ricordare i breakpoint non serve — i breakpoint SONO gli inviluppi.

I pannelli Apri/Salva sono quelli veri di macOS: il server gira sulla stessa
macchina e li chiede a ``osascript``, cosa che la pagina da sola non puo'
fare (Safari non ha le File System Access API, e un ``<input type=file>``
darebbe il contenuto ma non il percorso su cui risalvare). Il file si sceglie
dove si vuole: lo studio non e' piu' l'unico posto dove puo' stare uno stream.

Solo su 127.0.0.1: scrive file ed esegue un processo, non e' roba da esporre.
"""
from __future__ import annotations

import json
import os
import posixpath
import re
import signal
import subprocess
import sys
import time
from functools import partial
from typing import Any, Dict, Tuple
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

import yaml

LIVE = "live"          # sottocartella degli stream composti a mano
SAMPLES = "/samples/"  # i sample del repo, che stanno fuori dallo studio
# Il nome che `translate_path` restituisce quando la richiesta esce dalla
# cartella dei sample: un file che non c'e' e' un 404, che e' la risposta
# giusta. (Un carattere illegale darebbe un 500 con stack trace.)
_FUORI = "fuori-dalla-cartella-dei-sample"
_SAFE = re.compile(r"[^A-Za-z0-9._-]")


# Solo i percorsi usciti da un pannello di questa sessione si possono leggere
# e scrivere: il dialogo nativo E' l'autorizzazione dell'utente, e senza questo
# vincolo un POST basterebbe a scrivere ovunque sul disco.
_AUTORIZZATI: set = set()


def pannello(mode: str, name: str = "stream.yml", start: str = "") -> Tuple[str, str]:
    """Il pannello Apri/Salva di macOS. Ritorna ``(path, errore)``.

    Path vuoto ed errore vuoto = annullato: l'utente ha cambiato idea, non e'
    successo niente. Path vuoto con un errore = il pannello non si e' aperto
    (non siamo su macOS, o osascript non ha il permesso di mostrare dialoghi),
    ed e' una cosa che la pagina deve dire invece di non reagire — sono due
    silenzi identici a schermo e cause opposte.

    ``osascript`` blocca finche' l'utente non risponde: gira in un thread del
    server (ThreadingHTTPServer), quindi la pagina resta viva nel frattempo.
    """
    loc = f' default location POSIX file "{start}"' if os.path.isdir(start) else ""
    if mode == "save":
        scelta = (f'choose file name with prompt "Salva lo stream"'
                  f' default name "{name}"{loc}')
    else:
        scelta = (f'choose file with prompt "Apri uno stream"'
                  f' of type {{"yml", "yaml"}}{loc}')
    # Niente `tell me to activate`: `choose file` porta il pannello davanti da
    # se' (misurato: frontmost in 1.6s), mentre l'activate trasforma prima
    # l'eseguibile in applicazione con interfaccia e costa altri 3 secondi —
    # erano i 5 secondi fra il click e il pannello.
    #
    # NON passare da `tell application "System Events"`: senza il permesso di
    # Automazione quello risponde "User cancelled (-128)" dopo due secondi
    # senza aver mostrato niente, che e' esattamente il silenzio da evitare.
    script = f'POSIX path of ({scelta})'
    try:
        p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as e:
        return "", f"non riesco ad aprire il pannello: {e}"
    if p.returncode != 0:
        err = (p.stderr or "").strip()
        # -128 e' "User canceled": l'unico non-errore fra i codici di osascript.
        if "-128" in err or "canceled" in err.lower():
            return "", ""
        return "", err or "il pannello non si e' aperto"
    path = p.stdout.strip()
    if path:
        _AUTORIZZATI.add(os.path.abspath(path))
        recenti_aggiungi(path)
    return path, ""


def autorizzato(path: str) -> bool:
    return os.path.abspath(path) in _AUTORIZZATI


# Questo avvio del server. La pagina se lo fa dire e ci confronta la bozza in
# localStorage: un refresh riprende il lavoro non salvato, un `make serve`
# nuovo parte da foglio bianco — che e' quello che si vuole aprendo il
# laboratorio, non l'ultima cosa rimasta a meta'.
SESSIONE = f"{os.getpid()}-{time.time()}"

# I file usciti da un pannello, il piu' recente in testa. La lista sopravvive
# al riavvio (un JSON accanto alla pagina) ed E' anche l'autorizzazione: un
# file che l'utente ha gia' scelto in un pannello resta suo, altrimenti un
# recente si potrebbe elencare ma non aprire.
RECENTI = 3
_RECENTI: list = []
_RECENTI_PATH = ""


def recenti_carica(gen_root: str) -> None:
    global _RECENTI_PATH
    _RECENTI_PATH = os.path.join(gen_root, ".recenti.json")
    try:
        with open(_RECENTI_PATH) as fh:
            v = json.load(fh)
    except (OSError, ValueError):
        v = []
    # Un file cancellato o spostato non e' piu' un recente: elencarlo
    # significa offrire un'apertura che fallisce.
    _RECENTI[:] = [p for p in v if isinstance(p, str) and os.path.isfile(p)][:RECENTI]
    _AUTORIZZATI.update(os.path.abspath(p) for p in _RECENTI)


def recenti_aggiungi(path: str) -> None:
    p = os.path.abspath(path)
    _RECENTI[:] = ([p] + [q for q in _RECENTI if q != p])[:RECENTI]
    try:
        with open(_RECENTI_PATH, "w") as fh:
            json.dump(_RECENTI, fh)
    except OSError:
        pass            # senza posto dove scriverli restano quelli di adesso


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
               renderer: str = "numpy", render: bool = True,
               path: str = "", ascolto: dict | None = None) -> dict:
    """Scrive lo YAML e (se ``render``) lo rende accanto, in .aif.

    Con ``path`` scrive dove l'utente ha detto nel pannello di salvataggio;
    senza, in ``<gen_root>/live/<name>.yml`` come prima. L'audio nasce sempre
    accanto allo YAML, con lo stesso nome: due file che si spostano insieme.

    ``ascolto``, se diverso da ``doc``, e' cio' che si rende al posto suo: lo
    decide la pagina (uno stream aperto dal brano si salva col suo ``onset``
    e il suo ``mute``, ma si ascolta da solo e da zero). Il server non sa
    perche': scrive il secondo documento in ``logs/`` e rende quello.

    Il percorso dell'engine e dei sample e' relativo alla radice del repo:
    ``main.py`` risolve ``samples-dir`` da dove gira, non da dove sta lo YAML.
    """
    if path:
        if not autorizzato(path):
            return {"ok": False, "error": "percorso non scelto da un pannello: "
                                          "usa 'salva con nome'."}
        doc_path = path if path.endswith((".yml", ".yaml")) else path + ".yml"
        base = os.path.dirname(doc_path)
        out_path = os.path.splitext(doc_path)[0] + ".aif"
        os.makedirs(os.path.join(base, "logs"), exist_ok=True)
        live = base
    else:
        stem = _SAFE.sub("_", name) or "senza-nome"
        live = os.path.join(gen_root, LIVE)
        os.makedirs(os.path.join(live, "logs"), exist_ok=True)
        doc_path = os.path.join(live, stem + ".yml")
        out_path = os.path.join(live, stem + ".aif")
    with open(doc_path, "w") as fh:
        yaml.dump(doc, fh, Dumper=_Dumper, sort_keys=False, allow_unicode=True)
    def _rel(p: str) -> str:
        """Il path come lo usa la pagina: relativo se sta sotto lo studio
        (l'audio va caricato via HTTP), assoluto se l'utente l'ha messo
        altrove — e li' la pagina lo mostra e basta."""
        r = os.path.relpath(p, gen_root)
        return r if not r.startswith("..") else p

    # Salvare e' immediato, rendere no: si tiene il lavoro senza aspettare.
    if not render:
        return {"ok": True, "src": None, "yaml": _rel(doc_path), "path": doc_path}
    src_path = doc_path
    if ascolto is not None and ascolto != doc:
        src_path = os.path.join(live, "logs",
                                os.path.splitext(os.path.basename(doc_path))[0] + ".ascolto.yml")
        with open(src_path, "w") as fh:
            yaml.dump(ascolto, fh, Dumper=_Dumper, sort_keys=False, allow_unicode=True)
    cmd = [sys.executable, os.path.join(repo_root, "engine", "src", "main.py"),
           src_path, out_path,
           "--renderer", renderer,
           "--samples-dir", os.path.join(repo_root, "samples"),
           "--log-dir", os.path.join(live, "logs")]
    p = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    if p.returncode != 0:
        # Le ultime righe: l'errore dell'engine sta in fondo, e la pagina lo
        # mostra in una riga di stato, non in un pannello.
        tail = (p.stderr or p.stdout).strip().splitlines()[-12:]
        return {"ok": False, "error": "\n".join(tail)}
    return {"ok": True, "src": _rel(out_path), "yaml": _rel(doc_path),
            "path": doc_path, **_analisi(src_path, repo_root, live)}


def _analisi(doc_path: str, repo_root: str, live: str) -> dict:
    """Curve realizzate e grani dello stream, per i pannelli sotto lo spectroscope.

    Le chiede all'engine dopo il render, ricaricando lo YAML appena scritto:
    sono quelle della IR, non quelle del documento — ci sono dentro anche le
    derivate (``effective_density``), gli offset per-voce e i grani veri, che
    nel documento non ci sono affatto.

    ponytail: un ascolto non deve fallire perche' il disegno non si sa fare,
    quindi qualunque inciampo qui vale "niente da disegnare". E il documento
    del laboratorio non porta un ``seed``, quindi le curve di una strategia
    **stocastica** sono un'altra estrazione rispetto a quella che ha suonato:
    scrivere il seed nel documento, se dara' fastidio.
    """
    from . import engine_bridge

    try:
        return engine_bridge.stream_analysis(
            doc_path, os.path.join(repo_root, "samples"),
            log_dir=os.path.join(live, "logs"))
    except Exception:
        return {"inviluppi": [], "grani": None}


class Handler(SimpleHTTPRequestHandler):
    """GET come ``http.server``; l'unico POST e' il render."""

    repo_root = ""

    def do_POST(self):                      # noqa: N802  (nome dell'API stdlib)
        rotta = self.path.rstrip("/")
        if rotta not in ("/render", "/pick", "/open", "/stato"):
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError as e:
            self._json({"ok": False, "error": f"richiesta non valida: {e}"}, 400)
            return
        if rotta == "/stato":
            self._json({"ok": True, "sessione": SESSIONE, "recenti": list(_RECENTI)})
            return
        if rotta == "/pick":
            # Si parte dalla cartella del file aperto, o da quella dello studio.
            start = body.get("start") or os.path.join(self.directory, LIVE)
            path, err = pannello(body.get("mode", "open"),
                                 body.get("name") or "stream.yml", start)
            self._json({"ok": not err, "path": path, "error": err})
            return
        if rotta == "/open":
            path = body.get("path", "")
            if not autorizzato(path):
                self._json({"ok": False, "error": "apri il file dal pannello."}, 403)
                return
            try:
                with open(path) as fh:
                    self._json({"ok": True, "doc": yaml.safe_load(fh), "path": path})
            except (OSError, yaml.YAMLError) as e:
                self._json({"ok": False, "error": f"non riesco a leggerlo: {e}"})
            return
        try:
            doc = body["doc"]
        except KeyError as e:
            self._json({"ok": False, "error": f"richiesta non valida: {e}"}, 400)
            return
        self._json(render_doc(doc, body.get("name", "live"), self.directory,
                              self.repo_root, render=body.get("render", True),
                              path=body.get("path", ""), ascolto=body.get("ascolto")))

    def translate_path(self, path):
        """Come la stdlib, ma ``/samples/<file>`` esce dallo studio.

        I sample stanno in ``<repo>/samples`` e la pagina e' servita dalla
        cartella dello studio: senza questo, sentire un sample prima di
        sceglierlo nel laboratorio sarebbe l'unica cosa che richiede di
        renderizzare qualcosa.
        """
        p = path.split("?")[0].split("#")[0]
        if not p.startswith(SAMPLES):
            return super().translate_path(path)
        base = os.path.join(self.repo_root, "samples")
        rel = posixpath.normpath(unquote(p[len(SAMPLES):])).lstrip("/")
        full = os.path.abspath(os.path.join(base, rel))
        # `..` porta fuori dalla cartella dei sample: un nome che non esiste
        # (404) invece di un file del disco.
        return full if full.startswith(base + os.sep) else os.path.join(base, _FUORI)

    def end_headers(self):
        # La pagina e l'elenco cambiano a ogni `graph` e a ogni salvataggio, e
        # La pagina si riscrive a ogni `graph`, e il browser che ne tiene una
        # copia mostra un laboratorio vecchio senza dirlo. L'audio no: ha un
        # nome nuovo o un `?t=`, e ricaricarlo a ogni seek sarebbe uno spreco.
        if self.path.split("?")[0].endswith(".html"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, payload: dict, code: int = 200):
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass                                 # la console del terminale resta pulita


def crea(gen_root: str, repo_root: str, port: int = 8000) -> ThreadingHTTPServer:
    """Prende la porta. Separata da ``serve`` perche' e' qui che si fallisce:
    l'URL va stampato dopo, non prima di sapere se la porta e' libera.

    Threading: un render dura secondi o minuti e con un server a thread
    singolo bloccherebbe anche il caricamento dell'audio gia' pronto.
    """
    Handler.repo_root = os.path.abspath(repo_root)
    recenti_carica(gen_root)
    return ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=gen_root))


def serve(gen_root: str, repo_root: str, port: int = 8000):
    crea(gen_root, repo_root, port).serve_forever()


def pid_sulla_porta(port: int) -> int | None:
    """Chi tiene la porta. ``lsof`` e' l'unico che lo sa, e c'e' ovunque."""
    try:
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=5).stdout
        righe = out.strip().splitlines()[1:]
        if righe:
            return int(righe[0].split()[1])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    return None


def _e_un_nostro_serve(pid: int) -> bool:
    """Se quel processo e' un ``granstudies serve``, e non qualcos'altro.

    E' la domanda che autorizza il kill: un server nostro rimasto orfano si
    chiude senza chiedere niente, ma sulla stessa porta puo' esserci il lavoro
    di qualcun altro, e quello non si tocca.
    """
    try:
        cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "granstudies" in cmd and "serve" in cmd.split()


def libera_porta(port: int) -> int | None:
    """Chiude il ``granstudies serve`` orfano che tiene la porta, e dice chi era.

    Capita di continuo: si chiude la finestra di Safari, il terminale se ne va,
    e il server di ieri e' ancora li'. Non e' un altro lavoro, e' il proprio
    lavoro di prima: chiederne conferma ogni volta sarebbe solo un passaggio in
    piu'. Restituisce ``None`` se la porta e' di qualcun altro — quello non si
    tocca, e chi chiama lo dice all'utente.
    """
    pid = pid_sulla_porta(port)
    if pid is None or pid == os.getpid() or not _e_un_nostro_serve(pid):
        return None
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return None
    # Il tempo di mollare il socket. Se non molla (render in corso in un
    # thread), SIGKILL: la porta serve adesso.
    for _ in range(20):
        time.sleep(0.1)
        if pid_sulla_porta(port) != pid:
            return pid
    try:
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.3)
    except OSError:
        pass
    return pid


def porta_occupata(port: int) -> str:
    """Chi tiene la porta, per dirlo invece di stampare uno stack trace."""
    pid = pid_sulla_porta(port)
    if pid is not None:
        return (f"la porta {port} e' gia' occupata dal processo {pid}: "
                f"chiudilo con 'kill {pid}', o usa 'make serve PORT=<altra>'.")
    return (f"la porta {port} e' gia' occupata: chiudi l'altro server, "
            f"o usa 'make serve PORT=<altra>'.")
