"""Il JS della pagina: che sia sintatticamente valido e che la FFT sia giusta.

Gira solo dove c'e' `node`. La STFT e' l'unico pezzo di matematica della
pagina, ed e' anche l'unico che puo' sbagliare in silenzio: uno spettrogramma
storto si guarda senza accorgersene. Il resto (canvas, cursori) e' verificabile
solo a occhio e resta fuori.
"""
import json
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
    p.write_text(_script().replace("__DATA__", '{study:"s01",lab:{base:{},params:[]}}'))
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
    js = (js[js.index("function tipoDi"):js.index("function bpAdd")]
          + js[js.index("function serie"):js.index("function labDoc")])
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
        "const NUM = [{path:'a', kind:'num'}, {path:'b', kind:'num'}];\n"
        "const AUT = NUM;\n"
        "const ENVP = null, EP = 'grain.envelope';\n"
        "const SCHERMO = {a: 9, b: 5};\n"
        "const document = {getElementById: id => ({value: id[0] === 'I'"
        "  ? 'linear' : SCHERMO[id.slice(2)]})};\n"
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
    frag = js[js.index("function valoreA"):js.index("async function labPost")]
    doc = {"duration": 5, "streams": [{
        "grain": {"duration": [[0, 0.001], [0.4, 0.001], [1, 0.032]]},
        "pitch": {"ratio": [[0, 0.2], [1, 0.75]]},
        "fill_factor": 2}]}
    p = tmp_path / "o.js"
    p.write_text(
        "const NUM = [{path:'grain.duration', kind:'num'}, {path:'pitch.ratio', kind:'num'}, {path:'fill_factor', kind:'num'}];\n"
        "const AUT = NUM;\n"
        "const ENVP = null, EP = 'grain.envelope';\n"
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


@node
def test_applica_a_tutti_tocca_solo_i_valori_appena_cambiati(tmp_path):
    """Gli altri parametri restano com'erano, anche se diversi fra loro.

    E' il punto: se un parametro ha gia' un inviluppo disegnato, cambiarne un
    altro e applicarlo a tutti non deve appiattire il primo.
    """
    js = _script()
    frag = (js[js.index("function snapshot"):js.index("function bpAdd")]
            + js[js.index("function cambiati"):js.index("function bpDel")])
    p = tmp_path / "a.js"
    p.write_text(
        "const NUM = [{path:'a', kind:'num'}, {path:'b', kind:'num'}, {path:'c', kind:'num'}];\n"
        "const AUT = NUM;\n"
        "const ENVP = null, EP = 'grain.envelope';\n"
        # i select mostrano a=9 (cambiato); b e c restano come nel punto corrente
        "const SCHERMO = {a: 9, b: 5, c: 1};\n"
        "const document = {getElementById: id => ({value: id[0] === 'I'"
        "  ? 'linear' : SCHERMO[id.slice(2)],"
        "                  set textContent(v) {}, get textContent() { return ''; }})};\n"
        "let bps = [{t:0, vals:{a:1, b:5, c:0}},"
        "           {t:0.5, vals:{a:2, b:5, c:1}},"
        "           {t:1, vals:{a:3, b:7, c:2}}];\n"
        "let curBp = 1;\n"
        "function drawTl() {}\n"
        + frag +
        "console.log(JSON.stringify([cambiati(), (bpAll(), bps)]));")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    ks, bps = __import__("json").loads(out.stdout)
    assert ks == ["a"]                       # solo quello toccato sullo schermo
    assert [b["vals"]["a"] for b in bps] == [9, 9, 9]
    assert [b["vals"]["b"] for b in bps] == [5, 5, 7]    # intatti, anche se diversi
    assert [b["vals"]["c"] for b in bps] == [0, 1, 2]


@node
def test_il_tipo_di_interpolazione_finisce_sul_punto_giusto(tmp_path):
    """`linear` non si scrive (e' il default), e l'ultimo punto non ha tipo:
    il tipo governa il segmento che PARTE dal punto."""
    js = _script()
    frag = (js[js.index("function tipoDi"):js.index("function bpAdd")]
            + js[js.index("function serie"):js.index("function labDoc")])
    p = tmp_path / "i.js"
    p.write_text(
        "const NUM = [{path:'a', kind:'num'}, {path:'b', kind:'num'}, {path:'c', kind:'num'}];\n"
        "const AUT = NUM;\n"
        "const ENVP = null, EP = 'grain.envelope';\n"
        "const document = {getElementById: () => null};\n"
        "let bps = ["
        " {t:0,   vals:{a:1, b:5, c:2}, ints:{a:'cubic', b:'linear', c:'step'}},"
        " {t:0.5, vals:{a:2, b:5, c:2}, ints:{a:'cubic', b:'linear', c:'step'}},"
        " {t:1,   vals:{a:3, b:9, c:2}, ints:{a:'cubic', b:'linear', c:'step'}}];\n"
        + frag +
        "console.log(JSON.stringify([serie('a'), serie('b'), serie('c')]));")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    a, b, c = __import__("json").loads(out.stdout)
    assert a == [[0, 1, "cubic"], [0.5, 2, "cubic"], [1, 3]]
    assert b == [[0, 5], [0.5, 5], [1, 9]]          # linear: nessun tipo scritto
    # c non si muove mai, ma e' `step`: resta un envelope e non diventa uno
    # scalare, che perderebbe il tipo. Il punto di mezzo invece cade: fermo,
    # stesso tipo del precedente, non dice niente di nuovo.
    assert c == [[0, 2, "step"], [1, 2]]


@node
def test_riaprendo_ogni_punto_ritrova_il_suo_tipo(tmp_path):
    js = _script()
    frag = js[js.index("function tipoA"):js.index("async function labPost")]
    p = tmp_path / "t.js"
    p.write_text(frag +
        "const v = [[0, 1, 'cubic'], [0.5, 2], [1, 3, 'step']];\n"
        "console.log(JSON.stringify([tipoA(v, 0), tipoA(v, 0.25), tipoA(v, 0.5),"
        " tipoA(v, 1), tipoA(7, 0.5)]));")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    # dentro il primo segmento: cubic; dal secondo punto in poi: linear (non
    # scritto); uno scalare non ha segmenti, quindi linear.
    assert __import__("json").loads(out.stdout) == \
        ["cubic", "cubic", "linear", "step", "linear"]


@node
def test_l_anteprima_mostra_anche_il_tipo(tmp_path):
    """Due inviluppi che suonano diverso non devono leggersi identici."""
    js = _script()
    frag = (js[js.index("function tipoDi"):js.index("function bpAdd")]
            + js[js.index("function serie"):js.index("function labDoc")]
            + js[js.index("function preview"):js.index("// --- il file")])
    p = tmp_path / "p.js"
    p.write_text(
        "const NUM = [{path:'a', kind:'num'}, {path:'b', kind:'num'}];\n"
        "const AUT = NUM;\n"
        "const ENVP = null, EP = 'grain.envelope', LOOP = null;\n"
        "let bps = [{t:0, vals:{a:1, b:1}, ints:{a:'cubic', b:'linear'}},"
        "           {t:1, vals:{a:2, b:2}, ints:{a:'cubic', b:'linear'}}];\n"
        + frag + "console.log(preview());")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    righe = out.stdout.strip().splitlines()
    assert righe[0] == "a: [[0.000, 1, cubic], [1.000, 2]]"
    assert righe[1] == "b: [[0.000, 1], [1.000, 2]]"


# --- le finestre sui breakpoint -------------------------------------------
# serieEnv comprime la sequenza delle finestre in {states, curve} e envA la
# rilegge: e' l'unico punto del laboratorio dove il valore non e' un numero,
# quindi l'unico dove il round-trip puo' rompersi in silenzio.

def _fn(js: str, nome: str) -> str:
    i = js.index("function " + nome + "(")
    j = js.index("\nfunction ", i + 1)
    return js[i:j] + "\n"


def _env(bps: str, coda: str, tmp_path) -> str:
    js = _script()
    src = "\n".join([
        'const EP = "grain.envelope";',
        _fn(js, "serieEnv"), _fn(js, "envA"),
        _fn(js, "valoreA"), _fn(js, "tipoDi"),
        "let bps = " + bps + ";", coda,
    ])
    p = tmp_path / "env.js"
    p.write_text(src)
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def _bps(seq, tipi=None):
    """Breakpoint equispaziati in [0,1], una finestra ciascuno."""
    n = max(len(seq) - 1, 1)
    return "[" + ",".join(
        '{t:%s, vals:{"grain.envelope":"%s"}, ints:{"grain.envelope":"%s"}}'
        % (i / n, w, (tipi or ["linear"] * len(seq))[i])
        for i, w in enumerate(seq)) + "]"


@node
def test_una_finestra_sola_resta_una_stringa(tmp_path):
    """Uno stream con un envelope solo non diventa un multistate."""
    got = _env(_bps(["hanning", "hanning", "hanning"]),
               "console.log(JSON.stringify(serieEnv()));", tmp_path)
    assert got == '"hanning"'


@node
def test_la_sequenza_diventa_states_piu_curve(tmp_path):
    got = _env(_bps(["hanning", "bartlett"], ["step", "linear"]),
               "console.log(JSON.stringify(serieEnv()));", tmp_path)
    assert json.loads(got) == {
        "states": [[0, "hanning"], [1, "bartlett"]],
        # `step` sul primo punto: il cambio e' netto. L'ultimo non ha tipo.
        "curve": [[0, 0, "step"], [1, 1]],
    }


@node
def test_una_finestra_che_torna_apre_un_terzo_stato(tmp_path):
    """hanning -> bartlett -> hanning: tre stati, non due.

    L'engine pretende valori di stato crescenti (InvalidStrategyConfigError
    altrimenti): riusare lo stato 0 per l'ultimo punto farebbe tornare
    indietro la curve, quindi la finestra ripetuta ne apre uno nuovo.
    """
    spec = json.loads(_env(_bps(["hanning", "bartlett", "hanning"]),
                           "console.log(JSON.stringify(serieEnv()));", tmp_path))
    assert [w for _, w in spec["states"]] == ["hanning", "bartlett", "hanning"]
    vals = [v for v, _ in spec["states"]]
    assert vals == sorted(vals)
    assert [t for t, _ in spec["curve"]] == [0, 0.5, 1]


@node
@pytest.mark.parametrize("seq", [
    ["hanning", "bartlett"],
    ["hanning", "bartlett", "gaussian"],
    ["hanning", "bartlett", "hanning"],
    ["hanning", "hanning", "expodec", "expodec", "gaussian"],
])
def test_riaprendo_ogni_breakpoint_ritrova_la_sua_finestra(tmp_path, seq):
    """Il round-trip: serieEnv scrive, envA rilegge, la sequenza e' la stessa."""
    n = max(len(seq) - 1, 1)
    got = _env(_bps(seq), """
const spec = serieEnv();
const ts = spec.curve.map(p => p[0]);
console.log(JSON.stringify(ts.map(t => envA(spec, t))));
""", tmp_path)
    assert json.loads(got) == seq[:len(json.loads(got))]
    assert json.loads(got) == seq


@node
def test_da_dove_parte_ogni_parametro(tmp_path):
    """Il laboratorio parte dai default suoi, non dalla prima tacca.

    Tre strade in ordine: la tabella DEFAULTS, poi `base:` dello study.yml,
    poi la prima tacca — ed e' l'ordine che fa partire il volume da 0 (neutro
    per l'ascolto) invece che dai 12 dB con cui lo sweep compensa il sample.
    """
    js = _script()
    frag = (js[js.index("const DEFAULTS"):js.index("function iniziale")]
            + _fn(js, "iniziale") + _fn(js, "leggiPath"))
    p = tmp_path / "i.js"
    p.write_text(
        "const L = {base: {volume: 12, sample: 'x.wav', grain: {envelope: 'hanning'}}};\n"
        + frag +
        "console.log(JSON.stringify(["
        "  iniziale({path:'grain.duration', values:[0.001, 0.064]}),"
        "  iniziale({path:'volume', values:[], free:true}),"
        "  iniziale({path:'grain.envelope', values:['bartlett','gaussian']}),"
        "  iniziale({path:'sample', values:['a.wav','x.wav']}),"
        "  iniziale({path:'pan', values:[7, 9]})]));")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [
        0.064,        # dalla tabella
        0,            # dalla tabella, non i 12 dB di base:
        "gaussian",   # dalla tabella, non l'hanning di base:
        "x.wav",      # niente default: quello di base:
        7,            # niente default e niente base: la prima tacca
    ]


@node
def test_il_loop_disegnato_sul_sample_torna_riaprendo(tmp_path):
    """La regione sulla forma d'onda diventa loop_start/loop_end normalizzati.

    Senza loop le chiavi spariscono (il pointer legge tutto il file); con il
    loop sparisce `start`, cosi' il pointer parte da loop_start. Un loop in
    secondi non si sa disegnare e resta fuori.
    """
    js = _script()
    frag = _fn(js, "loopDi") + _fn(js, "scriviLoop")
    p = tmp_path / "l.js"
    p.write_text(frag + """
const base = {pointer: {start: 0, speed_ratio: 0.1, loop_unit: 'normalized', loop_start: 0, loop_end: 0.3636}};
const st = JSON.parse(JSON.stringify(base));
scriviLoop(st, [0.123456, 0.5]);
const via = JSON.parse(JSON.stringify(base));
scriviLoop(via, null);
console.log(JSON.stringify([loopDi(base), st.pointer, loopDi(st), via.pointer,
  loopDi({pointer: {loop_start: 1, loop_end: 2}}),
  loopDi({pointer: {loop_unit: 'normalized', loop_start: 0.8, loop_dur: 0.5}})]));
""")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [
        [0, 0.3636],
        {"speed_ratio": 0.1, "loop_unit": "normalized", "loop_start": 0.1235, "loop_end": 0.5},
        [0.1235, 0.5],
        {"start": 0, "speed_ratio": 0.1},
        None,
        [0.8, 1],
    ]


@node
def test_un_numerico_si_puo_scrivere_a_mano(tmp_path):
    """Il campo libero: la virgola vale il punto, il vuoto tiene il punto."""
    js = _script()
    frag = js[js.index("function snapshot"):js.index("function bpAdd")]
    p = tmp_path / "m.js"
    p.write_text(
        "const AUT = [{path:'a', kind:'num'}, {path:'b', kind:'num'}];\n"
        "const SCHERMO = {a: '0,0037', b: ''};\n"
        "const document = {getElementById: id => ({value: SCHERMO[id.slice(2)]})};\n"
        "let bps = [{t:0, vals:{a:1, b:5}}];\n"
        "let curBp = 0;\n"
        + frag +
        "console.log(JSON.stringify(snapshot()));")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    v = __import__("json").loads(out.stdout)
    assert v["a"] == 0.0037     # scritto a mano, fuori dalle tacche
    assert v["b"] == 5          # campo vuoto: resta il valore del breakpoint


@node
def test_undo_e_redo_tornano_sui_breakpoint(tmp_path):
    """La storia e' tutto il lavoro: i punti e i valori a schermo non salvati."""
    js = _script()
    frag = (js[js.index("function istantanea"):js.index("addEventListener(\"keydown\", e => {\n  if (e.key.toLowerCase()")]
            + _fn(js, "snapshot") + _fn(js, "snapInterp"))
    p = tmp_path / "u.js"
    p.write_text(
        "const AUT = [{path:'a', kind:'num'}];\n"
        "let bps = [], LOOP = null, curBp = -1;\n"
        "let STORIA = [], ISTO = -1, GESTO = false;\n"
        "const SELEZIONE = new Set();\n"
        "let DURPREC = 30;\n"
        "function durata() { return 30; }\n"
        "const SCHERMO = {a: 1};\n"
        "const document = {getElementById: id => ({\n"
        "  get value() { return id[0] === 'I' ? 'linear' : SCHERMO[id.slice(2)]; },\n"
        "  set value(v) { if (id[0] !== 'I') SCHERMO[id.slice(2)] = v; },\n"
        "  textContent: '', classList: {toggle(){}}, querySelectorAll: () => []})};\n"
        "function setSel(path, v) { SCHERMO[path] = v; }\n"
        "function drawTl() { if (!GESTO) storia(); }\n"
        "function iniziale() { return 0; }\n"
        + frag +
        "drawTl();\n"                        # stato iniziale: vuoto
        "bps.push({t:0, vals:{a:1}}); drawTl();\n"
        "SCHERMO.a = 7; drawTl();\n"         # valore cambiato ma non salvato
        "const prima = SCHERMO.a;\n"
        "vaiStoria(-1); const dopoUndo = SCHERMO.a;\n"
        "vaiStoria(-1); const punti = bps.length;\n"
        "vaiStoria(1); vaiStoria(1); const dopoRedo = SCHERMO.a;\n"
        "console.log(JSON.stringify([prima, dopoUndo, punti, dopoRedo, STORIA.length]));")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    prima, dopoUndo, punti, dopoRedo, n = __import__("json").loads(out.stdout)
    assert prima == 7
    assert dopoUndo == 1      # l'undo riporta anche il valore non salvato
    assert punti == 0         # un altro passo indietro: il breakpoint sparisce
    assert dopoRedo == 7
    assert n == 3


@node
def test_i_valori_generati_riempiono_l_intervallo_come_si_e_chiesto(tmp_path):
    """`riempi` riempie [a, b] nei quattro modi, e il passo quantizza.

    E' l'unica matematica di `genera breakpoint`: tempi e valori escono tutti
    di qui, e un intervallo riempito storto (un estremo mancato, un valore
    fuori maschera) sullo YAML non si vede.
    """
    js = _script()
    p = tmp_path / "g.js"
    p.write_text(
        _fn(js, "gaussiano") + _fn(js, "riempi") + """
const q = Math.pow(0.016 / 0.001, 1 / 4);   // il ratio che da' la geometrica
const out = {
  uno: riempi("regolare", 5, 0, 1, 0, 1),
  cresce: riempi("regolare", 5, 0, 1, 0, 2),
  cala: riempi("regolare", 5, 0, 1, 0, 0.5),
  geom: riempi("regolare", 5, 0.001, 0.016, 0, q),
  zero: riempi("regolare", 5, 0, 1, 0, q),  // il ratio non teme lo zero
  solo: riempi("regolare", 1, 0.2, 0.9, 0, 1),
  passo: riempi("regolare", 5, 0, 1, 0.3, 1),
  random: riempi("random", 200, 0.01, 0.04),
  gauss: riempi("gauss", 200, 0.01, 0.04),
};
console.log(JSON.stringify(out));
""")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    g = json.loads(out.stdout)
    assert g["uno"] == [0, 0.25, 0.5, 0.75, 1]        # ratio 1: equidistanti
    # ratio != 1: i passi stanno in progressione geometrica di quella ragione,
    # e gli estremi ci cadono sopra lo stesso
    for nome, r in (("cresce", 2), ("cala", 0.5)):
        passi = [b - a for a, b in zip(g[nome], g[nome][1:])]
        assert all(y / x == pytest.approx(r) for x, y in zip(passi, passi[1:])), nome
        assert (g[nome][0], g[nome][-1]) == pytest.approx((0, 1)), nome
    # ratio = (b/a)^(1/(n-1)): e' la geometrica di prima, rapporto costante
    # fra un VALORE e il successivo
    assert g["geom"][0] == pytest.approx(0.001) and g["geom"][-1] == pytest.approx(0.016)
    r = [b / a for a, b in zip(g["geom"], g["geom"][1:])]
    assert all(x == pytest.approx(r[0]) for x in r)
    # con a = 0 la vecchia geometrica non esisteva; qui il ratio lavora lo stesso
    assert g["zero"][0] == 0 and g["zero"][-1] == pytest.approx(1)
    assert sorted(g["zero"]) == g["zero"]
    assert g["solo"] == [0.2]                      # un punto solo: parte da `a`
    # il passo quantizza a multipli: comanda lui, anche se b non e' un
    # multiplo e l'ultimo punto ci resta sotto
    assert g["passo"] == pytest.approx([0, 0.3, 0.6, 0.9, 0.9])
    for modo in ("random", "gauss"):
        assert all(0.01 <= v <= 0.04 for v in g[modo]), modo
    # la gaussiana sta in mezzo, l'uniforme no: tre sigma sugli estremi
    centro = sum(1 for v in g["gauss"] if 0.02 <= v <= 0.03)
    assert centro > sum(1 for v in g["random"] if 0.02 <= v <= 0.03)


@node
def test_la_banda_prende_i_punti_che_ci_cadono_dentro_e_delete_li_toglie(tmp_path):
    """Selezione multipla: chi sta nella banda se ne va tutto insieme.

    Gli estremi ci stanno dentro (una banda tirata su un punto lo prende), il
    punto corrente sopravvissuto resta corrente, e la selezione si scioglie
    dopo: lasciarla addosso a oggetti cancellati toglierebbe il prossimo giro.
    """
    js = _script()
    p = tmp_path / "b.js"
    p.write_text(
        "let bps = [0.1, 0.3, 0.5, 0.7, 0.9].map(t => ({t, vals:{}}));\n"
        "let curBp = 4;\n"
        "let CARICATO = -1;\n"
        "function drawTl() {}\n"
        "function bpLoad(i) { CARICATO = i; }\n"
        "const document = {getElementById: () => ({hidden: true})};\n"
        "const addEventListener = () => {};\n"
        + "let SELEZIONE = new Set();\n"
        + _fn(js, "selezionaFra") + _fn(js, "mostraBp") + _fn(js, "bpDel") + """
selezionaFra(0.7, 0.3);                 // tirata al contrario: stesso risultato
const presi = SELEZIONE.size;
bpDel();
const restano = bps.map(b => b.t), dopo = curBp, sel = SELEZIONE.size;
bpDel();                                // senza banda: il punto corrente
console.log(JSON.stringify([presi, restano, dopo, sel, bps.map(b => b.t), CARICATO]));
""")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    presi, restano, dopo, sel, infine, caricato = json.loads(out.stdout)
    assert presi == 3                    # 0.3, 0.5, 0.7 — estremi compresi
    assert restano == [0.1, 0.9]
    assert dopo == 1                     # 0.9 era il corrente ed e' rimasto lui
    assert sel == 0                      # la banda si scioglie dopo la cancellazione
    assert infine == [0.1]               # il secondo giro toglie solo il corrente
    # il punto corrente e' cambiato da solo: i valori a schermo lo seguono,
    # se no `cambiati()` segnerebbe come non salvato quello che c'era prima
    assert caricato == 0


@node
def test_col_lucchetto_i_breakpoint_tengono_il_tempo_in_secondi(tmp_path):
    """Cambiando la durata, le x si riscalano e i tempi assoluti restano quelli.

    E' il `freezeEnvOnResize` di PGE-ui portato qui: le x sono normalizzate,
    quindi lo stesso 0.5 vale 15 s in uno stream di 30 e 5 s in uno di 10.
    Accorciando, chi esce se ne va ma lascia il punto in cui l'inviluppo
    tagliava la nuova fine — se no la coda resterebbe piatta.
    """
    js = _script()
    p = tmp_path / "r.js"
    p.write_text(
        "const AUT = [{path:'a'}, {path:'b'}];\n"
        "let bps = [{t:0, vals:{a:0, b:0}}, {t:0.5, vals:{a:10, b:0}, ints:{b:'step'}},\n"
        "           {t:1, vals:{a:20, b:100}}];\n"
        + _fn(js, "tipoDi") + _fn(js, "bpFra") + _fn(js, "ridimensiona") + """
const lungo = ridimensiona(30, 60);        // il doppio: tutto si contrae
const dopoLungo = bps.map(b => [b.t, b.vals.a]);
const corto = ridimensiona(60, 30);        // e torna dov'era
const dopoCorto = bps.map(b => [b.t, b.vals.a]);
const tagliati = ridimensiona(30, 20);     // 1.5x: l'ultimo esce
console.log(JSON.stringify([lungo, dopoLungo, corto, dopoCorto, tagliati,
                            bps.map(b => [b.t, b.vals.a, b.vals.b])]));
"""
    )
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    lungo, dopoLungo, corto, dopoCorto, tagliati, finale = json.loads(out.stdout)
    # 30 -> 60 s: 0.5 (15 s) diventa 0.25 (15 s di 60). Nessuno esce.
    assert lungo == 0 and dopoLungo == [[0, 0], [0.25, 10], [0.5, 20]]
    assert corto == 0 and dopoCorto == [[0, 0], [0.5, 10], [1, 20]]
    # 30 -> 20 s: 1 (30 s) cadrebbe a 1.5, fuori. Esce uno e al bordo resta il
    # valore interpolato: a meta' fra 10 e 20 sul segmento 0.75 -> 1.5.
    assert tagliati == 1
    assert [t for t, _, _ in finale] == [0, 0.75, 1]
    assert finale[-1][1] == pytest.approx(10 + 10 * (1 - 0.75) / (1.5 - 0.75))
    # `b` ha il tipo step sul punto di partenza: il bordo tiene il suo valore,
    # non interpola verso i 100 del punto che se n'e' andato
    assert finale[-1][2] == 0


def _voci(bps: str, coda: str, tmp_path) -> str:
    """Il mondo delle voci senza DOM: la tabella, il pruner, la progressione.

    Restano fuori `vociInit`/`vociVis`/`vociCarica`, che leggono i select: qui
    si prova quello che decide cosa finisce nel documento.
    """
    js = _script()
    tabella = js[js.index("const STRAT = {"):js.index("\n// Dove finisce ogni parametro")]
    src = "\n".join([
        "const L = {base: {}, params: []};",
        tabella,
        'const PROG = VOCI_DI["voices.pitch.progression"];',
        _fn(js, "progressione"), _fn(js, "passoA"),
        _fn(js, "vociDoc"), _fn(js, "setPath"), _fn(js, "tipoDi"),
        # Come fa labDoc: ogni path scritto, poi il pruner ripulisce.
        """function docFinto(vals) {
             const st = {};
             for (const p of VOCI) {
               if (p === PROG) continue;
               setPath(st, p.path, vals[p.path] !== undefined ? vals[p.path] : p.def);
             }
             vociDoc(st);
             return st.voices === undefined ? null : st.voices;
           }""",
        "let bps = " + bps + ";", coda,
    ])
    p = tmp_path / "voci.js"
    p.write_text(src)
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


@node
def test_il_documento_tiene_solo_le_chiavi_della_strategia_scelta(tmp_path):
    """Quattro assi spenti = nessun blocco `voices:`; acceso = solo le sue chiavi.

    E' la regola che tiene lo YAML leggibile: a schermo i parametri di tutte
    le strategie esistono, sul documento ci va solo quello che l'engine legge
    davvero per la strategia scelta.
    """
    got = json.loads(_voci("[{t: 0, vals: {}, ints: {}}]", """
console.log(JSON.stringify([
  docFinto({}),
  docFinto({"voices.num_voices": 3}),
  docFinto({"voices.num_voices": 4, "voices.pitch.strategy": "chord",
            "voices.pitch.chord": "min", "voices.pitch.unit": "semitones"}),
  docFinto({"voices.num_voices": 4, "voices.pitch.strategy": "spectral"}),
  docFinto({"voices.num_voices": 4, "voices.pitch.strategy": "step",
            "voices.pitch.unit": "edo", "voices.pitch.edo": 19}),
  docFinto({"voices.num_voices": 2, "voices.pointer.strategy": "linear",
            "voices.pointer.normalized": "si"}),
  docFinto({"voices.num_voices": 2, "voices.pan.strategy": "range",
            "voices.scatter": 0.5}),
]));
""", tmp_path))
    spento, sole, accordo, spettro, edo, puntatore, pan = got
    assert spento is None                       # una voce, nessuna strategia
    assert sole == {"num_voices": 3}            # tre voci all'unisono
    assert accordo["pitch"] == {"strategy": "chord", "chord": "min"}
    assert spettro["pitch"] == {"strategy": "spectral", "max_partial": 16}
    assert edo["pitch"] == {"strategy": "step", "unit": {"edo": 19}, "step": 3}
    assert puntatore["pointer"] == {"strategy": "linear", "step": 0.1, "normalized": True}
    assert pan == {"num_voices": 2, "scatter": 0.5,
                   "pan": {"strategy": "range", "spread": 60}}


@node
def test_la_progressione_di_accordi_e_i_breakpoint(tmp_path):
    """L'accordo cambia di colpo e resta: un ripetuto non apre un passo nuovo.

    Il rivolto viaggia dentro il passo (terzo elemento) e solo se non e' lo
    stato fondamentale; rileggendo, `passoA` rida' a ogni tempo l'accordo che
    ci valeva.
    """
    bps = """[
      {t: 0,   vals: {"voices.pitch.progression": "maj7", "voices.pitch.inversion": 0}, ints: {}},
      {t: 0.3, vals: {"voices.pitch.progression": "maj7", "voices.pitch.inversion": 0}, ints: {}},
      {t: 0.6, vals: {"voices.pitch.progression": "min7", "voices.pitch.inversion": 1},
       ints: {"voices.pitch.progression": "step"}},
      {t: 1,   vals: {"voices.pitch.progression": "dom7", "voices.pitch.inversion": 9}, ints: {}}]"""
    got = json.loads(_voci(bps, """
const doc = docFinto({"voices.num_voices": 4,
                      "voices.pitch.strategy": "chord_progression"});
const letti = [0, 0.3, 0.6, 1].map(t => passoA(doc.pitch.progression, t));
console.log(JSON.stringify([doc.pitch, letti]));
""", tmp_path))
    pitch, letti = got
    assert pitch["progression"] == [[0, "maj7"], [0.6, "min7", 1], [1, "dom7", 3]]
    assert "inversion" not in pitch           # sta nei passi, non accanto
    assert pitch.get("interp") is None        # il tipo del PRIMO punto e' linear
    assert [p[1] for p in letti] == ["maj7", "maj7", "min7", "dom7"]


@node
def test_gli_inviluppi_si_fermano_dove_finisce_lo_stream(tmp_path):
    """Il file reso e' piu' lungo dello stream (la coda dell'ultimo grano).

    Le curve occupano la loro frazione della larghezza, non tutta: se no
    l'ultimo breakpoint cadrebbe dopo il punto in cui suona. E il pannello
    resta chiuso quando a suonare non e' un render del laboratorio.
    """
    js = _script()
    stub = """
const TRATTI = [];
let _pen = null;
const CTX = {
  clearRect(){}, beginPath(){ _pen = []; TRATTI.push(_pen); },
  moveTo(x, y){ _pen.push([x, y]); }, lineTo(x, y){ _pen.push([x, y]); },
  stroke(){}, set strokeStyle(v){}, set lineWidth(v){}, set globalAlpha(v){},
};
function El(tag) {
  return {tag, children: [], className: "", textContent: "", innerHTML: "",
          hidden: false, style: {}, width: 0, height: 200,
          parentNode: {clientWidth: 500},
          appendChild(c){ this.children.push(c); return c; },
          getContext(){ return CTX; }};
}
const REG = {envView: El("div"), envLeg: El("div"), envc: El("canvas")};
const document = {getElementById: id => REG[id] || null, createElement: El,
                  createTextNode: t => ({t}), body: {}};
function getComputedStyle() { return {color: "#fff"}; }
let LAB_AUDIO = false, view = {duration: 10};
let ENVS = [{nome: "grain_duration", colore: "#377eb8", da: "10ms", a: "200ms",
             y: [0, 0.5, 1]},
            {nome: "pitch", colore: "#984ea3", da: "0st", a: "7st", y: [0, 1, 1]}];
let ENVDUR = 8;
"""
    p = tmp_path / "env.js"
    p.write_text(stub + _fn(js, "drawEnvs") + """
drawEnvs();
const chiuso = REG.envView.hidden;
LAB_AUDIO = true;
drawEnvs();
const curve = TRATTI.slice(1);   // il primo tratto e' la cornice
console.log(JSON.stringify([chiuso, REG.envView.hidden,
  curve.length, curve[0].map(p => p[0]), REG.envLeg.children.length]));
""")
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    chiuso, aperto, n_curve, xs, n_leg = json.loads(out.stdout)
    assert chiuso is True and aperto is False
    assert n_curve == 2 and n_leg == 2
    # 8 s di stream su 10 di file, canvas 500 px: l'ultimo punto a 400.
    assert xs == [0, 200, 400]
