"""Compensazione di guadagno fra stream che leggono punti diversi del buffer."""
import os

import numpy as np
import pytest
import soundfile as sf
import yaml

from granstudies import gainmap


SR = 48000


@pytest.fixture
def buffer_dir(tmp_path):
    """Un sample in due meta': la prima forte, la seconda 20 dB sotto."""
    x = np.concatenate([np.full(SR // 2, 0.8), np.full(SR // 2, 0.08)])
    sf.write(tmp_path / "t.wav", x, SR)
    return str(tmp_path)


def stream(start, *, onset=0.0, duration=10.0, volume=0.0, **kw):
    s = {
        "sample": "t.wav",
        "onset": onset,
        "duration": duration,
        "volume": volume,
        "time_mode": "normalized",
        "pointer": {"start": start, "loop_unit": "absolute"},
        "grain": {"duration": 50, "duration_unit": "samples"},
    }
    s.update(kw)
    return s


# --- 1. stream contemporanei: la differenza si chiude, in sottrazione -------------

def test_contemporanei_chiudono_la_differenza(buffer_dir):
    forte, debole = stream(0.1), stream(0.6)
    gainmap.compensate([forte, debole], samples_dir=buffer_dir, alpha=1.0)
    assert debole["volume"] - forte["volume"] == pytest.approx(20.0, abs=0.5)


def test_correzione_solo_in_sottrazione(buffer_dir):
    """Il bound engine di volume e' +12 dB e la base tipica e' 0: si abbassano
    i forti, non si alzano i deboli."""
    forte, debole = stream(0.1), stream(0.6)
    gainmap.compensate([forte, debole], samples_dir=buffer_dir, alpha=1.0)
    assert max(forte["volume"], debole["volume"]) == 0.0
    assert forte["volume"] < 0.0


def test_alpha_dosa_la_correzione(buffer_dir):
    forte, debole = stream(0.1), stream(0.6)
    gainmap.compensate([forte, debole], samples_dir=buffer_dir, alpha=0.5)
    assert debole["volume"] - forte["volume"] == pytest.approx(10.0, abs=0.5)


def test_alpha_zero_non_tocca_niente(buffer_dir):
    forte, debole = stream(0.1), stream(0.6)
    gainmap.compensate([forte, debole], samples_dir=buffer_dir, alpha=0.0)
    assert forte["volume"] == debole["volume"] == 0.0


def test_volume_di_partenza_conservato_come_offset(buffer_dir):
    """La compensazione somma un offset, non riscrive il volume dichiarato."""
    forte, debole = stream(0.1, volume=-6.0), stream(0.6, volume=-6.0)
    gainmap.compensate([forte, debole], samples_dir=buffer_dir, alpha=1.0)
    assert max(forte["volume"], debole["volume"]) == -6.0


# --- 2. stream non contemporanei: nessuna normalizzazione reciproca ---------------

def test_versioni_concatenate_non_si_normalizzano_a_vicenda(buffer_dir):
    """Il caso normale di ``versions``: le versioni si susseguono, quindi non
    si mascherano — pareggiarle cancellerebbe una differenza che e' reale."""
    prima, dopo = stream(0.1, onset=0.0), stream(0.6, onset=100.0)
    gainmap.compensate([prima, dopo], samples_dir=buffer_dir, alpha=1.0)
    assert prima["volume"] == dopo["volume"] == 0.0


def test_sovrapposizione_parziale_conta_come_contemporaneita(buffer_dir):
    forte = stream(0.1, onset=0.0, duration=10.0)
    debole = stream(0.6, onset=9.0, duration=10.0)
    gainmap.compensate([forte, debole], samples_dir=buffer_dir, alpha=1.0)
    assert debole["volume"] - forte["volume"] == pytest.approx(20.0, abs=0.5)


def test_gruppi_disgiunti_condividono_un_solo_shift(buffer_dir):
    """Due coppie contemporanee al loro interno ma separate nel tempo: ognuna
    si pareggia da se', e la traslazione in sottrazione e' unica — altrimenti
    i due gruppi non sarebbero piu' confrontabili all'ascolto."""
    a, b = stream(0.1, onset=0.0), stream(0.6, onset=0.0)
    c, d = stream(0.1, onset=100.0), stream(0.6, onset=100.0)
    gainmap.compensate([a, b, c, d], samples_dir=buffer_dir, alpha=1.0)
    assert a["volume"] == c["volume"]
    assert b["volume"] == d["volume"]
    assert max(s["volume"] for s in (a, b, c, d)) == 0.0


# --- 3. silenzio: non si compensa e non trascina la media -------------------------

def test_stream_su_silenzio_non_viene_corretto(tmp_path):
    x = np.concatenate([np.full(SR // 2, 0.8), np.zeros(SR // 2)])
    sf.write(tmp_path / "t.wav", x, SR)
    suona, muto = stream(0.1), stream(0.6)
    gainmap.compensate([suona, muto], samples_dir=str(tmp_path), alpha=1.0)
    assert muto["volume"] == 0.0


def test_silenzio_non_abbassa_il_riferimento_degli_altri(tmp_path):
    """Un cugino muto non deve far salire il gruppo in cui si trova.

    Serve un secondo gruppo di confronto: dentro un gruppo solo, un
    riferimento sbagliato sposta tutti gli offset della stessa costante e la
    traslazione finale lo cancellerebbe, nascondendo l'errore.
    """
    x = np.concatenate([
        np.full(SR // 3, 0.8), np.full(SR // 3, 0.08), np.zeros(SR - 2 * (SR // 3))
    ])
    sf.write(tmp_path / "t.wav", x, SR)
    # Gruppo 1: forte + debole + un muto. Gruppo 2 (piu' avanti): solo forte + debole.
    a, b, muto = stream(0.1), stream(0.5), stream(0.9)
    c, d = stream(0.1, onset=100.0), stream(0.5, onset=100.0)
    gainmap.compensate([a, b, muto, c, d], samples_dir=str(tmp_path), alpha=1.0)
    assert (a["volume"], b["volume"]) == (c["volume"], d["volume"])


# --- 4. max_shift ----------------------------------------------------------------

def test_max_shift_limita_la_correzione(buffer_dir):
    forte, debole = stream(0.1), stream(0.6)
    gainmap.compensate([forte, debole], samples_dir=buffer_dir, alpha=1.0, max_shift=6.0)
    assert debole["volume"] - forte["volume"] == pytest.approx(12.0, abs=0.5)


# --- 5. integrazione: il documento stack scritto su disco ------------------------

def _stack_study(gain=None):
    """Studio a due stream che leggono punti diversi dello stesso buffer."""
    data = {
        "study_id": "g",
        "base": {
            "sample": "t.wav",
            "volume": 0.0,
            "duration": 10,
            "time_mode": "normalized",
            "grain": {"envelope": "hanning", "duration_unit": "samples"},
            "pointer": {"loop_unit": "absolute", "speed_ratio": 0},
        },
        "axes": {
            "density": {"baseline": 10, "base": 10},
            "grain.duration": {"baseline": 50, "base": 50},
        },
        "stack": {"density": {"base": 1}, "grain.duration": {"base": 1}},
        "streams": {
            "forte": {"base": {"pointer": {"start": 0.1}}},
            "debole": {"base": {"pointer": {"start": 0.6}}},
        },
    }
    if gain is not None:
        data["gain_compensation"] = gain
    return data


def _volumes(doc):
    return [s["volume"] for s in doc["streams"]]


def test_write_stack_compensa_col_blocco(buffer_dir, tmp_path):
    from granstudies.render import write_stack
    from granstudies.study_spec import resolve_streams

    specs = resolve_streams(_stack_study({"alpha": 1.0}))
    (path,) = write_stack(specs, str(tmp_path), samples_dir=buffer_dir)
    with open(path, encoding="utf-8") as fh:
        vols = _volumes(yaml.safe_load(fh))
    assert max(vols) == 0.0
    assert max(vols) - min(vols) == pytest.approx(20.0, abs=0.5)


def test_write_stack_senza_blocco_non_tocca_i_volumi(buffer_dir, tmp_path):
    """Non-regressione: le scale gia' curate non devono cambiare di un dB."""
    from granstudies.render import write_stack
    from granstudies.study_spec import resolve_streams

    specs = resolve_streams(_stack_study())
    (path,) = write_stack(specs, str(tmp_path), samples_dir=buffer_dir)
    with open(path, encoding="utf-8") as fh:
        assert _volumes(yaml.safe_load(fh)) == [0.0, 0.0]


# --- 6. integrazione: versions, uno shift solo per tutti i gruppi -----------------

@pytest.fixture
def buffer_3_zone(tmp_path):
    """Tre zone a 0, -10 e -20 dB (punti di lettura 0.1, 0.5, 0.8)."""
    n = SR // 3
    x = np.concatenate([
        np.full(n, 0.8), np.full(n, 0.253), np.full(SR - 2 * n, 0.08)
    ])
    sf.write(tmp_path / "t.wav", x, SR)
    return str(tmp_path)


def _versions_study():
    """Due versioni concatenate con escursione interna diversa: la prima legge
    0.1 e 0.8 (20 dB di distanza), la seconda 0.1 e 0.5 (10 dB)."""
    data = _stack_study({"alpha": 1.0})
    data["streams"]["debole"]["base"]["pointer"]["start"] = {
        "expr": "p", "let": {"p": 0.8}
    }
    data["versions"] = {"duration": 10, "p": {"values": [0.8, 0.5]}}
    return data


def test_write_versions_un_solo_shift_per_tutti_i_gruppi(buffer_3_zone, tmp_path):
    """Compensando dopo lo split ogni file avrebbe il proprio massimo a 0 e i
    gruppi non sarebbero piu' confrontabili fra loro all'ascolto."""
    from granstudies.render import write_versions

    written = write_versions(
        _versions_study(), "g", str(tmp_path), samples_dir=buffer_3_zone
    )
    docs = []
    for path in sorted(written):
        with open(path, encoding="utf-8") as fh:
            docs.append(_volumes(yaml.safe_load(fh)))
    assert len(docs) == 2
    larga, stretta = sorted(docs, key=lambda v: max(v) - min(v), reverse=True)
    # Ogni versione si pareggia da se': 20 dB una, 10 dB l'altra.
    assert max(larga) - min(larga) == pytest.approx(20.0, abs=0.5)
    assert max(stretta) - min(stretta) == pytest.approx(10.0, abs=0.5)
    # Un solo massimo a 0 su tutto il prodotto cartesiano, non uno per file.
    assert max(larga) == 0.0
    assert max(stretta) < -1.0


# --- 7. la CLI: `study stack` applica davvero la compensazione -------------------

def test_cmd_stack_applica_la_compensazione(tmp_path, monkeypatch, buffer_dir):
    """Il percorso vero (`make stack`): senza questo cablaggio la feature
    esiste solo nei test."""
    from granstudies import __main__ as cli

    doc = _stack_study({"alpha": 1.0})
    doc["samples_dir"] = buffer_dir
    sdir = tmp_path / "studies" / doc["study_id"]
    sdir.mkdir(parents=True)
    (sdir / "study.yml").write_text(yaml.safe_dump(doc, sort_keys=False))
    monkeypatch.setattr(
        cli, "study_dir", lambda s: os.path.join(str(tmp_path), "studies", s)
    )
    monkeypatch.setattr(
        cli, "gen_dir", lambda s: os.path.join(str(tmp_path), "generated", s)
    )

    assert cli.cmd_stack(doc["study_id"]) == 0
    out = os.path.join(
        str(tmp_path), "generated", doc["study_id"], "yaml", "stack", "stack.yml"
    )
    with open(out, encoding="utf-8") as fh:
        vols = _volumes(yaml.safe_load(fh))
    assert max(vols) - min(vols) == pytest.approx(20.0, abs=0.5)


def test_cmd_percorso_applica_la_compensazione(tmp_path, monkeypatch, buffer_dir):
    """Il percorso vero (`make percorso`): il cablaggio di issue #36 fa passare
    `samples_dir` fino a `gainmap.compensate` anche sul quarto processo."""
    from granstudies import __main__ as cli

    doc = _stack_study({"alpha": 1.0})
    doc["samples_dir"] = buffer_dir
    doc["percorso"] = {
        "onset": {"values": [0, 3, 6]},
        "duration": {"base": 10, "unit": "s"},
    }
    sdir = tmp_path / "studies" / doc["study_id"]
    sdir.mkdir(parents=True)
    (sdir / "study.yml").write_text(yaml.safe_dump(doc, sort_keys=False))
    monkeypatch.setattr(
        cli, "study_dir", lambda s: os.path.join(str(tmp_path), "studies", s)
    )
    monkeypatch.setattr(
        cli, "gen_dir", lambda s: os.path.join(str(tmp_path), "generated", s)
    )

    assert cli.cmd_percorso(doc["study_id"]) == 0
    out = os.path.join(
        str(tmp_path), "generated", doc["study_id"], "yaml", "percorso",
        "percorso.yml",
    )
    with open(out, encoding="utf-8") as fh:
        vols = _volumes(yaml.safe_load(fh))
    assert max(vols) == 0.0
    assert max(vols) - min(vols) == pytest.approx(20.0, abs=0.5)


def test_senza_samples_dir_nessuna_compensazione_e_nessun_errore(tmp_path):
    """Il sample non e' raggiungibile: si scrive il documento com'era, in
    silenzio — un documento senza audio non e' un errore di sintassi."""
    from granstudies.render import write_stack
    from granstudies.study_spec import resolve_streams

    specs = resolve_streams(_stack_study({"alpha": 1.0}))
    (path,) = write_stack(specs, str(tmp_path), samples_dir=None)
    with open(path, encoding="utf-8") as fh:
        assert _volumes(yaml.safe_load(fh)) == [0.0, 0.0]


# --- 8. parse_config: errori leggibili -------------------------------------------

def test_parse_config_assente_e_none():
    assert gainmap.parse_config({"study_id": "x"}) is None


def test_parse_config_default():
    assert gainmap.parse_config({"gain_compensation": {}})["alpha"] == 1.0


@pytest.mark.parametrize("raw, atteso", [
    (0.7, "non un valore secco"),
    ({"alpha": 1.5}, "fra 0 e 1"),
    ({"alpha": -0.1}, "fra 0 e 1"),
    ({"max_shift": 0}, "> 0 dB"),
    ({"alfa": 0.7}, "chiavi sconosciute"),
    # issue #37: un nodo-expr in alpha/max_shift esce come errore leggibile,
    # non come TypeError grezzo da float(dict).
    ({"alpha": {"expr": "0.7"}}, "deve essere un numero"),
    ({"max_shift": {"expr": "12"}}, "deve essere un numero"),
])
def test_parse_config_errori(raw, atteso):
    with pytest.raises(ValueError, match=atteso):
        gainmap.parse_config({"gain_compensation": raw})


# --- 9. unita' e envelope --------------------------------------------------------

def test_grain_duration_in_secondi(buffer_dir):
    grain = {"duration": 50 / SR, "duration_unit": "seconds"}
    forte, debole = stream(0.1, grain=grain), stream(0.6, grain=grain)
    gainmap.compensate([forte, debole], samples_dir=buffer_dir, alpha=1.0)
    assert debole["volume"] - forte["volume"] == pytest.approx(20.0, abs=0.5)


def test_grain_duration_in_millisecondi(buffer_dir):
    """``milliseconds`` misura la stessa finestra dei secondi equivalenti."""
    grain = {"duration": 50 / SR * 1000, "duration_unit": "milliseconds"}
    forte, debole = stream(0.1, grain=grain), stream(0.6, grain=grain)
    gainmap.compensate([forte, debole], samples_dir=buffer_dir, alpha=1.0)
    assert debole["volume"] - forte["volume"] == pytest.approx(20.0, abs=0.5)


def test_pointer_start_normalized(buffer_dir):
    """Senza ``loop_unit`` lo start ricade su ``time_mode``, come nell'engine:
    normalized = frazione della durata del sample."""
    forte = stream(0.1, pointer={"start": 0.1})       # 0.1 * 1 s
    debole = stream(0.6, pointer={"start": 0.6})
    gainmap.compensate([forte, debole], samples_dir=buffer_dir, alpha=1.0)
    assert debole["volume"] - forte["volume"] == pytest.approx(20.0, abs=0.5)


def test_grain_duration_envelope_usa_la_mediana(buffer_dir):
    """Una costante per documento (mediana dei breakpoint) invece di inseguire
    l'envelope: inseguirlo produrrebbe un tremolo alla velocita' della
    camminata, non una correzione."""
    env = {"type": "linear", "points": [[0.0, 10], [0.5, 50], [1.0, 90]],
           "time_mode": "normalized"}
    forte = stream(0.1, grain={"duration": env, "duration_unit": "samples"})
    debole = stream(0.6, grain={"duration": env, "duration_unit": "samples"})
    gainmap.compensate([forte, debole], samples_dir=buffer_dir, alpha=1.0)
    assert debole["volume"] - forte["volume"] == pytest.approx(20.0, abs=0.5)


def test_volume_envelope_riceve_offset_su_tutti_i_breakpoint(buffer_dir):
    env = {"type": "linear", "points": [[0.0, 0.0], [1.0, -6.0]],
           "time_mode": "normalized"}
    forte = stream(0.1, volume=dict(env, points=[list(p) for p in env["points"]]))
    debole = stream(0.6)
    gainmap.compensate([forte, debole], samples_dir=buffer_dir, alpha=1.0)
    ys = [y for _, y in forte["volume"]["points"]]
    assert ys[0] - ys[1] == pytest.approx(6.0)      # la forma resta
    assert ys[0] == pytest.approx(-20.0, abs=0.5)   # traslata in blocco
