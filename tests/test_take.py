"""Modalita' take: risoluzione di TAKE e sicurezza degli hardlink.

Una take nasce come copia hardlink della precedente (``make take``): finche' un
file audio non viene rirenderizzato e' lo STESSO inode di quello gia' ascoltato.
L'engine scrive troncando in place, quindi senza lo sgancio dell'hardlink il
render riscriverebbe l'audio della take precedente. E' il punto in cui la
modalita' take smette di essere comoda e diventa perdita di dati: sta qui il
test, non nei target make.
"""
import os

import pytest
import yaml

from granstudies import __main__ as cli
from granstudies import render as render_mod
from granstudies.errors import SpecError
from granstudies.render import render_variants, write_variants
from granstudies.study_spec import parse_study_spec


def _spec():
    return parse_study_spec({
        "study_id": "s",
        "base": {"sample": "x.wav", "duration": 6, "time_mode": "normalized",
                 "grain": {"envelope": "hanning"}},
        "axes": {
            "density": {"path": "density", "baseline": 20, "values": [5, 50]},
            "grain_duration": {"path": "grain.duration", "baseline": 0.05,
                               "values": [0.01, 0.2]},
        },
        "sweep": {"mode": "envelope", "orders": [1, 2], "plateau": 5, "transition": 5},
    })


def _fake_engine(marker):
    """Engine finto che scrive ``marker``: come il vero, tronca in place."""
    def fake(yaml_path, output_path, samples_dir, output_sr=48000,
             per_stream=False, use_cache=False, cache_dir=None, jobs=1):
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w") as fh:
            fh.write(marker)
        return [output_path]
    return fake


# --- risoluzione di TAKE ---------------------------------------------------

def test_gen_dir_senza_take_resta_in_generated(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("TAKE", raising=False)
    assert cli.gen_dir("s1") == os.path.join(str(tmp_path), "generated", "s1")
    assert cli.take_label() is None


@pytest.mark.parametrize("valore", ["", "0", "false", "no", "off", "FALSE"])
def test_gen_dir_take_spento_esplicitamente_resta_in_generated(tmp_path, monkeypatch, valore):
    # `export TAKE=false` e' il modo naturale di spegnere la modalita' senza
    # unset: se finisse nel ramo "label di una take" darebbe un errore assurdo.
    monkeypatch.setattr(cli, "REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("TAKE", valore)
    assert cli.take_label() is None
    assert cli.gen_dir("s1") == os.path.join(str(tmp_path), "generated", "s1")


def test_gen_dir_risolve_latest_e_label_esplicita(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "REPO_ROOT", str(tmp_path))
    take = tmp_path / "takes" / "s1" / "2026-01-01_1200"
    take.mkdir(parents=True)
    os.symlink("2026-01-01_1200", tmp_path / "takes" / "s1" / "latest")

    # TAKE=1 passa da ``latest`` ma restituisce la take vera: i path che
    # finiscono nei log e negli .sv nominano la take, non l'alias mobile.
    monkeypatch.setenv("TAKE", "1")
    assert cli.gen_dir("s1") == os.path.realpath(take)
    # una label esplicita serve a tornare su una take vecchia
    monkeypatch.setenv("TAKE", "2026-01-01_1200")
    assert cli.gen_dir("s1") == os.path.realpath(take)


def test_gen_dir_take_inesistente_e_errore(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("TAKE", "mai-aperta")
    with pytest.raises(SpecError):
        cli.gen_dir("s1")


# --- sicurezza degli hardlink ----------------------------------------------

def test_render_non_tocca_laudio_hardlinkato_della_take_precedente(tmp_path, monkeypatch):
    variant_dir = str(tmp_path / "variants")
    write_variants(_spec(), variant_dir)
    audio_dir = tmp_path / "take1"
    kwargs = dict(variant_dir=variant_dir, audio_dir=str(audio_dir),
                  score_dir=None, samples_dir="unused", jobs=1)

    monkeypatch.setattr(render_mod.engine_bridge, "render", _fake_engine("take1"))
    manifest = render_variants(**kwargs)
    assert len(manifest) >= 2

    # `make take`: la take nuova hardlinka l'audio della precedente.
    take2 = tmp_path / "take2"
    for entry in manifest:
        dst = str(take2 / os.path.relpath(entry["audio"], audio_dir))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.link(entry["audio"], dst)
        assert os.stat(dst).st_nlink == 2

    # una sola variante cambia
    changed = manifest[0]
    now = os.path.getmtime(changed["yaml"]) + 10
    os.utime(changed["yaml"], (now, now))

    monkeypatch.setattr(render_mod.engine_bridge, "render", _fake_engine("take2"))
    render_variants(**dict(kwargs, audio_dir=str(take2)))

    rel = os.path.relpath(changed["audio"], audio_dir)
    with open(take2 / rel) as fh:
        assert fh.read() == "take2"
    # il file della take precedente e' rimasto quello ascoltato
    with open(audio_dir / rel) as fh:
        assert fh.read() == "take1"
    assert os.stat(take2 / rel).st_nlink == 1

    # le varianti immutate restano condivise: e' il risparmio di disco
    for entry in manifest[1:]:
        other = os.path.relpath(entry["audio"], audio_dir)
        assert os.stat(take2 / other).st_nlink == 2


# --- nomi dei .sv ----------------------------------------------------------

_DOC_SWEEP = {
    "study_id": "s_take",
    "seed": 7,
    "samples_dir": "samples",
    "base": {"onset": 0, "sample": "corpus.wav", "duration": 10,
             "time_mode": "normalized", "grain": {"envelope": "hanning"}},
    "axes": {"density": {"path": "density", "baseline": 20, "values": [5, 50]}},
    "sweep": {"mode": "envelope", "orders": [1], "plateau": 5, "transition": 5},
}


def test_sv_di_take_diverse_hanno_nomi_diversi(tmp_path, monkeypatch):
    """Sonic Visualiser identifica la sessione dal nome file: due take dello
    stesso studio devono produrre .sv distinguibili, altrimenti la seconda non
    si apre mentre la prima e' aperta — e il confronto fra take e' il motivo
    per cui esistono."""
    import granstudies.render as render_mod
    import granstudies.sv_export as sv_export

    monkeypatch.setattr(cli, "REPO_ROOT", str(tmp_path))
    sdir = tmp_path / "studies" / "s_take"
    sdir.mkdir(parents=True)
    (sdir / "study.yml").write_text(yaml.safe_dump(_DOC_SWEEP, sort_keys=False))

    def fake_render(yaml_path, output_path, samples_dir, output_sr=48000,
                    per_stream=False, use_cache=False, cache_dir=None, jobs=1):
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w") as fh:
            fh.write("x")
        return [output_path]

    monkeypatch.setattr(render_mod.engine_bridge, "render", fake_render)
    esportati = []
    monkeypatch.setattr(
        sv_export, "variant_to_sv",
        lambda variant, audio, out, layout, markers, markers_scope: esportati.append(out),
    )

    for label in ("2026-01-01_1200", "2026-01-01_1400"):
        (tmp_path / "takes" / "s_take" / label).mkdir(parents=True)
        monkeypatch.setenv("TAKE", label)
        assert cli.cmd_sweep("s_take") == 0
        assert cli.cmd_render("s_take", no_score=True) == 0
        assert cli.cmd_sv("s_take", layout="multi") == 0

    nomi = [os.path.basename(p) for p in esportati]
    assert len(nomi) == 2, nomi          # una variante per take: il test non gira a vuoto
    assert len(nomi) == len(set(nomi)), nomi
    assert all("2026-01-01_1200" in n or "2026-01-01_1400" in n for n in nomi)


def test_sv_senza_take_non_prende_suffisso(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("TAKE", raising=False)
    assert cli.sv_take_suffix(os.path.join(str(tmp_path), "generated", "s1")) == ""
