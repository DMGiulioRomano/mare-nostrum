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
    p.write_text(build_html(study, lab_completo(raw, CAMPIONI, {}, lambda _p: None,
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
