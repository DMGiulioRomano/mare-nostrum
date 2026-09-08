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
