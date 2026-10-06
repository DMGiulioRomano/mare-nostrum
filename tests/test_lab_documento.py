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
ENGINE_SRC = os.path.join(ROOT, "engine", "src")

node = pytest.mark.skipif(shutil.which("node") is None, reason="serve node")
engine = pytest.mark.skipif(not os.path.isdir(os.path.join(ENGINE_SRC, "pge")),
                            reason="serve il submodule engine")

# Due dei sample del brano, non tutti: uno stream che usa un sample fuori
# dalla cartella dello studio vede il suo select vuoto, come nel browser.
CAMPIONI = ["001-41_5-5_5.wav", "001-3_0-5_5.wav"]


def _predefiniti():
    """I default dell'engine per path, come li passa `cmd_graph`. Senza il
    submodule non ce ne sono, e la pagina ricade sul foglio bianco."""
    if not os.path.isdir(os.path.join(ENGINE_SRC, "pge")):
        return {}
    from granstudies.engine_bridge import parameter_path_defaults
    return parameter_path_defaults()


_FINESTRE = None


def _finestre():
    """Le finestre dell'engine, come le passa `cmd_graph`. Senza, la pagina
    ripiega su un menu delle sole tacche dello studio, e un documento con una
    finestra che non sta fra quelle (lo `hanning` del brano) leggeva `""`:
    `grain.envelope` risultava sempre non salvato sul breakpoint, cosa che
    servita da `make serve` non succede. Senza submodule: nessuna."""
    global _FINESTRE
    if _FINESTRE is None:
        from granstudies.__main__ import _finestre as engine
        _FINESTRE = engine()
    return _FINESTRE


# Il `seed:` dello `study.yml` servito si tiene com'e' scritto, salvo quando un
# test vuole l'altro ramo (#5): `seed_studio=None` e' uno studio che non ne
# dichiara, un numero e' un altro seed.
TIENE = object()


def _pagina(tmp_path, study="001-41", seed_studio=TIENE):
    with open(os.path.join(ROOT, "studies", study, "study.yml")) as fh:
        raw = yaml.safe_load(fh)
    if seed_studio is not TIENE:
        raw.pop("seed", None)
        if seed_studio is not None:
            raw["seed"] = seed_studio
    p = tmp_path / "graph.html"
    p.write_text(build_html(study, lab_completo(raw, CAMPIONI, _finestre(), lambda _p: None,
                                                _predefiniti())))
    return p


def _lab(tmp_path, scenario, prima=None, study="001-41", seed_studio=TIENE):
    """Fa girare lo scenario sulla pagina; l'ultima riga stampata e' JSON."""
    args = ["node", HARNESS, str(_pagina(tmp_path, study, seed_studio))]
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


def _con_testa(st):
    """Il documento con in testa chiavi che il laboratorio non conosce: il
    `seed` (#5 conta che resti), una chiave di PGE-ui, un bpm che non e' 120
    e la durata del brano intero, diversa da quella dello stream."""
    return {"duration": 322.074, "bpm": 90, "seed": 1441,
            "ui_tracks": [{"id": "t1", "streams": [st["stream_id"]]}], "streams": [st]}


@node
def test_le_chiavi_in_testa_al_documento_restano(tmp_path):
    """Aperto e risalvato senza toccare niente, torna identico anche fuori
    dallo stream: prima `labDoc` riscriveva la testa come `{duration, bpm:
    120}` e il `seed` spariva."""
    doc = _con_testa(_stream("stream2"))
    got = _lab(tmp_path, "carica(%s, '/brano/stream2.yml');\n" % json.dumps(doc) + STAMPA)
    assert got == doc


@node
def test_la_durata_toccata_si_scrive_in_testa_e_nello_stream(tmp_path):
    """La durata in testa segue la regola delle altre chiavi: resta quella
    del documento finche' nessuno tocca `durata (s)`; toccata, si scrive li'
    e nello stream. Il resto della testa resta."""
    doc = _con_testa(_stream("stream2"))
    got = _lab(tmp_path, "carica(%s, '/brano/stream2.yml');\n" % json.dumps(doc) + """
const d = document.getElementById('labDur');
d.value = '120';
d.onchange();
console.log(JSON.stringify(labDoc()));
""")
    assert got["duration"] == 120 and got["streams"][0]["duration"] == 120
    assert {k: got[k] for k in ("bpm", "seed", "ui_tracks")} == \
        {k: doc[k] for k in ("bpm", "seed", "ui_tracks")}


@node
def test_un_parametro_assente_non_eredita_lo_schermo_del_documento_di_prima(tmp_path):
    """Aperto dopo un altro documento, un parametro che il nuovo non dichiara
    mostra il valore da cui parte il foglio bianco, non quello rimasto a
    schermo — ne' sui breakpoint (`pan_range`) ne' nei fissi
    (`voices.pitch.unit`). Nel file non entra comunque, finche' non lo si tocca.
    """
    a = dict(_stream("stream3"), pan_range=360)
    st = _stream("stream2")          # niente voci, pan_range 360
    del st["pan_range"]
    got = _lab(tmp_path, _apri(a) + _apri(st) + """
console.log(JSON.stringify({
  schermo: document.getElementById('P:pan_range').value,
  punti: bps.map(b => b.vals['pan_range']),
  unit: document.getElementById('P:voices.pitch.unit').value,
  doc: labDoc()}));
""")
    assert float(got["schermo"]) == 0 and set(got["punti"]) == {0}
    assert got["unit"] == "semitones"
    assert got["doc"]["streams"][0] == st


@node
@engine
def test_un_parametro_assente_si_mostra_al_valore_che_l_engine_suona(tmp_path):
    """Lo stream non dichiara `grain.duration` ne' `grain.envelope`: l'engine
    rende col suo default, e lo schermo deve dire quello, non il punto di
    partenza del foglio bianco (`DEFAULTS`).

    Altrimenti lo schermo mente in silenzio: mostra un valore che l'ascolto
    non ha, e sceglierlo a mano non scrive niente — per `labDoc` e' "non
    toccato" — mentre l'engine continua a rendere il suo. Il documento resta
    senza le due chiavi finche' non le si tocca davvero.
    """
    from granstudies.engine_bridge import parameter_path_defaults
    motore = parameter_path_defaults()
    st = _stream("stream2")
    del st["grain"]["duration"], st["grain"]["envelope"]
    got = _lab(tmp_path, _apri(st) + """
const vista = {
  durate: bps.map(b => b.vals['grain.duration']),
  finestre: bps.map(b => b.vals['grain.envelope']),
  foglio: [DEFAULTS['grain.duration'], DEFAULTS['grain.envelope']]};
// Lo stesso valore, scelto a mano su ogni breakpoint: non e' una modifica.
for (let i = 0; i < bps.length; i++) {
  bpLoad(i);
  document.getElementById('P:grain.duration').value = String(vista.durate[0]);
  bpSave();
}
vista.doc = labDoc();
console.log(JSON.stringify(vista));
""")
    attesi = [motore["grain.duration"], motore["grain.envelope"]]
    # Il caso discrimina solo finche' il foglio bianco parte da altro.
    assert got["foglio"] != attesi
    assert set(got["durate"]) == {attesi[0]}
    assert set(got["finestre"]) == {attesi[1]}
    assert got["doc"]["streams"][0] == st


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
    # Lo `stream_id` di un foglio mai salvato e' il campo `nome` (#5): non
    # c'e' un file da cui prenderlo, e `lab` non era il nome di niente.
    assert (out["stream_id"], out["onset"], out["time_mode"]) == \
        ("nuovo stream", 0, "normalized")
    assert out["grain"]["duration"] == 0.064             # DEFAULTS
    assert out["distribution_mode"] == "uniform"         # base:


@node
def test_nuovo_dopo_un_documento_aperto_non_se_lo_porta_dietro(tmp_path):
    """`nuovo` torna al foglio bianco: lo stream di prima non e' piu' la base.

    E nemmeno il suo nome: `fNew` riporta il campo a `nuovo stream`, quindi
    l'id torna quello del foglio bianco e non quello del file che si aveva
    aperto.
    """
    doc = _lab(tmp_path, _apri(_stream("stream2")) + "fNew(); bpAdd();\n" + STAMPA)
    out = doc["streams"][0]
    assert (out["stream_id"], out["onset"]) == ("nuovo stream", 0)
    assert "read_direction" not in out["grain"]


# --- #5: l'identita' dello stream e' il nome del file -------------------------
# L'RNG dell'engine e' (seed, rng_group o stream_id, componente), quindi l'id
# non e' un'etichetta: decide il suono. Il seed, l'altra meta', sta in
# `tests/test_graph_js.py`.

@node
def test_lo_stream_id_e_il_nome_del_file_non_quello_che_c_era_scritto(tmp_path):
    """Il piano (regola 3): nel master l'id di uno stream importato e' il nome
    del file. Il laboratorio scrive quello, e non passa dal "toccato" della
    #3 — l'id non e' una chiave che si scelga, e' il file."""
    st = _stream("stream2")                     # stream_id: stream2
    doc = _lab(tmp_path, _apri(st, "/brano/risacca.yml") + STAMPA)
    assert doc["streams"][0]["stream_id"] == "risacca"
    # Il resto dello stream resta quello di prima: cambia solo l'identita'.
    atteso = dict(st, stream_id="risacca")
    assert doc["streams"][0] == atteso


@node
@pytest.mark.parametrize("path,atteso", [
    ("/brano/risacca.yml", "risacca"),
    ("/brano/risacca.yaml", "risacca"),
    ("/brano/risacca", "risacca"),          # il server gli mette .yml lui
    ("/brano/ri.sacca.yml", "ri.sacca"),    # il punto nel nome non e' l'estensione
])
def test_l_estensione_non_entra_nell_id(tmp_path, path, atteso):
    doc = _lab(tmp_path, _apri(_stream("stream2"), path) + STAMPA)
    assert doc["streams"][0]["stream_id"] == atteso


@node
def test_il_foglio_mai_salvato_prende_l_id_dal_campo_nome(tmp_path):
    doc = _lab(tmp_path, "document.getElementById('labName').value = 'risacca';\n"
                         "bpAdd();\n" + STAMPA)
    assert doc["streams"][0]["stream_id"] == "risacca"


@node
def test_salva_con_nome_scrive_l_id_nuovo_e_la_riga_di_stato_lo_dice(tmp_path):
    """`salva con nome` cambia il nome, quindi l'id, quindi la realizzazione.

    E' accettato, ma deve dirlo: a orecchio un suono diverso dopo un
    salvataggio non si spiega. L'id e' quello del file di **destinazione**,
    che quando `labDoc` gira non e' ancora `FILE`.
    """
    got = _lab(tmp_path, _apri(_stream("stream2"), "/brano/a.yml") + """
const POST = [];
fetch = async (rotta, opt) => { POST.push(JSON.parse(opt.body));
  return {ok: true, json: async () => ({ok: true, yaml: 'b.yml', path: '/brano/b.yml'})}; };
labPost(false, '/brano/b.yml').then(() => console.log(JSON.stringify({
  id: POST[0].doc.streams[0].stream_id,
  info: document.getElementById('labInfo').textContent,
  file: FILE, nome: document.getElementById('labName').value})));
""")
    assert got["id"] == "b"
    assert "stream_id: b" in got["info"]
    # Il campo `nome` segue il file: il pannello dopo non deve riproporre `a`,
    # e la riga del `nome` non deve dire un id che non e' quello scritto.
    assert (got["file"], got["nome"]) == ("/brano/b.yml", "b")


@node
def test_un_render_su_un_foglio_mai_salvato_non_diventa_il_file(tmp_path):
    """Il server scrive in `live/` col nome ripulito (`_SAFE`), e adottarlo
    cambiava l'id fra il primo render e il secondo: lo stesso documento dava
    due audio. `FILE` e' il file scelto in un pannello, non quello scritto."""
    got = _lab(tmp_path, """
bpAdd();
const POST = [];
fetch = async (rotta, opt) => { POST.push(JSON.parse(opt.body));
  return {ok: true, json: async () => ({ok: true, src: 'x.aif', yaml: 'live/nuovo_stream.yml',
                                        path: '/gen/live/nuovo_stream.yml'})}; };
labPost(true).then(() => labPost(true)).then(() => console.log(JSON.stringify({
  id: POST.map(b => b.doc.streams[0].stream_id), file: FILE,
  nome: document.getElementById('labName').value})));
""")
    assert got["id"] == ["nuovo stream", "nuovo stream"]
    assert (got["file"], got["nome"]) == ("", "nuovo stream")


# Lo stato "salvato" (`SALVATO`) e' com'e' il file su disco: il `• modificato`,
# il `salva` acceso e la conferma prima di `nuovo`/`apri` leggono tutti da li'.

# Cosa la barra dei file dice del lavoro, e se `nuovo` chiederebbe conferma.
STATO_FILE = """{sporco: sporco(), salva: !document.getElementById('fSave').disabled,
  dirty: document.getElementById('fFile').classList.contains('dirty'),
  etichetta: document.getElementById('fFile').textContent,
  info: document.getElementById('labInfo').textContent,
  chiede: (() => { let c = false; const v = confirm;
                   confirm = () => { c = true; return false; };
                   confermaPerdita('x'); confirm = v; return c; })()}"""


@node
def test_un_render_su_un_foglio_mai_salvato_lo_lascia_da_salvare(tmp_path):
    """Il render scrive in `live/`, ma quel file non e' `FILE`: il lavoro resta
    non salvato, e la pagina deve dirlo tutta insieme.

    Prima `SALVATO` si aggiornava a ogni scrittura, anche questa: la barra
    diceva `(non salvato)` senza `• modificato`, il `salva` era spento — su un
    foglio che non ha un file, cioe' proprio dove serve — e `nuovo` buttava il
    lavoro senza chiedere.
    """
    got = _lab(tmp_path, """
bpAdd();
fetch = async () => ({ok: true, json: async () => ({ok: true, src: 'x.aif',
  yaml: 'live/nuovo_stream.yml', path: '/gen/live/nuovo_stream.yml'})});
labPost(true).then(() => console.log(JSON.stringify(%s)));
""" % STATO_FILE)
    assert got["etichetta"] == "(non salvato)"
    assert (got["sporco"], got["dirty"], got["salva"], got["chiede"]) == (True,) * 4


@node
def test_scritto_sul_file_scelto_il_lavoro_e_salvato(tmp_path):
    """L'altra meta': un render o un `salva` che scrivono su `FILE` (o sul
    file appena scelto) rendono pulito il documento, come prima."""
    for azione in ("labPost(false, '/brano/b.yml')", "labPost(true)"):
        got = _lab(tmp_path, _apri(_stream("stream2")) + _tocca(0, "pitch.ratio", 0.75) + """
fetch = async (rotta, opt) => ({ok: true, json: async () => ({ok: true, src: 'x.aif',
  yaml: 'x.yml', path: JSON.parse(opt.body).path})});
%s.then(() => console.log(JSON.stringify(%s)));
""" % (azione, STATO_FILE))
        assert (got["sporco"], got["dirty"], got["salva"], got["chiede"]) == (False,) * 4, azione


@node
def test_aperto_con_la_sua_identita_e_pulito(tmp_path):
    """Un file il cui nome e' gia' il suo `stream_id`, e che ha un seed: il
    laboratorio lo riscriverebbe uguale, quindi niente da salvare e niente da
    dire sull'identita'."""
    got = _lab(tmp_path, "carica(%s, '/brano/stream2.yml');\n"
               % json.dumps(_con_testa(_stream("stream2")))
               + "console.log(JSON.stringify(%s));\n" % STATO_FILE)
    assert (got["sporco"], got["dirty"], got["salva"]) == (False,) * 3
    assert "stream_id" not in got["info"] and "seed" not in got["info"]


@node
def test_aperto_con_un_altro_id_e_da_salvare_e_lo_dice(tmp_path):
    """Il laboratorio scrive l'id del file, non quello che c'era dentro (#5):
    quello su disco non e' piu' il documento che si scriverebbe. Prima la
    pagina lo dava per salvato — `salva` spento, nessuna conferma — e la riga
    di stato taceva, cosi' il primo render suonava diverso dal file aperto
    senza che niente lo avesse detto."""
    doc = _con_testa(_stream("stream2"))                  # seed 1441, id stream2
    got = _lab(tmp_path, "carica(%s, '/brano/risacca.yml');\n" % json.dumps(doc)
               + "console.log(JSON.stringify(%s));\n" % STATO_FILE)
    assert (got["sporco"], got["dirty"], got["salva"], got["chiede"]) == (True,) * 4
    assert "stream_id: risacca (era stream2)" in got["info"]


@node
def test_aperto_senza_seed_prende_quello_dello_studio_e_lo_dice(tmp_path):
    """Stessa cosa per il seed: il file non ne ha, il documento che si
    scriverebbe porta quello dello `study.yml`."""
    doc = _documento(_stream("stream2"))                  # nessun seed
    got = _lab(tmp_path, "carica(%s, '/brano/stream2.yml');\n" % json.dumps(doc)
               + "console.log(JSON.stringify(%s));\n" % STATO_FILE)
    assert (got["sporco"], got["dirty"], got["salva"]) == (True,) * 3
    assert "seed 1441 dallo study.yml" in got["info"]
    assert "stream_id" not in got["info"]


@node
def test_il_nome_di_un_foglio_mai_salvato_entra_nella_bozza(tmp_path):
    """Sul foglio bianco il `nome` e' lo `stream_id`: cambiarlo cambia il
    documento, e un refresh subito dopo non deve riportare l'id di prima."""
    got = _lab(tmp_path, """
bpAdd();
const n = document.getElementById('labName');
n.value = 'risacca';
n.dispatchEvent(new Event('change'));
console.log(localStorage.getItem('lab:001-41'));
""")
    assert got["name"] == "risacca"


@node
def test_l_undo_torna_allo_stream_aperto(tmp_path):
    """Lo stream e la testa del documento: tutti e due stanno nella storia."""
    st = _stream("stream2")
    doc = _con_testa(st)
    got = _lab(tmp_path, "carica(%s, '/brano/stream2.yml');\n" % json.dumps(doc)
               + _tocca(0, "pitch.ratio", 0.75) + """
const toccato = labDoc();
vaiStoria(-1);
const annullato = labDoc();
vaiStoria(1);
console.log(JSON.stringify([toccato, annullato, labDoc()]));
""")
    toccato, annullato, rifatto = got
    assert annullato == doc
    assert toccato == rifatto and toccato["streams"][0]["pitch"]["ratio"][0] == [0, 0.75]
    assert toccato["seed"] == 1441


@node
def test_la_bozza_riporta_lo_stream_conservato(tmp_path):
    """Un refresh a meta' lavoro: torna anche quello che il laboratorio non
    conosce, non solo i breakpoint."""
    st = _stream("stream2")
    bozza = _lab(tmp_path, "carica(%s, '/brano/stream2.yml');\n" % json.dumps(_con_testa(st))
                 + _tocca(0, "pitch.ratio", 0.75)
                 + "console.log(localStorage.getItem('lab:001-41'));\n")
    bozza["sess"] = "S"
    prima = """
localStorage.setItem('lab:001-41', %s);
fetch = async () => ({ok: true, json: async () => ({ok: true, sessione: 'S', recenti: []})});
""" % json.dumps(json.dumps(bozza))
    doc = _lab(tmp_path, STAMPA, prima=prima)
    assert (doc["seed"], doc["bpm"], doc["duration"]) == (1441, 90, 322.074)
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


# --- #9 sopra #3 e #4: uno stream aperto coi tempi in secondi -----------------
# Senza `time_mode: normalized` l'engine legge i tempi in secondi. Il
# laboratorio li porta a frazioni per leggerli (`tempiFrazione`) e li riscrive
# in secondi (`scalaTempi`) — anche dentro un `{type, points}`, che #4 legge e
# che la sola #9 lasciava com'era, cioe' in secondi letti come frazioni.

DUR_S = 100.0


def _in_secondi(st):
    """stream4 com'e' scritto senza `time_mode`: gli inviluppi in secondi."""
    st = json.loads(json.dumps(st))
    st.pop("time_mode", None)
    st["duration"] = DUR_S

    def sec(v):
        if isinstance(v, dict):
            return dict(v, points=sec(v["points"]))
        return [[round(p[0] * DUR_S, 6)] + p[1:] for p in v]

    st["fill_factor"] = sec(st["fill_factor"])
    st["grain"]["duration"] = sec(st["grain"]["duration"])
    return st


@node
def test_in_secondi_aperto_e_risalvato_e_lo_stesso_stream(tmp_path):
    st = _in_secondi(_stream("stream4"))
    got = _lab(tmp_path, _apri(st) + "console.log(JSON.stringify({ts: bps.map(b => b.t), "
                                     "doc: labDoc()}));\n")
    assert got["doc"]["streams"][0] == st
    assert all(0 <= t <= 1 for t in got["ts"]) and 0.0926 in got["ts"]


@node
@engine
def test_in_secondi_ogni_breakpoint_vale_quanto_per_il_motore(tmp_path):
    Envelope = _motore(tmp_path)
    st = _in_secondi(_stream("stream4"))
    got = _lab(tmp_path, _apri(st) + "console.log(JSON.stringify(bps));\n")
    for path in ("fill_factor", "grain.duration"):
        env = Envelope(_leggi(st, path))
        for b in got:
            assert _vicini(b["vals"][path], env.evaluate(b["t"] * DUR_S)), (path, b["t"])


@node
@engine
def test_in_secondi_un_type_points_toccato_si_scrive_in_secondi(tmp_path):
    """Toccato resta `{type: cubic}`, coi tempi in secondi, e l'engine vale su
    ogni breakpoint quanto il laboratorio mostra. `grain.duration`, non
    toccato, resta com'era."""
    Envelope = _motore(tmp_path)
    st = _in_secondi(_stream("stream4"))
    got = _lab(tmp_path, _apri(st) + """
const i = bps.findIndex(b => Math.abs(b.t - 0.1631) < 1e-9);
bpLoad(i); document.getElementById('P:fill_factor').value = '0.9'; bpSave();
console.log(JSON.stringify({doc: labDoc(), bps}));
""")
    out = got["doc"]["streams"][0]
    ff = out["fill_factor"]
    assert isinstance(ff, dict) and ff["type"] == "cubic"
    assert [16.31, 0.9] in ff["points"] and ff["points"][-1][0] == DUR_S
    env = Envelope(ff)
    for b in got["bps"]:
        assert _vicini(env.evaluate(b["t"] * DUR_S), b["vals"]["fill_factor"]), b["t"]
    assert out["grain"]["duration"] == st["grain"]["duration"]
    assert "time_mode" not in out


# --- #6: due editor, un file --------------------------------------------------
# Lo stesso file aperto qui e in PGE-ui (regola 7 del piano). Il laboratorio
# ricorda la firma del file che ha letto e la manda a ogni scrittura; il server
# non scrive se su disco non e' piu' quella.
#
# Il "disco" sta nel `fetch` finto, con le regole del server vero
# (`gia_su_disco` e poi `cambiato_su_disco`, verificate in
# `tests/test_serve.py`): `DISCO` e' il documento su disco, `FDISCO` la sua
# firma, `scriveAltri` l'altro editor che salva. Un documento uguale a quello
# su disco non si scrive e non e' un file cambiato: la firma resta quella del
# file. Qui "uguale" e' il JSON a chiavi ordinate, perche' in JS `4` e `4.0`
# sono lo stesso numero; la distinzione dei tipi la prova `test_serve.py`.
# `/stato` risponde da se', perche' `apriPath` e `fSave` chiedono i recenti e
# quella non e' una scrittura.

def _doppio(disco):
    return """
const POST = [];
let DISCO = %s, FDISCO = 'sha256:letta';
function scriveAltri(doc) { DISCO = doc; FDISCO = 'sha256:altro'; }
const discoCanonico = v => JSON.stringify(v, (k, x) =>
  x && typeof x === 'object' && !Array.isArray(x)
    ? Object.keys(x).sort().reduce((o, c) => (o[c] = x[c], o), {}) : x);
fetch = async (rotta, opt) => {
  if (rotta === '/stato')
    return {ok: true, json: async () => ({ok: true, sessione: 'S', recenti: []})};
  const body = JSON.parse(opt.body);
  POST.push(Object.assign({rotta}, body));
  if (rotta === 'open') {
    // Firmato alla richiesta, come fa il server: una firma letta dopo sarebbe
    // di un file che intanto puo' essere cambiato di nuovo.
    const d = DISCO, f = FDISCO;
    return {ok: true, json: async () =>
      ({ok: true, doc: d, path: body.path, firma: f})};
  }
  if (discoCanonico(body.doc) === discoCanonico(DISCO))
    return {ok: true, json: async () =>
      ({ok: true, src: 'x.aif', yaml: 'r.yml', path: body.path, firma: FDISCO})};
  if (body.firma && body.firma !== FDISCO && !body.sovrascrivi)
    return {ok: true, json: async () => ({ok: false, cambiato: true,
      error: "il file e' cambiato su disco da quando l'hai letto."})};
  DISCO = body.doc; FDISCO = 'sha256:scritta';
  return {ok: true, json: async () =>
    ({ok: true, src: 'x.aif', yaml: 'r.yml', path: body.path, firma: FDISCO})};
};
""" % json.dumps(disco)


# Cosa si guarda dopo: le richieste andate al server (rotta, firma mandata,
# sovrascrittura chiesta, e il `volume` del documento scritto, che e' il
# marcatore di quale versione e' finita nel file), la firma che il laboratorio
# ricorda, la riga di stato, se la domanda e' aperta, e se il render e' partito.
VISTO = """
console.log(JSON.stringify({
  post: POST.map(p => ({rotta: p.rotta, firma: p.firma || null,
                        sovrascrivi: !!p.sovrascrivi,
                        volume: p.doc ? p.doc.streams[0].volume : null})),
  firma: FIRMA, file: FILE, sporco: sporco(), daPerdere: daPerdere(),
  info: document.getElementById('labInfo').textContent,
  domanda: !document.getElementById('fCambiato').hidden,
  disco: DISCO.streams[0].volume, reso: ULTIMO || null,
  ratio: labDoc().streams[0].pitch.ratio,
}));
"""

VOL_MIO, VOL_ALTRI = -11, -7


def _mio_e_altrui(sid="stream2"):
    """Lo stesso stream nelle due versioni: la mia (quella che apro) e quella
    che l'altro editor scrive su disco mentre io ci lavoro. Il `volume` e' il
    marcatore: il laboratorio non lo tocca, quindi resta quello del documento
    aperto (#3) e dice quale versione e' stata scritta."""
    st = dict(_stream(sid), volume=VOL_MIO)
    return _documento(st), _documento(dict(st, volume=VOL_ALTRI))


@node
def test_senza_modifiche_proprie_il_file_cambiato_si_rilegge_e_il_render_prosegue(tmp_path):
    """Niente da perdere, niente da decidere: si rilegge e si riprova, e il
    render prosegue sulla versione su disco — quella che l'altro editor ha
    appena scritto e' quella che si vuole sentire. La riga di stato lo dice,
    perche' il documento a schermo non e' piu' quello di prima."""
    mio, altrui = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml')
  .then(() => { scriveAltri(%s); return labRender(); })
  .then(() => { %s });
""" % (json.dumps(altrui), VISTO))
    assert [p["rotta"] for p in got["post"]] == ["open", "render", "open", "render"]
    # Il primo render manda la firma letta aprendo, il secondo quella riletta.
    assert [p["firma"] for p in got["post"]] == [
        None, "sha256:letta", None, "sha256:altro"]
    # Ed e' la versione su disco che si e' scritta e che si sente.
    assert got["post"][3]["volume"] == VOL_ALTRI
    assert (got["firma"], got["domanda"]) == ("sha256:scritta", False)
    assert got["reso"].startswith("x.aif")
    assert "riletto" in got["info"]


def _mio_e_altrui_gia_del_laboratorio():
    """Come `_mio_e_altrui`, ma il file ha gia' l'identita' che il laboratorio
    scriverebbe (lo `stream_id` del suo nome, il `seed` dello `study.yml`): e'
    il documento che PGE-ui riscrive tenendo seed e id del file
    (DMGiulioRomano/PGE-ui#184). Aperto, e' gia' quello che si scriverebbe."""
    mio, altrui = _mio_e_altrui("stream2")
    for d in (mio, altrui):
        d["seed"] = 1441
        d["streams"][0]["stream_id"] = "risacca"
    return mio, altrui


@node
def test_senza_toccare_niente_il_render_non_riscrive_il_file(tmp_path):
    """Aperto e reso senza toccare niente: il documento e' gia' quello su
    disco, e il server non lo riscrive (`gia_su_disco`). Se lo riscrivesse,
    ogni ascolto cambierebbe i byte del file e la guardia dell'altro editor
    parlerebbe a vuoto. La firma resta quella letta, e il render parte."""
    mio, _ = _mio_e_altrui_gia_del_laboratorio()
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml')
  .then(() => labRender())
  .then(() => { %s });
""" % VISTO)
    assert [p["rotta"] for p in got["post"]] == ["open", "render"]
    assert got["firma"] == "sha256:letta"
    assert got["reso"].startswith("x.aif")
    assert (got["sporco"], got["daPerdere"], got["domanda"]) == (False, False, False)


@node
def test_riletto_senza_modifiche_proprie_il_file_dell_altro_editor_non_si_riscrive(tmp_path):
    """Il caso per cui `gia_su_disco` c'e': l'altro editor ha scritto, io non
    ho niente da perdere, quindi rileggo e rendo. Il documento che il secondo
    `/render` manda e' quello appena riletto, e il file resta dell'altro
    editor: la firma che ricordo e' la sua, e al suo giro dopo la sua guardia
    non trova niente di cambiato."""
    mio, altrui = _mio_e_altrui_gia_del_laboratorio()
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml')
  .then(() => { scriveAltri(%s); return labRender(); })
  .then(() => { %s });
""" % (json.dumps(altrui), VISTO))
    assert [p["rotta"] for p in got["post"]] == ["open", "render", "open", "render"]
    assert got["post"][3]["volume"] == VOL_ALTRI
    assert (got["firma"], got["disco"]) == ("sha256:altro", VOL_ALTRI)
    assert got["reso"].startswith("x.aif") and "riletto" in got["info"]


@node
def test_con_modifiche_proprie_si_chiede_e_non_si_scrive(tmp_path):
    """La decisione e' dell'utente: due bottoni accanto al nome del file, e
    finche' non si risponde non si scrive niente — che e' anche la terza
    risposta, quella che non deve costare un click."""
    mio, altrui = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml').then(() => {
  %s
  scriveAltri(%s);
  return labRender();
}).then(() => { %s });
""" % (_tocca(0, "pitch.ratio", 0.75), json.dumps(altrui), VISTO))
    assert [p["rotta"] for p in got["post"]] == ["open", "render"]
    assert got["domanda"] is True
    assert "modifiche non salvate" in got["info"]
    assert "cambiato su disco" in got["info"]
    # Non si e' scritto: su disco c'e' ancora il lavoro dell'altro editor, e
    # il render non e' partito.
    assert got["disco"] == VOL_ALTRI and got["reso"] is None
    # E le modifiche proprie sono dove le ho lasciate.
    assert got["ratio"][0] == [0, 0.75]


@node
def test_sovrascrivi_scrive_le_proprie_modifiche(tmp_path):
    """La risposta passa dal bottone, e riprende la scrittura da dove si era
    interrotta: era stata chiesta, e la risposta dice solo con quale
    documento farla."""
    mio, altrui = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml').then(() => {
  %s
  scriveAltri(%s);
  return labRender();
}).then(() => document.getElementById('fOverwrite').onclick())
  .then(() => { %s });
""" % (_tocca(0, "pitch.ratio", 0.75), json.dumps(altrui), VISTO))
    assert [p["rotta"] for p in got["post"]] == ["open", "render", "render"]
    assert got["post"][2]["sovrascrivi"] is True
    # Il documento scritto e' il mio, modifiche comprese.
    assert got["post"][2]["volume"] == VOL_MIO
    assert got["ratio"][0] == [0, 0.75]
    assert (got["firma"], got["domanda"]) == ("sha256:scritta", False)
    assert got["reso"].startswith("x.aif")


@node
def test_ricarica_perde_le_proprie_modifiche_e_non_le_fa_tornare_con_un_undo(tmp_path):
    """"Ricarica" e' un `apri` dello stesso file: la storia si azzera, o un
    undo riporterebbe indietro una versione che su disco non c'e' piu' — e la
    scrittura dopo la riscriverebbe."""
    mio, altrui = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml').then(() => {
  %s
  scriveAltri(%s);
  return labRender();
}).then(() => document.getElementById('fReload').onclick())
  .then(() => { vaiStoria(-1); %s });
""" % (_tocca(0, "pitch.ratio", 0.75), json.dumps(altrui), VISTO))
    assert [p["rotta"] for p in got["post"]] == ["open", "render", "open", "render"]
    assert got["post"][3]["firma"] == "sha256:altro"
    assert got["post"][3]["volume"] == VOL_ALTRI
    # Nemmeno un undo riporta il 0.75: la storia e' quella del file riletto.
    assert got["ratio"] == _stream("stream2")["pitch"]["ratio"]
    assert got["domanda"] is False


@node
def test_la_firma_e_del_file_aperto_non_di_un_altro(tmp_path):
    """Un `salva con nome` scrive un file che il laboratorio non ha letto, e
    della sovrascrittura ha chiesto il pannello nativo. Mandare la firma
    accuserebbe un file qualunque di essere cambiato — cosa che e', rispetto a
    un altro file."""
    mio, _ = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/a.yml')
  .then(() => labPost(false, '/brano/b.yml'))
  .then(() => { %s });
""" % VISTO)
    assert [p["rotta"] for p in got["post"]] == ["open", "render"]
    assert got["post"][1]["firma"] is None
    assert (got["file"], got["firma"]) == ("/brano/b.yml", "sha256:scritta")


@node
def test_due_salvataggi_di_fila_il_secondo_non_si_accusa_da_solo(tmp_path):
    """La firma di cio' che si e' appena scritto torna dal server e prende il
    posto di quella letta: senza, il salvataggio dopo manderebbe la firma di
    prima e si rifiuterebbe da se'."""
    mio, _ = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml').then(() => {
  %s
  return fSave(false);
}).then(() => {
  %s
  return fSave(false);
}).then(() => { %s });
""" % (_tocca(0, "pitch.ratio", 0.75), _tocca(0, "pitch.ratio", 0.5), VISTO))
    assert [p["rotta"] for p in got["post"]] == ["open", "render", "render"]
    assert [p["firma"] for p in got["post"]] == [
        None, "sha256:letta", "sha256:scritta"]
    assert got["domanda"] is False and got["ratio"][0] == [0, 0.5]


@node
def test_la_firma_sopravvive_a_un_refresh(tmp_path):
    """Senza, il refresh disarmerebbe la guardia proprio sul file su cui si
    stava lavorando: la scrittura dopo passerebbe senza confronto."""
    mio, altrui = _mio_e_altrui()
    bozza = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml').then(() => {
  %s
  console.log(localStorage.getItem('lab:001-41'));
});
""" % _tocca(0, "pitch.ratio", 0.75))
    assert bozza["firma"] == "sha256:letta"
    bozza["sess"] = "S"
    prima = """
localStorage.setItem('lab:001-41', %s);
fetch = async () => ({ok: true, json: async () => ({ok: true, sessione: 'S', recenti: []})});
""" % json.dumps(json.dumps(bozza))
    # Riaperta la pagina, l'altro editor ha scritto: la guardia e' ancora
    # armata e, con le modifiche riprese dalla bozza, chiede.
    got = _lab(tmp_path, _doppio(altrui) + """
FDISCO = 'sha256:altro';
labRender().then(() => { %s });
""" % VISTO, prima=prima)
    assert got["post"][0]["firma"] == "sha256:letta"
    assert got["domanda"] is True and got["reso"] is None


@node
def test_una_scrittura_nuova_sostituisce_la_domanda_in_attesa(tmp_path):
    """La via d'uscita piu' ovvia dal "cambiato su disco" e' salvare le proprie
    da un'altra parte. La domanda riguardava quella scrittura: se ne resta
    aperta una a cui nessuno risponde piu', i due bottoni dicono che c'e'
    qualcosa di fermo quando non c'e' niente."""
    mio, altrui = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml').then(() => {
  %s
  scriveAltri(%s);
  return labRender();
}).then(() => labPost(false, '/brano/mie.yml'))
  .then(() => { %s });
""" % (_tocca(0, "pitch.ratio", 0.75), json.dumps(altrui), VISTO))
    assert [p["rotta"] for p in got["post"]] == ["open", "render", "render"]
    assert got["post"][2]["volume"] == VOL_MIO        # le mie, in un file mio
    assert (got["file"], got["domanda"]) == ("/brano/mie.yml", False)


@node
def test_se_il_file_cambia_mentre_lo_rileggo_lo_si_dice_invece_di_rincorrerlo(tmp_path):
    """Si riprova una volta sola. A rincorrere un file che qualcuno riscrive
    continuamente non si finisce mai, e intanto non si scrive niente: meglio
    dirlo, che e' una cosa da guardare."""
    mio, altrui = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + """
// L'altro editor salva di nuovo appena abbiamo riletto: la firma che ci ha
// dato e' gia' vecchia quando proviamo a scrivere.
const server = fetch;
fetch = async (rotta, opt) => {
  const r = await server(rotta, opt);
  if (rotta === 'open' && POST.length > 1) FDISCO = 'sha256:e-ancora';
  return r;
};
apriPath('/brano/risacca.yml')
  .then(() => { scriveAltri(%s); return labRender(); })
  .then(() => { %s });
""" % (json.dumps(altrui), VISTO))
    assert [p["rotta"] for p in got["post"]] == ["open", "render", "open", "render"]
    assert "cambia mentre lo rileggo" in got["info"]
    assert got["reso"] is None            # il render non e' partito
    # E non e' una domanda: senza modifiche proprie non c'e' niente da
    # decidere, solo da riprovare.
    assert got["domanda"] is False


@node
def test_l_identita_riscritta_non_e_lavoro_da_perdere(tmp_path):
    """Dalla #5 il laboratorio riscrive l'identita' — `stream_id` col nome del
    file, e il `seed` dello studio se il documento non ne ha — e `SALVATO` ne
    tiene conto (`comeLetto`): un file il cui id non e' il suo nome, e ogni
    file scritto prima della #5, e' `• modificato` dal primo istante.

    Quella differenza una rilettura la ricalcola identica, quindi non e'
    lavoro da perdere: la guardia legge `daPerdere()` e non `sporco()`.
    Chiedere li' direbbe "hai modifiche non salvate" a chi non ha toccato
    niente, e su quella popolazione — che e' la maggioranza — la regola 7
    vuole che si rilegga.
    """
    mio, altrui = _mio_e_altrui()             # stream_id: stream2, nessun seed
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml').then(() => {
  const subito = {sporco: sporco(), daPerdere: daPerdere()};
  scriveAltri(%s);
  return labRender().then(() => console.log(JSON.stringify({subito,
    post: POST.map(p => p.rotta),
    domanda: !document.getElementById('fCambiato').hidden,
    info: document.getElementById('labInfo').textContent})));
});
""" % json.dumps(altrui))
    # Le due domande divergono, ed e' qui che si vede.
    assert got["subito"] == {"sporco": True, "daPerdere": False}
    assert got["post"] == ["open", "render", "open", "render"]
    assert got["domanda"] is False
    assert "modifiche non salvate" not in got["info"]


@node
def test_dopo_un_salvataggio_non_c_e_piu_niente_da_perdere(tmp_path):
    """Salvato, il file E' il documento: `SCRITTO0` si sposta col salvataggio,
    o il lavoro appena messo al sicuro continuerebbe a contare come da
    perdere e la domanda comparirebbe su un documento che non ha piu' niente
    di proprio."""
    mio, altrui = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml').then(() => {
  %s
  return fSave(false);
}).then(() => {
  const prima = {sporco: sporco(), daPerdere: daPerdere()};
  scriveAltri(%s);
  return labRender().then(() => console.log(JSON.stringify({prima,
    post: POST.map(p => p.rotta),
    domanda: !document.getElementById('fCambiato').hidden})));
});
""" % (_tocca(0, "pitch.ratio", 0.75), json.dumps(altrui)))
    assert got["prima"] == {"sporco": False, "daPerdere": False}
    # Salvataggio, render rifiutato, rilettura, render: nessuna domanda.
    assert got["post"] == ["open", "render", "render", "open", "render"]
    assert got["domanda"] is False


@node
def test_un_refresh_senza_lavoro_proprio_rilegge_invece_di_chiedere(tmp_path):
    """L'altra meta' della bozza: `FIRMA` tiene armata la guardia, `SCRITTO0`
    le fa dare la risposta giusta. Senza, dopo un refresh ogni file risulta
    tutto lavoro proprio e la domanda compare sempre."""
    mio, altrui = _mio_e_altrui()
    bozza = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml')
  .then(() => console.log(localStorage.getItem('lab:001-41')));
""")
    bozza["sess"] = "S"
    prima = """
localStorage.setItem('lab:001-41', %s);
fetch = async () => ({ok: true, json: async () => ({ok: true, sessione: 'S', recenti: []})});
""" % json.dumps(json.dumps(bozza))
    got = _lab(tmp_path, _doppio(altrui) + """
FDISCO = 'sha256:altro';
labRender().then(() => { %s });
""" % VISTO, prima=prima)
    assert [p["rotta"] for p in got["post"]] == ["render", "open", "render"]
    assert got["domanda"] is False and got["reso"].startswith("x.aif")


@node
def test_salvato_e_poi_un_refresh_la_scrittura_dopo_non_si_accusa(tmp_path):
    """La bozza va riscritta dopo ogni scrittura: e' li' che stanno `FIRMA`,
    `SALVATO` e `SCRITTO0`. Senza, un refresh dopo un salvataggio riprendeva
    quelli di prima — la firma letta aprendo, il documento com'era aperto — e
    il giro dopo mandava al server la firma di un file che il laboratorio
    stesso aveva riscritto: "cambiato su disco", e la domanda "hai modifiche
    non salvate" su un documento appena salvato."""
    mio, _ = _mio_e_altrui()
    bozza = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml').then(() => {
  %s
  return fSave(false);
}).then(() => console.log(localStorage.getItem('lab:001-41')));
""" % _tocca(0, "pitch.ratio", 0.75))
    assert bozza["firma"] == "sha256:scritta"
    bozza["sess"] = "S"
    prima = """
localStorage.setItem('lab:001-41', %s);
fetch = async () => ({ok: true, json: async () => ({ok: true, sessione: 'S', recenti: []})});
""" % json.dumps(json.dumps(bozza))
    # Sul disco c'e' quello che il laboratorio ha scritto, e nessun altro l'ha
    # toccato.
    got = _lab(tmp_path, _doppio(mio) + """
FDISCO = 'sha256:scritta';
const fuori = {sporco: sporco(), daPerdere: daPerdere()};
labRender().then(() => { %s });
""" % VISTO.replace("console.log(JSON.stringify({",
                    "console.log(JSON.stringify({fuori,"), prima=prima)
    assert got["fuori"] == {"sporco": False, "daPerdere": False}
    assert [p["firma"] for p in got["post"]] == ["sha256:scritta"]
    assert got["domanda"] is False and got["reso"].startswith("x.aif")


@node
def test_un_render_fallito_dopo_la_scrittura_non_fa_accusare_il_giro_dopo(tmp_path):
    """Il server scrive lo YAML prima di rendere: se l'engine poi fallisce (un
    valore fuori bounds, la cosa piu' comune in un laboratorio) il file e' gia'
    quello nuovo, e la risposta ne porta la firma. La pagina la prende come
    dopo una scrittura riuscita — o il render dopo, corretto il valore,
    trovava il file "cambiato su disco" per mano propria e chiedeva."""
    mio, _ = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + """
const server = fetch;
let muore = true;
fetch = async (rotta, opt) => {
  const r = await server(rotta, opt);
  if (rotta !== 'render' || !muore) return r;
  muore = false;
  const out = await r.json();
  return {ok: true, json: async () => ({ok: false, error: 'ValueError: bounds',
                                        path: out.path, yaml: out.yaml,
                                        firma: out.firma})};
};
apriPath('/brano/risacca.yml').then(() => {
  %s
  return labRender();
}).then(() => {
  const dopo = {info: document.getElementById('labInfo').textContent,
                sporco: sporco(), daPerdere: daPerdere()};
  %s
  return labRender().then(() => dopo);
}).then(dopo => { %s });
""" % (_tocca(0, "pitch.ratio", 0.75), _tocca(0, "pitch.ratio", 0.5),
       VISTO.replace("console.log(JSON.stringify({",
                     "console.log(JSON.stringify({dopo,")))
    # Il fallimento si dice, e il file scritto non e' piu' "modificato".
    assert "bounds" in got["dopo"]["info"]
    assert got["dopo"]["sporco"] is False and got["dopo"]["daPerdere"] is False
    assert [p["firma"] for p in got["post"]] == [
        None, "sha256:letta", "sha256:scritta"]
    assert got["domanda"] is False and got["reso"].startswith("x.aif")


@node
def test_riletto_un_file_che_non_e_piu_un_documento_non_si_riprova(tmp_path):
    """Se l'altro editor ha lasciato un file senza stream, la rilettura non
    carica niente: riprovare la scrittura col documento di prima e la firma di
    prima darebbe un secondo "cambiato" e la riga di stato direbbe "cambia
    mentre lo rileggo", che non e' vero — il motivo e' un altro, e va detto."""
    mio, _ = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml')
  .then(() => { scriveAltri({streams: []}); return labRender(); })
  .then(() => { %s });
""" % VISTO.replace("disco: DISCO.streams[0].volume", "disco: null"))
    assert [p["rotta"] for p in got["post"]] == ["open", "render", "open"]
    assert "non e' un documento con stream" in got["info"]
    assert "rileggo" not in got["info"]
    assert got["firma"] == "sha256:letta" and got["reso"] is None


# --- i valori a schermo e il render --------------------------------------------
# Il render suona i breakpoint, non lo schermo: un valore scritto nel campo e
# non confermato (`salva modifica`, `applica a tutti`, `+ breakpoint`) non sta
# nel documento che si rende. Prima di rendere si chiede se scartarlo; col
# bottone `scarto automatico` acceso si scarta senza chiedere. In tutti e due
# i casi la riga di stato dice cosa e' stato scartato.

def _schermo(risposta):
    """Il `confirm` della pagina, registrato: cosa ha chiesto, e la risposta."""
    return "const CHIESTO = [];\nconfirm = m => { CHIESTO.push(m); return %s; };\n" % (
        "true" if risposta else "false")


# Scritto nel campo del breakpoint 2, e non confermato: il gesto di chi prova un
# valore e preme subito `rendi e ascolta`.
A_SCHERMO = ("bpLoad(1); document.getElementById('P:pitch.ratio').value = '0.75';"
             " document.getElementById('P:pitch.ratio').onchange();\n")

VISTO_SCHERMO = """
const visto = () => ({
  chiesto: CHIESTO,
  resi: POST.filter(p => p.rotta === 'render').map(p => p.doc.streams[0].pitch.ratio),
  campo: document.getElementById('P:pitch.ratio').value,
  cambiati: cambiati(),
  info: document.getElementById('labInfo').textContent,
  reso: ULTIMO || null,
  auto: document.getElementById('labScarta').classList.contains('on'),
});
"""


@node
def test_valori_a_schermo_non_salvati_si_chiede_e_no_li_tiene(tmp_path):
    """"No" e' la risposta che non perde niente: il render non parte, i valori
    restano nei campi, e la riga di stato dice come metterli nel documento."""
    mio, _ = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + _schermo(False) + VISTO_SCHERMO + """
apriPath('/brano/risacca.yml').then(() => {
  %s
  return labRender();
}).then(() => console.log(JSON.stringify(visto())));
""" % A_SCHERMO)
    assert len(got["chiesto"]) == 1
    assert "breakpoint 2" in got["chiesto"][0] and "pitch.ratio" in got["chiesto"][0]
    assert got["resi"] == [] and got["reso"] is None
    assert got["campo"] == "0.75" and got["cambiati"] == ["pitch.ratio"]
    assert "salva modifica" in got["info"] and "pitch.ratio" in got["info"]


@node
def test_valori_a_schermo_si_li_scarta_rende_e_un_undo_li_riporta(tmp_path):
    """"Si'": lo schermo torna al breakpoint, il render parte e la riga di stato
    dice cosa si e' scartato. Scartare e' un passo della storia come gli altri:
    un undo rimette i valori nei campi."""
    mio, _ = _mio_e_altrui()
    ratio = _stream("stream2")["pitch"]["ratio"]
    got = _lab(tmp_path, _doppio(mio) + _schermo(True) + VISTO_SCHERMO + """
apriPath('/brano/risacca.yml').then(() => {
  %s
  return labRender();
}).then(() => {
  const dopo = visto();
  vaiStoria(-1);
  console.log(JSON.stringify(Object.assign(dopo,
    {undo: document.getElementById('P:pitch.ratio').value})));
});
""" % A_SCHERMO)
    assert len(got["chiesto"]) == 1
    # Il documento reso e' quello dei breakpoint: lo 0.75 non c'e'.
    assert len(got["resi"]) == 1 and got["resi"][0] == ratio
    assert got["reso"].startswith("x.aif")
    assert got["cambiati"] == [] and got["campo"] != "0.75"
    assert "scartati" in got["info"] and "pitch.ratio" in got["info"]
    assert got["undo"] == "0.75"


@node
def test_con_lo_scarto_automatico_acceso_non_si_chiede(tmp_path):
    """Il bottone accanto al render: acceso, scartare e' la risposta data una
    volta per tutte. Non si chiede, ma la riga di stato lo dice lo stesso —
    scartare in silenzio e' proprio cio' che la domanda e' venuta a togliere."""
    mio, _ = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + _schermo(False) + VISTO_SCHERMO + """
apriPath('/brano/risacca.yml').then(() => {
  document.getElementById('labScarta').onclick();
  %s
  return labRender();
}).then(() => console.log(JSON.stringify(visto())));
""" % A_SCHERMO)
    assert got["auto"] is True and got["chiesto"] == []
    assert len(got["resi"]) == 1 and got["reso"].startswith("x.aif")
    assert got["cambiati"] == []
    assert "scartati" in got["info"] and "pitch.ratio" in got["info"]


@node
def test_senza_valori_a_schermo_non_si_chiede_niente(tmp_path):
    mio, _ = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + _schermo(False) + VISTO_SCHERMO + """
apriPath('/brano/risacca.yml')
  .then(() => labRender())
  .then(() => console.log(JSON.stringify(visto())));
""")
    assert got["chiesto"] == [] and len(got["resi"]) == 1
    assert "scartati" not in got["info"]


@node
def test_lo_scarto_automatico_parte_spento(tmp_path):
    """Spento a ogni apertura della pagina: scartare senza chiedere e' una
    scelta, non il comportamento di partenza."""
    got = _lab(tmp_path, _schermo(False) + """
const b = document.getElementById('labScarta');
const stati = [b.classList.contains('on')];
b.onclick(); stati.push(b.classList.contains('on'));
b.onclick(); stati.push(b.classList.contains('on'));
console.log(JSON.stringify(stati));
""")
    assert got == [False, True, False]


# Con `segui il render` acceso lo schermo non e' lavoro: e' la lettura degli
# inviluppi al cursore, che `mostraSegui` riscrive a ogni frame (anche in
# pausa). Lontano dal breakpoint selezionato i campi ne differiscono, e
# `cambiati()` li conta: chi chiede se scartarli chiederebbe di valori che
# nessuno ha scritto. Il cursore va a meta' fra i primi due breakpoint, dove
# gli inviluppi di stream2 che si muovono stanno fra i due valori.
SEGUE = """
SEGUI = true; LAB_AUDIO = true;
mostraSegui((bps[0].t + bps[1].t) / 2 * durata());
const letti = cambiati();
"""


@node
def test_con_segui_il_render_la_lettura_a_schermo_non_e_un_valore_da_scartare(tmp_path):
    """Il render non chiede, non dice di aver scartato niente, e parte: lo
    schermo e' la lettura, non un valore scritto e non salvato."""
    mio, _ = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + _schermo(False) + VISTO_SCHERMO + """
apriPath('/brano/risacca.yml').then(() => {
  %s
  return labRender().then(() => letti);
}).then(letti => console.log(JSON.stringify(Object.assign(visto(), {letti}))));
""" % SEGUE)
    assert got["letti"]                        # lo scenario dice qualcosa
    assert got["chiesto"] == []
    assert len(got["resi"]) == 1 and got["reso"].startswith("x.aif")
    assert "scartati" not in got["info"]


@node
def test_con_segui_il_render_il_file_cambiato_si_rilegge_senza_chiedere(tmp_path):
    """Per la stessa ragione la lettura non e' lavoro da perdere: senza
    modifiche proprie il file cambiato su disco si rilegge e il render
    prosegue, come a schermo fermo."""
    mio, altrui = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml').then(() => {
  %s
  scriveAltri(%s);
  return labRender();
}).then(() => { %s });
""" % (SEGUE, json.dumps(altrui), VISTO))
    assert [p["rotta"] for p in got["post"]] == ["open", "render", "open", "render"]
    assert got["domanda"] is False and got["reso"].startswith("x.aif")


@node
def test_salva_su_un_file_cambiato_con_valori_a_schermo_chiede_invece_di_rileggere(tmp_path):
    """`salva` scrive i breakpoint senza chiedere, e i valori a schermo restano
    nei campi. Ma se il file e' cambiato su disco la rilettura li butterebbe —
    in silenzio, e senza undo, perche' `carica` azzera la storia. Sono lavoro
    proprio come i breakpoint toccati: si chiede, e finche' non si risponde i
    campi restano come sono."""
    mio, altrui = _mio_e_altrui()
    got = _lab(tmp_path, _doppio(mio) + """
apriPath('/brano/risacca.yml').then(() => {
  %s
  scriveAltri(%s);
  return fSave(false);
}).then(() => { %s });
""" % (A_SCHERMO, json.dumps(altrui), VISTO.replace(
        "console.log(JSON.stringify({",
        "console.log(JSON.stringify({campo: document.getElementById('P:pitch.ratio').value,")))
    assert [p["rotta"] for p in got["post"]] == ["open", "render"]
    assert got["domanda"] is True
    assert "modifiche non salvate" in got["info"]
    assert got["campo"] == "0.75"
    assert got["disco"] == VOL_ALTRI
