"""Il JS della pagina: che sia sintatticamente valido e che la FFT sia giusta.

Gira solo dove c'e' `node`. La STFT e' l'unico pezzo di matematica della
pagina, ed e' anche l'unico che puo' sbagliare in silenzio: uno spettrogramma
storto si guarda senza accorgersene. Il resto (canvas, cursori) e' verificabile
solo a occhio e resta fuori.
"""
import os
import shutil
import subprocess

import pytest

from granstudies.graph import _TEMPLATE_PATH

node = pytest.mark.skipif(shutil.which("node") is None, reason="serve node")


def _script() -> str:
    s = open(_TEMPLATE_PATH).read()
    return s[s.index("<script>") + len("<script>"):s.index("</script>")]


def _run(extra: str, tmp_path) -> str:
    js = _script()
    js = js[js.index("const twiddles"):js.index("function mixdown")]
    p = tmp_path / "t.js"
    p.write_text(js + extra)
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


@node
def test_il_javascript_della_pagina_e_sintatticamente_valido(tmp_path):
    p = tmp_path / "page.js"
    p.write_text(_script().replace("__DATA__", "{keys:[],values:{},combos:[]}"))
    out = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


@node
@pytest.mark.parametrize("nfft", [256, 512, 1024, 2048, 4096, 8192])
def test_la_stft_mette_il_picco_alla_frequenza_giusta(tmp_path, nfft):
    """Seno a 1000 Hz: il bin di massima energia vale ~1000 Hz, a ogni finestra.

    Vale per tutte le risoluzioni offerte dalla pagina: cambiare finestra
    cambia la precisione, non la taratura.
    """
    got = _run("""
const rate = 48000, f = 1000, N = %d * 8, NFFT = %d;
const x = new Float32Array(N);
for (let i = 0; i < N; i++) x[i] = Math.sin(2 * Math.PI * f * i / rate);
const s = stft(x, NFFT);
let best = 0;
for (let b = 0; b < s.bins; b++) if (s.db[b] > s.db[best]) best = b;
const far = Math.round(s.bins * 0.9);
console.log((best * (rate / 2) / s.bins).toFixed(1), s.db[best].toFixed(2), s.db[far].toFixed(1));
""" % (nfft, nfft), tmp_path)
    hz, peak_db, far_db = (float(v) for v in got.split())
    assert abs(hz - 1000) <= 48000 / nfft   # entro una risoluzione di bin
    assert -8 < peak_db < -5                # ampiezza 1, ~6 dB tolti dalla finestra di Hann
    assert far_db == -96                    # lontano dal picco si sta sul floor


@node
def test_l_hop_e_un_quarto_della_finestra_a_ogni_risoluzione(tmp_path):
    """Il numero di colonne segue l'hop: quattro volte piu' fitto per ottava."""
    got = _run("""
const x = new Float32Array(48000);
console.log([512, 1024, 2048].map(n => stft(x, n).cols).join(" "));
""", tmp_path)
    c512, c1024, c2048 = (int(v) for v in got.split())
    assert abs(c512 / c1024 - 2) < 0.05
    assert abs(c1024 / c2048 - 2) < 0.05


@node
def test_la_stft_tiene_la_continua_nel_bin_zero(tmp_path):
    got = _run("""
const s = stft(new Float32Array(2048 * 4).fill(1), 2048);
console.log(s.db[0].toFixed(1), s.db[50].toFixed(1));
""", tmp_path)
    dc_db, far_db = (float(v) for v in got.split())
    assert abs(dc_db) < 0.5
    assert far_db == -96


@node
def test_il_breakpoint_va_solo_dove_il_valore_cambia(tmp_path):
    """Un punto uguale a quello prima e a quello dopo non dice niente in piu'.

    Ed e' la regola che tiene leggibile lo YAML del laboratorio: dodici
    parametri per breakpoint, ma nell'inviluppo di ognuno solo i punti dove
    quel parametro si muove davvero.
    """
    js = _script()
    js = js[js.index("function serie"):js.index("function labDoc")]
    p = tmp_path / "s.js"
    p.write_text("let bps = [\n"
                 " {t:0,   vals:{a:1, b:5, c:9}},\n"
                 " {t:0.5, vals:{a:1, b:7, c:9}},\n"
                 " {t:1,   vals:{a:2, b:7, c:9}}];\n"
                 + js +
                 "console.log(JSON.stringify([serie('a'), serie('b'), serie('c')]));")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    a, b, c = __import__("json").loads(out.stdout)
    # a: il punto di mezzo e' uguale al precedente ma non al successivo -> resta
    # (senza, la rampa partirebbe da t=0 invece che da meta').
    assert a == [[0, 1], [0.5, 1], [1, 2]]
    assert b == [[0, 5], [0.5, 7], [1, 7]]
    assert c == 9          # mai mosso: scalare, non un inviluppo piatto


@node
def test_salva_modifica_riscrive_solo_il_breakpoint_selezionato(tmp_path):
    """Cambiare i select non tocca il punto finche' non si salva."""
    js = _script()
    frag = (js[js.index("function snapshot"):js.index("function bpAdd")]
            + js[js.index("function bpSave"):js.index("function bpDel")]
            + js[js.index("function serie"):js.index("function labDoc")])
    p = tmp_path / "s.js"
    p.write_text(
        "const NUM = [{path:'a'}, {path:'b'}];\n"
        "const SCHERMO = {a: 9, b: 5};\n"
        "const document = {getElementById: id => ({value: SCHERMO[id.slice(2)]})};\n"
        "let bps = [{t:0, vals:{a:1, b:5}}, {t:1, vals:{a:2, b:5}}];\n"
        "let curBp = 1;\n"
        "function drawTl() {}\n"
        + frag +
        "const prima = serie('a');\n"
        "bpSave();\n"
        "console.log(JSON.stringify([prima, serie('a'), serie('b'), bps[0].vals.a]));")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    prima, dopo, b, primo = __import__("json").loads(out.stdout)
    assert prima == [[0, 1], [1, 2]]
    assert dopo == [[0, 1], [1, 9]]     # salvato sul secondo punto
    assert primo == 1                   # il primo non e' stato toccato
    assert b == 5                       # invariato: resta scalare


@node
def test_il_profilo_disegnato_parte_e_finisce_dove_deve(tmp_path):
    """La polilinea e' il profilo vero: y invertita (1 = in alto) e x distesa."""
    js = _script()
    frag = js[js.index("function envSvg"):js.index("function mkEnv")]
    p = tmp_path / "e.js"
    p.write_text(frag + "console.log(envSvg([0, 1, 0]));")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    # x: 0 -> 23 -> 46 (la larghezza); y: 19 (fondo) -> 1 (cima) -> 19
    assert 'd="M0.0 19.0 L23.0 1.0 L46.0 19.0"' in out.stdout


@node
def test_riaprire_un_progetto_ricostruisce_i_breakpoint(tmp_path):
    """I breakpoint sono i tempi degli inviluppi: un progetto si riapre da li'."""
    js = _script()
    frag = js[js.index("function valoreA"):js.index("function labOpen")]
    doc = {"duration": 5, "streams": [{
        "grain": {"duration": [[0, 0.001], [0.4, 0.001], [1, 0.032]]},
        "pitch": {"ratio": [[0, 0.2], [1, 0.75]]},
        "fill_factor": 2}]}
    p = tmp_path / "o.js"
    p.write_text(
        "const NUM = [{path:'grain.duration'}, {path:'pitch.ratio'}, {path:'fill_factor'}];\n"
        "const st = " + __import__("json").dumps(doc["streams"][0]) + ";\n"
        + frag +
        "const ts = new Set([0]);\n"
        "for (const p of NUM) { const v = leggiPath(st, p.path);"
        "  if (Array.isArray(v)) for (const [t] of v) ts.add(t); }\n"
        "const bps = [...ts].sort((a,b)=>a-b).map(t => ({t, vals:"
        "  Object.fromEntries(NUM.map(p => [p.path, Number(valoreA(leggiPath(st, p.path), t))]))}));\n"
        "console.log(JSON.stringify(bps));")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    bps = __import__("json").loads(out.stdout)
    assert [b["t"] for b in bps] == [0, 0.4, 1]
    # A 0.4 pitch.ratio non ha un punto suo: vale quanto la rampa vale li'
    # (0.2 -> 0.75 al 40%), non il valore a sinistra — altrimenti risalvando
    # il file la rampa ripartirebbe da 0.4 e il suono cambierebbe.
    assert bps[1]["vals"]["grain.duration"] == 0.001
    assert bps[1]["vals"]["fill_factor"] == 2
    assert abs(bps[1]["vals"]["pitch.ratio"] - 0.42) < 1e-9
    assert bps[2]["vals"]["grain.duration"] == 0.032
