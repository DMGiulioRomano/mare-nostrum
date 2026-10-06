"""Lo stream come file, dal lato di chi lo rende (#7, passo 2 del piano).

Il motore del submodule risolve `- file: <path>` negli stream di un master
(DMGiulioRomano/PythonGranularEngine#290). Le sue regole hanno i test la'; qui
si prova la cucitura con questo repo, cioe' la promessa del piano
(`docs/plans/stream-come-file.md`): un documento **scritto dal laboratorio**,
importato da un master, suona come lo stesso stream scritto dentro il master.

La fixture e' `tests/fixtures/stream_come_file/`: `master.yml` importa
`streams/risacca.yml`, che non e' scritto a mano ma e' l'uscita della pagina
(`labDoc`, scritta come la scrive `render_doc`). Il documento porta quello
che il laboratorio ci mette davvero: il `seed` dello `study.yml`, lo
`stream_id` uguale al nome del file (#5), e il piazzamento dello stream da cui
e' stato aperto (`onset: 12.5`, `mute: true`), che nel brano non conta —
decide il master.
"""
import json
import os
import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf
import yaml

from granstudies import engine_bridge
from granstudies.graph import build_html, lab_completo

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "stream_come_file")
DOCUMENTO = os.path.join("streams", "risacca.yml")
HARNESS = os.path.join(ROOT, "tests", "lab_dom.js")

engine = pytest.mark.skipif(not os.path.isdir(engine_bridge.ENGINE_SRC),
                            reason="serve il submodule engine")
node = pytest.mark.skipif(shutil.which("node") is None, reason="serve node")

# Le chiavi che il master tiene per se' accanto a `file:` (regola 4 della
# #290); lo `stream_id` a parte, perche' ha un default.
PIAZZAMENTO = ("onset", "mute", "solo")


def _leggi(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _scritto_dentro(master, cartella):
    """Lo stesso master, con ogni stream importato scritto dentro.

    E' la promessa del piano messa per esteso. Dal file viene lo stream; dal
    master il piazzamento e lo `stream_id`, che di default e' il nome del file
    senza estensione. Il resto del file non arriva: ne' la sua testa (`seed`,
    `duration`, `bpm`) ne' il piazzamento scritto dentro il suo stream.
    """
    streams = []
    for voce in master["streams"]:
        if "file" not in voce:
            streams.append(voce)
            continue
        (st,) = _leggi(os.path.join(cartella, voce["file"]))["streams"]
        sid = voce.get("stream_id",
                       os.path.splitext(os.path.basename(voce["file"]))[0])
        st = {"stream_id": sid,
              **{k: v for k, v in st.items()
                 if k not in PIAZZAMENTO and k != "stream_id"}}
        st.update({k: voce[k] for k in PIAZZAMENTO if k in voce})
        streams.append(st)
    return dict(master, streams=streams)


@pytest.fixture
def cartella(tmp_path):
    """La fixture copiata in una cartella sua, col sample che nomina."""
    dst = tmp_path / "brano"
    shutil.copytree(FIXTURE, dst)
    samples = tmp_path / "samples"
    samples.mkdir()
    sr = 44100
    t = np.arange(2 * sr) / sr
    sf.write(str(samples / "onda.wav"), 0.5 * np.sin(2 * np.pi * 220 * t), sr)
    return dst, samples


def _grani(path, samples, logs):
    """Ogni grano di ogni voce, per stream: i dataclass congelati del motore,
    confrontati campo per campo (onset, durata, pointer, pitch, volume, pan,
    tabelle)."""
    gen = engine_bridge.load_generator(str(path), samples_dir=str(samples),
                                       log_dir=str(logs))
    return {s.stream_id: [list(v) for v in s.voices] for s in gen.streams}


@engine
def test_importato_e_scritto_dentro_danno_gli_stessi_grani(cartella, tmp_path, capsys):
    """Il criterio della #7: a seed fisso, il master con `file:` genera gli
    stessi grani dello stesso master con lo stream scritto dentro.

    L'uguaglianza tiene insieme tre cose che il documento del laboratorio
    mette alla prova: l'`onset` 12.5 scritto nel file non sposta lo stream
    (lo mette il master, a 2.5), il suo `mute` non lo zittisce, e il suo
    `seed`, uguale a quello del master, non fa scattare l'avviso.
    """
    dst, samples = cartella
    master = _leggi(dst / "master.yml")
    dentro = dst / "master_dentro.yml"
    with open(dentro, "w", encoding="utf-8") as fh:
        yaml.safe_dump(_scritto_dentro(master, str(dst)), fh, sort_keys=False)

    importato = _grani(dst / "master.yml", samples, tmp_path / "logs")
    scritto = _grani(dentro, samples, tmp_path / "logs")

    assert sorted(importato) == ["risacca", "riva"]
    assert importato == scritto
    for sid, voci in importato.items():
        assert voci and all(voci), sid               # nessuna voce muta
    assert min(g.onset for v in importato["risacca"] for g in v) >= 2.5
    assert "[SEED]" not in capsys.readouterr().err


@engine
def test_la_fixture_importa_davvero(cartella, tmp_path):
    """La controprova: senza `file:` risolto il confronto qui sopra non
    direbbe niente. Il master della fixture importa lo stream, e un seed
    diverso da' un'altra realizzazione — quindi l'uguaglianza non e' quella
    di due documenti che il seed non tocca."""
    dst, samples = cartella
    master = _leggi(dst / "master.yml")
    assert [v.get("file") for v in master["streams"]] == [DOCUMENTO, None]
    altro = dst / "master_altro_seed.yml"
    with open(altro, "w", encoding="utf-8") as fh:
        yaml.safe_dump(dict(master, seed=7), fh, sort_keys=False)
    a = _grani(dst / "master.yml", samples, tmp_path / "logs")["risacca"]
    b = _grani(altro, samples, tmp_path / "logs")["risacca"]
    assert a != b


@node
def test_la_fixture_e_un_documento_del_laboratorio(tmp_path):
    """`streams/risacca.yml` e' il documento come lo scrive il laboratorio.

    Aperto nella pagina col suo nome e riscritto senza toccare niente, torna
    identico, e la pagina lo da' per salvato: l'identita' (lo `stream_id` del
    nome del file, il `seed` dello `study.yml` servito) e' gia' quella che il
    laboratorio scriverebbe. Se il laboratorio cambia il modo di scrivere un
    documento, la fixture va riscritta da lui, non a mano.
    """
    with open(os.path.join(ROOT, "studies", "001-41", "study.yml")) as fh:
        raw = yaml.safe_load(fh)
    predefiniti = {}
    if os.path.isdir(engine_bridge.ENGINE_SRC):
        predefiniti = engine_bridge.parameter_path_defaults()
    pagina = tmp_path / "graph.html"
    pagina.write_text(build_html("001-41", lab_completo(
        raw, ["onda.wav"], {}, lambda _p: None, predefiniti)))
    doc = _leggi(os.path.join(FIXTURE, DOCUMENTO))
    scenario = tmp_path / "scenario.js"
    scenario.write_text(
        "carica(%s, '/brano/risacca.yml');\n" % json.dumps(doc)
        + "console.log(JSON.stringify({doc: labDoc(), sporco: sporco()}));\n")
    out = subprocess.run(["node", HARNESS, str(pagina), str(scenario)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got["doc"] == doc
    assert got["sporco"] is False
