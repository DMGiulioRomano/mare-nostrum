"""Il brano passa agli stream come file (#8, passo 4 del piano).

`configs/mare-nostrum.yml` e' il master: tiene il `seed` e il piazzamento, e
importa ogni stream da `configs/streams/<id>.yml`, un documento del
laboratorio. Qui si pretende cio' che il piano promette del brano:

- **una chiave, una casa**: accanto a `file:` solo il piazzamento; nel file lo
  stream e la testa del documento da solo, e nessuna chiave di piazzamento;
- **identita'**: il nome del file e' lo `stream_id`, e il seed del file e'
  quello del master, quindi lo stream suona uguale nel brano e da solo;
- il master con i `file:` e' lo stesso brano del master con gli stream scritti
  dentro: stesso documento per il motore (sempre), stessi grani e stesso audio
  (marker `brano`, `make brano-tests`: rendono il brano due volte);
- ogni file si apre nel laboratorio gia' pulito, e il suo ascolto e' lo stream
  del brano a meno del piazzamento: stessi grani spostati dell'onset, e lo
  stesso audio dello stem (ancora `brano`).

Il lato di PGE-ui (il master si apre, una modifica a uno stream importato
finisce nel suo file) sta in PGE-ui, che legge questa cartella come workspace:
qui non c'e' il suo bridge. Vedi CLAUDE.md, "Il brano".
"""
import glob
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest
import soundfile as sf
import yaml

from granstudies import engine_bridge
from granstudies.graph import build_html, lab_completo
from granstudies.serve import _Dumper, _stesso, gia_su_disco

import brano_master as B

HARNESS = os.path.join(B.ROOT, "tests", "lab_dom.js")
SEED = 1441

engine = pytest.mark.skipif(not os.path.isdir(engine_bridge.ENGINE_SRC),
                            reason="serve il submodule engine")
node = pytest.mark.skipif(shutil.which("node") is None, reason="serve node")

MASTER = B.leggi(B.MASTER)
VOCI = MASTER["streams"]
FILES = [v["file"] for v in VOCI]


def _file(voce_o_file):
    f = voce_o_file["file"] if isinstance(voce_o_file, dict) else voce_o_file
    return B.leggi(os.path.join(B.CONFIGS, f))


# --- una chiave, una casa -----------------------------------------------------

def test_il_master_ha_il_seed_e_importa_ogni_stream():
    """Il seed e' quello deciso nella #2, lo stesso degli `study.yml`; ogni
    stream del brano e' un file (decisione della #8: tutti, non solo quelli da
    lavorare nel laboratorio), e nessun file e' nominato due volte."""
    assert MASTER["seed"] == SEED
    assert VOCI and all("file" in v for v in VOCI)
    assert len(set(FILES)) == len(FILES)


def test_accanto_a_file_c_e_solo_il_piazzamento():
    """Lo `stream_id` non c'e': e' il nome del file, e scriverlo uguale sarebbe
    una seconda casa per la stessa chiave. Un id diverso dal nome del file
    cambierebbe la realizzazione (#2), e va scelto, non ereditato."""
    for voce in VOCI:
        assert set(voce) - {"file"} <= set(B.PIAZZAMENTO), voce
        assert "onset" in voce, voce


def test_ogni_file_di_streams_e_importato_dal_master():
    """Un file in `configs/streams/` che il master non nomina non suona nel
    brano: e' uno stream perso, o un altro brano, e allora non sta qui."""
    su_disco = sorted(os.path.relpath(p, B.CONFIGS)
                      for p in glob.glob(os.path.join(B.CONFIGS, "streams", "*.yml")))
    assert su_disco == sorted(FILES)


@pytest.mark.parametrize("file", FILES)
def test_il_file_e_uno_stream_solo_con_la_sua_identita(file):
    """Il file si rende anche da solo, e da solo suona come nel brano: il suo
    `stream_id` e' il nome del file e il suo seed e' quello del master. Il
    piazzamento non c'e' — e' del master — e la durata in testa e' quella del
    render da solo, cioe' dello stream."""
    doc = _file(file)
    (st,) = doc["streams"]
    assert st["stream_id"] == B.id_del_file(file)
    assert doc["seed"] == MASTER["seed"]
    assert not set(st) & set(B.PIAZZAMENTO), st
    assert doc["duration"] == st["duration"]


# --- il master con i file e' il master scritto dentro --------------------------

def _motore(tmp_path):
    engine_bridge._ensure_engine_on_path()
    engine_bridge._silence_loggers(str(tmp_path / "logs"))


def _carica(path):
    from pge.engine.generator import Generator
    g = Generator(str(path))
    g.load_yaml()
    return g


@engine
def test_per_il_motore_il_master_e_il_master_scritto_dentro(tmp_path, capsys):
    """La verifica d'identita' sul documento: dopo `resolve_stream_files` il
    motore vede gli stessi stream, chiave per chiave, dello stesso master con
    gli stream scritti dentro, e la cache gli da' lo stesso fingerprint. Il
    seed del file e' quello del master, quindi nessun avviso `[SEED]`.

    E' il controllo che gira sempre: da qui in poi cache, solo/mute e grani
    lavorano sulla lista risolta, e nessuno sa che `file:` esiste. Grani e
    audio li confrontano i test `brano`.
    """
    _motore(tmp_path)
    from pge.rendering.stream_cache_manager import StreamCacheManager
    dentro = tmp_path / "mare-nostrum.yml"
    with open(dentro, "w", encoding="utf-8") as fh:
        yaml.safe_dump(B.brano(), fh, sort_keys=False)
    a, b = _carica(B.MASTER), _carica(dentro)
    assert a.data["seed"] == b.data["seed"] == SEED
    assert [s["stream_id"] for s in a.data["streams"]] == \
        [B.id_del_file(f) for f in FILES]
    m = StreamCacheManager(str(tmp_path / "manifest.json"), renderer_type="numpy")
    for sa, sb in zip(a.data["streams"], b.data["streams"]):
        assert sa == sb, sa["stream_id"]
        assert m.compute_fingerprint(sa) == m.compute_fingerprint(sb)
    assert sorted(a.stream_origins) == sorted(B.id_del_file(f) for f in FILES)
    assert "[SEED]" not in capsys.readouterr().err


# --- ogni file nel laboratorio -----------------------------------------------

_PAGINA = {}


def _pagina(tmp_path):
    """La pagina come la serve `make serve` (`cmd_graph`): finestre, limiti e
    default dell'engine, e fra i sample quelli del brano — servita, la
    cartella `samples/` li ha tutti."""
    if "html" not in _PAGINA:
        from granstudies import bounds
        from granstudies.__main__ import _finestre
        raw = B.leggi(os.path.join(B.ROOT, "studies", "001-41", "study.yml"))
        campioni = sorted({_file(f)["streams"][0]["sample"] for f in FILES})
        _PAGINA["html"] = build_html("001-41", lab_completo(
            raw, campioni, _finestre(), bounds.bounds_for,
            engine_bridge.parameter_path_defaults()))
    p = tmp_path / "graph.html"
    p.write_text(_PAGINA["html"])
    return p


def _lab(tmp_path, file, js):
    path = os.path.join(B.CONFIGS, file)
    scenario = tmp_path / "scenario.js"
    scenario.write_text("carica(%s, %s);\n" % (json.dumps(_file(file)), json.dumps(path)) + js)
    out = subprocess.run(["node", HARNESS, str(_pagina(tmp_path)), str(scenario)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@engine
@node
@pytest.mark.parametrize("file", FILES)
def test_ogni_file_si_apre_nel_laboratorio_gia_pulito(tmp_path, file):
    """Aperto nel laboratorio dal suo path, il file e' gia' il documento che la
    pagina scriverebbe: niente `• modificato`, nessun valore a schermo che il
    breakpoint non abbia, e un `rendi e ascolta` non lo riscrive
    (`gia_su_disco`, con i tipi), quindi la firma che PGE-ui ricorda resta
    buona. I file sono stati scritti cosi', dalla pagina; se il laboratorio
    cambia il modo di scrivere un documento, questo test lo dice."""
    got = _lab(tmp_path, file, "console.log(JSON.stringify({doc: labDoc(), sporco: sporco(),"
                               " cambiati: cambiati(), daPerdere: daPerdere()}));\n")
    assert _stesso(got["doc"], _file(file))
    assert gia_su_disco(os.path.join(B.CONFIGS, file), got["doc"])
    assert (got["sporco"], got["cambiati"], got["daPerdere"]) == (False, [], False)


def _ascolto(tmp_path, file):
    """Il documento che `rendi e ascolta` manda al server per l'ascolto."""
    got = _lab(tmp_path, file, """
const POST = [];
fetch = async (rotta, opt) => { POST.push(JSON.parse(opt.body));
  return {ok: true, json: async () => ({ok: false, error: 'fermo qui'})}; };
labRender().then(() => console.log(JSON.stringify(POST[0])));
""")
    return got["ascolto"]


@engine
@node
@pytest.mark.parametrize("file", FILES)
def test_l_ascolto_del_laboratorio_e_lo_stream_del_brano(tmp_path, file):
    """Cio' che il laboratorio rende, per il motore, e' lo stream del brano a
    meno del piazzamento: stesso `stream_id`, stesso seed, stesse chiavi; parte
    da 0 e non e' muto. E' la condizione perche' suoni come nel brano — l'RNG e'
    `(seed, stream_id, componente)` — e i test `brano` la ascoltano."""
    _motore(tmp_path)
    doc = _ascolto(tmp_path, file)
    solo = tmp_path / os.path.basename(file)
    with open(solo, "w", encoding="utf-8") as fh:
        yaml.dump(doc, fh, Dumper=_Dumper, sort_keys=False, allow_unicode=True)
    (st,) = _carica(solo).data["streams"]
    sid = B.id_del_file(file)
    nel_brano = next(s for s in _carica(B.MASTER).data["streams"] if s["stream_id"] == sid)
    assert doc["seed"] == MASTER["seed"]
    assert st["onset"] == 0 and "mute" not in st and "solo" not in st
    fuori = set(B.PIAZZAMENTO)
    assert {k: v for k, v in st.items() if k not in fuori} == \
        {k: v for k, v in nel_brano.items() if k not in fuori}


# --- grani e audio (marker `brano`: `make brano-tests`) -----------------------
#
# Rendono il brano intero: piu' di tre milioni di grani, minuti per ogni
# render. Con i sample veri in `samples/` si confronta il brano come suona;
# senza, con sample sintetici dai nomi giusti — l'identita' non dipende da
# cosa c'e' nei sample, purche' i due lati leggano gli stessi.

brano = pytest.mark.brano


@pytest.fixture(scope="module")
def campioni(tmp_path_factory):
    nomi = sorted({_file(f)["streams"][0]["sample"] for f in FILES})
    veri = os.path.join(B.ROOT, "samples")
    if all(os.path.isfile(os.path.join(veri, n)) for n in nomi):
        return veri
    d = tmp_path_factory.mktemp("samples")
    rng = np.random.default_rng(0)
    for n in nomi:
        sf.write(str(d / n), 0.3 * rng.standard_normal((48000 * 8, 2)), 48000)
    return str(d)


def _senza_piazzamento_muto(master):
    """Il master con ogni stream che suona: `mute` e `solo` decidono quali
    stream si rendono, non come suonano, e qui si vogliono sentire tutti."""
    return dict(master, streams=[{k: v for k, v in voce.items() if k not in ("mute", "solo")}
                                 for voce in master["streams"]])


@pytest.fixture(scope="module")
def due_master(tmp_path_factory):
    """Lo stesso brano due volte: coi `file:` (configs/ copiata) e scritto
    dentro. Stesso nome, quindi stessi nomi di stem."""
    radice = tmp_path_factory.mktemp("brano")
    con_file = radice / "con_file"
    shutil.copytree(B.CONFIGS, con_file)
    m = _senza_piazzamento_muto(MASTER)
    with open(con_file / "mare-nostrum.yml", "w", encoding="utf-8") as fh:
        yaml.safe_dump(m, fh, sort_keys=False)
    dentro = radice / "dentro"
    dentro.mkdir()
    with open(dentro / "mare-nostrum.yml", "w", encoding="utf-8") as fh:
        yaml.safe_dump(B.scritto_dentro(m, str(con_file)), fh, sort_keys=False)
    return {"con_file": con_file / "mare-nostrum.yml", "dentro": dentro / "mare-nostrum.yml"}


def _grani(path, samples, logs):
    """Per stream: l'onset, e i grani di ogni voce come colonne di numeri, con
    le tabelle tradotte nel loro nome — il numero di una tabella dipende da
    quali altri stream ci sono, il sample e la finestra no."""
    gen = engine_bridge.load_generator(str(path), samples_dir=samples, log_dir=str(logs))
    tab = gen.ftable_manager.get_all_tables()
    out = {}
    for s in gen.streams:
        voci = []
        for v in s.voices:
            num = np.array([[g.onset, g.duration, g.pointer_pos, g.pitch_ratio, g.volume, g.pan]
                            for g in v], dtype=float).reshape(-1, 6)
            nomi = [(tab[g.sample_table][1], tab[g.envelope_table][1]) for g in v]
            voci.append((num, nomi))
        out[s.stream_id] = (s.onset, voci)
    return out


@pytest.fixture(scope="module")
def grani_con_file(due_master, campioni, tmp_path_factory):
    return _grani(due_master["con_file"], campioni, tmp_path_factory.mktemp("logs"))


@engine
@brano
def test_il_master_con_i_file_genera_gli_stessi_grani(due_master, campioni, grani_con_file,
                                                      tmp_path):
    """Il criterio della #8: a parita' di seed e di id, i grani sono gli stessi,
    campo per campo, su ogni voce di ogni stream."""
    dentro = _grani(due_master["dentro"], campioni, tmp_path / "logs")
    assert sorted(dentro) == sorted(grani_con_file) == sorted(B.id_del_file(f) for f in FILES)
    for sid, (onset, voci) in grani_con_file.items():
        assert dentro[sid][0] == onset
        assert len(dentro[sid][1]) == len(voci) and voci, sid
        for (a, na), (b, nb) in zip(voci, dentro[sid][1]):
            assert len(a), sid
            assert np.array_equal(a, b) and na == nb, sid


def _rendi(yml, out, campioni, logs, per_stream):
    cmd = [sys.executable, os.path.join(B.ROOT, "engine", "src", "main.py"), str(yml), str(out),
           "--renderer", "numpy", "--samples-dir", campioni, "--log-dir", str(logs)]
    if per_stream:
        cmd += ["--per-stream", "--jobs", str(os.cpu_count() or 1)]
    p = subprocess.run(cmd, cwd=B.ROOT, capture_output=True, text=True)
    assert p.returncode == 0, (p.stdout + p.stderr)[-3000:]


@pytest.fixture(scope="module")
def stem_con_file(due_master, campioni, tmp_path_factory):
    d = tmp_path_factory.mktemp("stem_con_file")
    _rendi(due_master["con_file"], d / "brano.aif", campioni, d / "logs", per_stream=True)
    return d


@engine
@brano
def test_il_master_con_i_file_rende_lo_stesso_audio(due_master, campioni, stem_con_file,
                                                    tmp_path):
    """Lo stesso criterio sull'audio: uno stem per stream, e ogni stem e' lo
    stesso, campione per campione."""
    _rendi(due_master["dentro"], tmp_path / "brano.aif", campioni, tmp_path / "logs",
           per_stream=True)
    for f in FILES:
        nome = "brano__%s.aif" % B.id_del_file(f)
        a, sra = sf.read(str(stem_con_file / nome))
        b, srb = sf.read(str(tmp_path / nome))
        assert sra == srb and len(a) and np.array_equal(a, b), nome


def _solo(tmp_path, file):
    """Il file come lo rende `rendi e ascolta`: lo stream da 0, senza `mute`.
    Che il laboratorio mandi proprio questo lo dice
    `test_l_ascolto_del_laboratorio_e_lo_stream_del_brano`."""
    doc = _file(file)
    doc["streams"][0] = {**doc["streams"][0], "onset": 0}
    path = tmp_path / os.path.basename(file)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(doc, fh, Dumper=_Dumper, sort_keys=False, allow_unicode=True)
    return path


@engine
@brano
@pytest.mark.parametrize("file", FILES)
def test_ogni_file_da_solo_suona_come_nel_brano(file, campioni, grani_con_file, stem_con_file,
                                                tmp_path):
    """Reso da solo, il file da' i grani che ha nel brano, spostati del suo
    onset (a meno dell'arrotondamento della somma: l'onset di un grano e'
    `onset dello stream + tempo trascorso`), e lo stesso audio dello stem del
    brano, campione per campione."""
    sid = B.id_del_file(file)
    solo = _solo(tmp_path, file)
    (onset_solo, voci_solo), = _grani(solo, campioni, tmp_path / "logs").values()
    onset, voci = grani_con_file[sid]
    assert onset_solo == 0
    for (a, na), (b, nb) in zip(voci, voci_solo):
        assert a.shape == b.shape and len(a), sid
        assert np.array_equal(a[:, 1:], b[:, 1:]) and na == nb, sid
        assert np.allclose(a[:, 0] - onset, b[:, 0], rtol=0, atol=1e-9), sid
    _rendi(solo, tmp_path / "solo.aif", campioni, tmp_path / "logs", per_stream=False)
    a, _ = sf.read(str(stem_con_file / ("brano__%s.aif" % sid)))
    b, _ = sf.read(str(tmp_path / "solo.aif"))
    assert len(a) and np.array_equal(a, b), sid
