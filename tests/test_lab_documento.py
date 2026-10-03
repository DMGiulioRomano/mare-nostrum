"""Il laboratorio apre un documento e lo riscrive: cosa resta e cosa cambia.

Qui la pagina gira intera (``tests/lab_dom.js``), non a frammenti: il giro
che conta passa per ``carica`` (il documento aperto), i select, le voci, il
loop, la storia, la bozza, e torna fuori da ``labDoc``. Il documento arriva
come lo manda il server (``yaml.safe_load`` -> JSON) e, dove serve l'engine,
esce come lo scrive il server (``render_doc``: JSON -> YAML).

La regola (#3): si parte dallo stream del documento aperto e si sovrascrive
solo cio' che il laboratorio conosce **e che e' stato toccato**. Il ``base:``
dello studio e la tabella ``DEFAULTS`` valgono solo per il foglio bianco.
"""
import json
import os
import shutil
import subprocess

import pytest
import yaml

from granstudies.graph import build_html, lab_completo

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HARNESS = os.path.join(ROOT, "tests", "lab_dom.js")

node = pytest.mark.skipif(shutil.which("node") is None, reason="serve node")

# Due dei sample del brano, non tutti: uno stream che usa un sample fuori
# dalla cartella dello studio vede il suo select vuoto, come nel browser.
CAMPIONI = ["001-41_5-5_5.wav", "001-3_0-5_5.wav"]


def _pagina(tmp_path, study="001-41"):
    with open(os.path.join(ROOT, "studies", study, "study.yml")) as fh:
        raw = yaml.safe_load(fh)
    p = tmp_path / "graph.html"
    p.write_text(build_html(study, lab_completo(raw, CAMPIONI, {}, lambda _p: None)))
    return p


def _lab(tmp_path, scenario, prima=None, study="001-41"):
    """Fa girare lo scenario sulla pagina; l'ultima riga stampata e' JSON."""
    args = ["node", HARNESS, str(_pagina(tmp_path, study))]
    sc = tmp_path / "scenario.js"
    sc.write_text(scenario)
    args.append(str(sc))
    if prima:
        pr = tmp_path / "prima.js"
        pr.write_text(prima)
        args.append(str(pr))
    out = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def _brano():
    with open(os.path.join(ROOT, "mare-nostrum.yml")) as fh:
        return yaml.safe_load(fh)


STREAMS = [s["stream_id"] for s in _brano()["streams"]]


def _stream(sid):
    return next(s for s in _brano()["streams"] if s["stream_id"] == sid)


def _documento(st):
    """Uno stream del brano in un file suo, come lo apre il laboratorio."""
    return {"duration": st.get("duration"), "bpm": 120, "streams": [st]}


def _apri(st, path=None):
    return "carica(%s, %s);\n" % (json.dumps(_documento(st)),
                                  json.dumps(path or "/brano/%s.yml" % st["stream_id"]))


STAMPA = "console.log(JSON.stringify(labDoc()));\n"

# Il valore che si scrive nel campo di un parametro e si salva sul
# breakpoint selezionato: e' il gesto di `salva modifica`.
def _tocca(i, path, valore, tipo=None):
    js = "bpLoad(%d); document.getElementById(%s).value = %s;\n" % (
        i, json.dumps("P:" + path), json.dumps(str(valore)))
    if tipo:
        js += "document.getElementById(%s).value = %s;\n" % (
            json.dumps("I:" + path), json.dumps(tipo))
    return js + "bpSave();\n"


# --- #3: lo stream aperto si conserva -----------------------------------------

@node
def test_read_direction_a_inviluppo_sopravvive_al_giro(tmp_path):
    """Il caso che ha aperto la #3: 8 stream del brano su 10 la perdevano."""
    st = _stream("stream2")
    doc = _lab(tmp_path, _apri(st) + STAMPA)
    assert doc["streams"][0]["grain"]["read_direction"] == st["grain"]["read_direction"]


@node
@pytest.mark.parametrize("sid", ["stream2", "stream4", "stream9"])
def test_aperto_e_risalvato_senza_toccare_e_lo_stesso_stream(tmp_path, sid):
    """Niente chiavi del `base:` dello studio, niente default del laboratorio.

    stream4 non dichiara `pointer.offset_range` ne' `pitch.range`, e il
    laboratorio di 001-41 ha un campo per tutti e due: restano assenti. Lo
    `stream_id` e l'`onset` sono quelli del documento, non `lab` e 0.
    """
    st = _stream(sid)
    doc = _lab(tmp_path, _apri(st) + STAMPA)
    assert doc["streams"][0] == st


@node
def test_un_parametro_toccato_si_scrive_come_prima(tmp_path):
    """Breakpoint e interpolazione, come oggi; il resto resta com'era."""
    st = _stream("stream2")
    doc = _lab(tmp_path, _apri(st) + _tocca(0, "pitch.ratio", 0.75, "cubic") + STAMPA)
    out = doc["streams"][0]
    assert out["pitch"]["ratio"][0] == [0, 0.75, "cubic"]
    assert out["pitch"]["ratio"][-1][1] == 0.2
    out["pitch"]["ratio"] = st["pitch"]["ratio"]
    assert out == st


@node
def test_le_voci_toccate_si_scrivono_le_altre_restano(tmp_path):
    st = _stream("stream3")
    doc = _lab(tmp_path, _apri(st) + "setSel('voices.pan.strategy', 'off');\n" + STAMPA)
    out = doc["streams"][0]
    assert out["voices"] == {"num_voices": 4, "pitch": st["voices"]["pitch"]}
    out["voices"] = st["voices"]
    assert out == st


@node
def test_il_loop_acceso_si_scrive_col_suo_gruppo(tmp_path):
    """Il loop e' un gruppo di chiavi: acceso, `start: 0` se ne va con lui
    (col loop il pointer parte da loop_start), il resto del pointer resta."""
    st = _stream("stream2")
    doc = _lab(tmp_path, _apri(st) + "loopDisegna(0.1, 0.4);\n" + STAMPA)
    assert doc["streams"][0]["pointer"] == {
        "speed_ratio": 0.1, "loop_unit": "normalized", "offset_range": 0.01,
        "loop_start": 0.1, "loop_end": 0.4}


@node
def test_la_finestra_che_cambia_diventa_a_stati(tmp_path):
    st = _stream("stream2")
    doc = _lab(tmp_path, _apri(st)
               + "bps[bps.length - 1].vals['grain.envelope'] = 'bartlett'; drawTl();\n"
               + STAMPA)
    env = doc["streams"][0]["grain"]["envelope"]
    assert env["states"] == [[0, "hanning"], [1, "bartlett"]]
    assert doc["streams"][0]["grain"]["read_direction"] == st["grain"]["read_direction"]


@node
def test_il_foglio_bianco_nasce_da_defaults_e_base(tmp_path):
    doc = _lab(tmp_path, "bpAdd();\n" + STAMPA)
    out = doc["streams"][0]
    assert (out["stream_id"], out["onset"], out["time_mode"]) == ("lab", 0, "normalized")
    assert out["grain"]["duration"] == 0.064             # DEFAULTS
    assert out["distribution_mode"] == "uniform"         # base:


@node
def test_nuovo_dopo_un_documento_aperto_non_se_lo_porta_dietro(tmp_path):
    """`nuovo` torna al foglio bianco: lo stream di prima non e' piu' la base."""
    doc = _lab(tmp_path, _apri(_stream("stream2")) + "fNew(); bpAdd();\n" + STAMPA)
    out = doc["streams"][0]
    assert (out["stream_id"], out["onset"]) == ("lab", 0)
    assert "read_direction" not in out["grain"]


@node
def test_l_undo_torna_allo_stream_aperto(tmp_path):
    st = _stream("stream2")
    got = _lab(tmp_path, _apri(st) + _tocca(0, "pitch.ratio", 0.75) + """
const toccato = labDoc().streams[0];
vaiStoria(-1);
const annullato = labDoc().streams[0];
vaiStoria(1);
console.log(JSON.stringify([toccato, annullato, labDoc().streams[0]]));
""")
    toccato, annullato, rifatto = got
    assert annullato == st
    assert toccato == rifatto and toccato["pitch"]["ratio"][0] == [0, 0.75]


@node
def test_la_bozza_riporta_lo_stream_conservato(tmp_path):
    """Un refresh a meta' lavoro: torna anche quello che il laboratorio non
    conosce, non solo i breakpoint."""
    st = _stream("stream2")
    bozza = _lab(tmp_path, _apri(st) + _tocca(0, "pitch.ratio", 0.75)
                 + "console.log(localStorage.getItem('lab:001-41'));\n")
    bozza["sess"] = "S"
    prima = """
localStorage.setItem('lab:001-41', %s);
fetch = async () => ({ok: true, json: async () => ({ok: true, sessione: 'S', recenti: []})});
""" % json.dumps(json.dumps(bozza))
    doc = _lab(tmp_path, STAMPA, prima=prima)
    out = doc["streams"][0]
    assert out["pitch"]["ratio"][0] == [0, 0.75]
    out["pitch"]["ratio"] = st["pitch"]["ratio"]
    assert out == st


@node
def test_l_anteprima_e_quella_del_documento(tmp_path):
    """L'anteprima dice cosa finisce nello YAML: un inviluppo non toccato
    esce come era scritto, non coi punti in piu' della griglia dei
    breakpoint (qui quelli di `fill_factor`)."""
    righe = _lab(tmp_path, _apri(_stream("stream4"))
                 + "console.log(JSON.stringify(preview().split('\\n')));\n")
    assert "grain.duration: [[0.000, 0.02, step], [0.343, 0.0032], [1.000, 0.02]]" in righe
    assert ("fill_factor: {type: cubic} [[0.000, 2], [0.093, 2.01], [0.163, 0.46], "
            "[0.259, 0.4], [0.313, 2.75], [1.000, 1]]") in righe


@node
@pytest.mark.parametrize("sid", ["stream5", "stream10"])
def test_si_ascolta_senza_piazzamento_ma_si_salva_con(tmp_path, sid):
    """`onset`, `mute` e `solo` sono del brano, non del suono dello stream.

    Nel file restano (lo stream e' quello). Ma ascoltato nel laboratorio uno
    stream con onset 43 s partirebbe dopo 43 s di silenzio, e uno con `mute`
    non suonerebbe affatto: il render d'ascolto li toglie.
    """
    st = _stream(sid)
    got = _lab(tmp_path, _apri(st) + """
const POST = [];
fetch = async (rotta, opt) => { POST.push(JSON.parse(opt.body));
  return {ok: true, json: async () => ({ok: false, error: 'fermo qui'})}; };
labRender().then(() => console.log(JSON.stringify(POST[0])));
""")
    assert got["doc"]["streams"][0] == st
    ascolto = got["ascolto"]["streams"][0]
    assert ascolto["onset"] == 0
    assert "mute" not in ascolto and "solo" not in ascolto
    piazzati = {"onset", "mute", "solo"}
    assert ({k: v for k, v in ascolto.items() if k not in piazzati}
            == {k: v for k, v in st.items() if k not in piazzati})


# --- #4: gli inviluppi {type, points} -----------------------------------------
# `{type: cubic, points: [...]}` e' l'interpolazione globale di un inviluppo:
# la scrive PGE-ui appena quella di una curva di soli breakpoint non e'
# lineare, e in `mare-nostrum.yml` la portano grain.duration (stream6,
# stream8), fill_factor (stream4) e voices.pitch.pitch_range (stream10, step).

ENGINE_SRC = os.path.join(ROOT, "engine", "src")
engine = pytest.mark.skipif(not os.path.isdir(os.path.join(ENGINE_SRC, "pge")),
                            reason="serve il submodule engine")


def _motore(tmp_path):
    from granstudies import engine_bridge
    engine_bridge._ensure_engine_on_path()
    engine_bridge._silence_loggers(str(tmp_path / "logs"))
    from pge.envelopes.envelope import Envelope
    return Envelope


_TIPI = {"LinearInterpolation": "linear", "CubicInterpolation": "cubic",
         "StepInterpolation": "step"}


def _tipo_motore(env, t):
    """Il tipo del segmento che parte da t, per l'engine; None fuori dai punti."""
    segs = env.segments
    if not segs[0].start_time <= t < segs[-1].end_time:
        return None
    for s in segs:
        if s.start_time <= t < s.end_time:
            return _TIPI[type(s.strategy).__name__]
    return None


def _inviluppo(v):
    return isinstance(v, list) or (isinstance(v, dict) and "points" in v)


def _leggi(st, path):
    for k in path.split("."):
        if not isinstance(st, dict):
            return None
        st = st.get(k)
    return st


def _vicini(a, b):
    return abs(a - b) <= 1e-12 * max(1.0, abs(a), abs(b))


@node
@engine
@pytest.mark.parametrize("sid", STREAMS)
def test_ogni_breakpoint_si_apre_col_valore_e_il_tipo_del_motore(tmp_path, sid):
    """Niente NaN, e non un'approssimazione: su ogni breakpoint ogni inviluppo
    vale quanto lo valuta l'engine, anche dove il breakpoint e' di un altro
    parametro e il segmento e' `cubic` (PCHIP di Fritsch-Carlson, con le
    tangenti calcolate su tutti i punti) o `step`. E il menu di
    interpolazione di quel breakpoint mostra il tipo del segmento che ne parte.
    """
    Envelope = _motore(tmp_path)
    st = _stream(sid)
    got = _lab(tmp_path, _apri(st)
               + "console.log(JSON.stringify({bps, num: NUM.map(p => p.path)}));\n")
    visti = 0
    for path in got["num"]:
        raw = _leggi(st, path)
        if not _inviluppo(raw):
            continue
        env = Envelope(raw)
        for b in got["bps"]:
            v = b["vals"][path]
            assert isinstance(v, (int, float)), (path, b["t"], v)
            assert _vicini(v, env.evaluate(b["t"])), (path, b["t"], v, env.evaluate(b["t"]))
            tipo = _tipo_motore(env, b["t"])
            if tipo:
                assert b["ints"][path] == tipo, (path, b["t"])
            visti += 1
    assert visti


@node
@engine
@pytest.mark.parametrize("sid", STREAMS)
def test_criterio_del_piano_ogni_stream_del_brano_risalvato_e_lo_stesso(tmp_path, sid):
    """Passo 1 di `docs/plans/stream-come-file.md`.

    Ogni stream di `mare-nostrum.yml`, aperto nel laboratorio e risalvato
    senza toccare niente, da' all'engine lo stesso stream: stesso fingerprint
    (`StreamCacheManager.compute_fingerprint`, quello che decide se uno stem
    va rifatto). Il giro e' quello vero: YAML -> JSON del server -> pagina ->
    JSON -> YAML scritto come lo scrive `render_doc`.
    """
    from granstudies import serve as S
    _motore(tmp_path)
    from pge.engine.generator import Generator
    from pge.rendering.stream_cache_manager import StreamCacheManager

    def impronte(path):
        g = Generator(str(path))
        g.load_yaml()
        m = StreamCacheManager(str(tmp_path / "manifest.json"), renderer_type="numpy")
        return {s["stream_id"]: m.compute_fingerprint(s) for s in g.data["streams"]}

    doc = _lab(tmp_path, _apri(_stream(sid)) + STAMPA)
    salvato = tmp_path / (sid + ".yml")
    with open(salvato, "w") as fh:
        yaml.dump(doc, fh, Dumper=S._Dumper, sort_keys=False, allow_unicode=True)
    assert impronte(salvato)[sid] == impronte(os.path.join(ROOT, "mare-nostrum.yml"))[sid]


@node
@pytest.mark.parametrize("sid,path", [("stream4", "fill_factor"),
                                      ("stream6", "grain.duration"),
                                      ("stream8", "grain.duration"),
                                      ("stream10", "voices.pitch.pitch_range")])
def test_un_type_points_non_toccato_si_riscrive_nella_sua_forma(tmp_path, sid, path):
    st = _stream(sid)
    doc = _lab(tmp_path, _apri(st) + STAMPA)
    assert _leggi(doc["streams"][0], path) == _leggi(st, path)


@engine
def test_type_points_e_tipo_su_ogni_punto_sono_lo_stesso_inviluppo(tmp_path):
    """La prova che decide la forma di riscrittura, fatta sull'engine.

    `{type: T, points}` (un segmento solo, strategia T su tutti i punti) e la
    lista con T scritto su ogni punto (un segmento per coppia) potrebbero non
    coincidere: le tangenti della cubica si calcolano sui punti del segmento.
    Non e' cosi': l'engine le calcola sempre su TUTTI i punti, e i due
    inviluppi valgono uguale ovunque, integrale compreso (il pointer integra
    speed_ratio), sui quattro `{type, points}` del brano. Per questo un
    `{type, points}` toccato puo' restare tale (tutti i segmenti T) o
    diventare la lista del laboratorio (tipi mescolati) senza che il suono
    cambi. Vale anche col tipo globale e le eccezioni per punto insieme, la
    forma scritta a mano che il laboratorio legge (`curva`) come una lista.
    """
    Envelope = _motore(tmp_path)
    casi = []
    for st in _brano()["streams"]:
        for path in ("grain.duration", "fill_factor", "voices.pitch.pitch_range"):
            d = _leggi(st, path)
            if isinstance(d, dict) and "points" in d:
                casi.append(d)
    assert len(casi) == 4
    # Un toccato: tipo globale cubic, un segmento `linear` e uno `step`.
    casi.append({"type": "cubic", "points": [[0, 2], [0.2, 0.5, "linear"], [0.4, 3],
                                             [0.6, 1, "step"], [0.8, 2.5], [1, 1]]})
    for d in casi:
        P = d["points"]
        lista = [[p[0], p[1], p[2] if len(p) > 2 else d["type"]] for p in P[:-1]] + [P[-1][:2]]
        a, b = Envelope(d), Envelope(lista)
        for i in range(2401):
            t = -0.1 + 1.2 * i / 2400
            assert a.evaluate(t) == b.evaluate(t), (d, t)
        for k in range(1, 41):
            assert _vicini(a.integrate(0, k / 40), b.integrate(0, k / 40)), (d, k)


def _toccato(tmp_path, js):
    """stream4 aperto, `fill_factor` toccato; il documento e i breakpoint."""
    return _lab(tmp_path, _apri(_stream("stream4")) + """
const at = t => bps.findIndex(b => Math.abs(b.t - t) < 1e-9);
""" + js + "console.log(JSON.stringify({doc: labDoc(), bps}));\n")


def _riceve_cio_che_si_vede(Envelope, inv, bps):
    """L'engine, letto il documento, vale su ogni breakpoint quanto il
    laboratorio mostra li', col tipo di segmento che il menu mostra."""
    env = Envelope(inv)
    for b in bps:
        assert _vicini(env.evaluate(b["t"]), b["vals"]["fill_factor"]), b["t"]
        tipo = _tipo_motore(env, b["t"])
        if tipo:
            assert tipo == b["ints"]["fill_factor"], b["t"]


@node
@engine
def test_un_type_points_toccato_resta_type_points(tmp_path):
    """Toccato un valore, i segmenti restano tutti `cubic`: si riscrive
    `{type: cubic, points}`, la forma in cui era arrivato. Il resto dello
    stream non e' stato toccato."""
    Envelope = _motore(tmp_path)
    got = _toccato(tmp_path, "bpLoad(at(0.1631)); "
                             "document.getElementById('P:fill_factor').value = '0.9'; bpSave();\n")
    out = got["doc"]["streams"][0]
    ff = out["fill_factor"]
    assert isinstance(ff, dict) and ff["type"] == "cubic"
    assert all(len(p) == 2 for p in ff["points"])
    assert [0.1631, 0.9] in ff["points"]
    _riceve_cio_che_si_vede(Envelope, ff, got["bps"])
    st = _stream("stream4")
    out["fill_factor"] = st["fill_factor"]
    assert out == st


@node
@engine
def test_un_type_points_coi_tipi_mescolati_si_riscrive_lista(tmp_path):
    """Un segmento passato a `linear` in un `{type: cubic}`: si riscrive la
    lista del laboratorio, col tipo su ogni punto da cui parte una cubica.

    Il dict col tipo globale e le eccezioni sul punto sarebbe per l'engine lo
    stesso inviluppo, ma PGE-ui non lo rilegge intatto: `wrapEnv`, appena un
    punto ha un tipo suo, riscrive la lista piatta e il `type` globale si
    perde — la cubica degli altri segmenti diventerebbe una retta alla prima
    modifica fatta li'. La lista coi tipi sul punto, invece, PGE-ui la tiene.
    """
    Envelope = _motore(tmp_path)
    got = _toccato(tmp_path, "bpLoad(at(0.1631)); "
                             "document.getElementById('P:fill_factor').value = '0.9'; bpSave();\n"
                             "bpLoad(at(0.2586)); "
                             "document.getElementById('I:fill_factor').value = 'linear'; bpSave();\n")
    ff = got["doc"]["streams"][0]["fill_factor"]
    assert isinstance(ff, list)
    assert [0.1631, 0.9, "cubic"] in ff and [0.2586, 0.4] in ff
    assert len(ff[-1]) == 2
    _riceve_cio_che_si_vede(Envelope, ff, got["bps"])


@node
def test_un_type_points_che_non_usa_piu_il_suo_tipo_torna_lista(tmp_path):
    """Se nessun segmento e' piu' del tipo globale, `{type: step}` non dice
    piu' niente: torna la lista, che e' la forma di sempre del laboratorio."""
    got = _lab(tmp_path, _apri(_stream("stream10")) + """
for (const b of bps) b.ints['voices.pitch.pitch_range'] = 'linear';
drawTl();
console.log(JSON.stringify(labDoc()));
""")
    pr = got["streams"][0]["voices"]["pitch"]["pitch_range"]
    assert isinstance(pr, list) and all(len(p) == 2 for p in pr)


@node
@engine
def test_segui_il_render_legge_gli_inviluppi_come_il_motore(tmp_path):
    """Fra due breakpoint `segui` mostra il valore della curva dei breakpoint
    come la valuterebbe l'engine: il gradino tiene, la cubica e' una cubica."""
    Envelope = _motore(tmp_path)
    xs = [0.05, 0.12, 0.2, 0.3, 0.33, 0.5, 0.9]
    got = _lab(tmp_path, _apri(_stream("stream4")) + """
const xs = %s;
console.log(JSON.stringify({bps, a: xs.map(x => bpA(x).vals)}));
""" % json.dumps(xs))
    curva = [[b["t"], b["vals"]["fill_factor"], b["ints"]["fill_factor"]] for b in got["bps"]]
    env = Envelope(curva)
    for x, vals in zip(xs, got["a"]):
        assert _vicini(vals["fill_factor"], env.evaluate(x)), x
    step = _lab(tmp_path, _apri(_stream("stream10")) + """
console.log(JSON.stringify([0.2, 0.5].map(x => bpA(x).vals['voices.pitch.pitch_range'])));
""")
    assert step == [0.5, 0]


@node
@engine
def test_il_lucchetto_taglia_un_type_points_dove_la_curva_passa(tmp_path):
    """Lucchetto chiuso, durata dimezzata: i punti tengono il loro tempo in
    secondi, quelli oltre la nuova fine escono, e il punto di chiusura sta
    dove la curva (cubica) passava a meta' della durata vecchia."""
    Envelope = _motore(tmp_path)
    st = _stream("stream4")
    got = _lab(tmp_path, _apri(st) + """
const prima = bps.map(b => [b.t, b.vals['fill_factor'], b.ints['fill_factor']]);
LUCCHETTO = true;
const d = document.getElementById('labDur');
d.value = String(%s / 2);
d.onchange();
console.log(JSON.stringify({prima, doc: labDoc()}));
""" % st["duration"])
    ff = got["doc"]["streams"][0]["fill_factor"]
    assert isinstance(ff, dict) and ff["type"] == "cubic"
    assert ff["points"][-1][0] == 1
    attesa = Envelope(got["prima"]).evaluate(0.5)
    assert _vicini(ff["points"][-1][1], attesa)
    assert got["doc"]["streams"][0]["duration"] == st["duration"] / 2


@node
def test_genera_breakpoint_su_un_type_points(tmp_path):
    """I punti generati prendono i valori a schermo e i tipi dei menu: niente
    NaN, e l'inviluppo resta `{type: cubic}` con i tempi nuovi dentro."""
    got = _lab(tmp_path, _apri(_stream("stream4")) + """
document.getElementById('gN').value = '3';
document.getElementById('gDa').value = '0.4';
document.getElementById('gA').value = '0.6';
genBps();
console.log(JSON.stringify(labDoc()));
""")
    ff = got["streams"][0]["fill_factor"]
    assert isinstance(ff, dict) and ff["type"] == "cubic"
    assert all(isinstance(p[1], (int, float)) for p in ff["points"])
    # Tutti e tre col valore a schermo (quello del primo breakpoint, 2): il
    # punto di mezzo, uguale ai due vicini e dello stesso tipo, non dice
    # niente e `serie` lo lascia fuori, come per ogni inviluppo.
    punti = {p[0]: p[1] for p in ff["points"]}
    assert punti[0.4] == punti[0.6] == 2 and 0.5 not in punti
