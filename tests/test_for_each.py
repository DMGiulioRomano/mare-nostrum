"""``for_each:`` — l'asse esterno: una combinazione, un render intero.

Il blocco moltiplica i file invece dei gradini: ogni combinazione e' una patch
sullo ``study.yml`` e ha la sua cartella sotto ``generated/<study>/``. Qui
stanno il parse (prodotto cartesiano, etichette, guardie) e il giro completo
della CLI, che e' il punto in cui si vede se le combinazioni restano davvero
separate — cartelle, snapshot e nomi dei ``.sv``.
"""
import os

import pytest
import yaml

from granstudies import __main__ as cli
from granstudies import for_each
from granstudies.errors import SpecError


def _combos(block):
    return for_each.parse({"base": {"volume": 0}, "for_each": block})


# --- parse: forme e prodotto cartesiano ------------------------------------

def test_senza_blocco_una_sola_combinazione_vuota():
    # Il caso degenere non e' un ramo speciale: chi itera trova sempre almeno
    # una combinazione, e uno studio senza assi esterni resta com'era.
    assert for_each.parse({"base": {}}) == [for_each.EMPTY]
    assert for_each.parse(None) == [for_each.EMPTY]


def test_manopola_singola_la_chiave_e_il_path():
    combos = _combos({"base.distribution": {"values": [0, 0.5, 1]}})
    assert [c.label for c in combos] == ["distribution=0", "distribution=0.5", "distribution=1"]
    assert combos[1].overrides == {"base.distribution": 0.5}


def test_lista_nuda_e_generatore_sono_la_stessa_cosa():
    assert [c.label for c in _combos({"base.volume": [6, 12]})] == \
           [c.label for c in _combos({"base.volume": {"values": [6, 12]}})]
    # e il vocabolario dei generatori vale tutto: ramp compreso
    assert [c.label for c in _combos({"base.volume": {"ramp": {"start": 0, "stop": 12, "step": 6}}})] == \
           ["volume=0", "volume=6", "volume=12"]


def test_etichetta_toglie_sezione_e_generatore():
    # `base.` e `axes.`, e il nome del generatore in coda, nel nome di una
    # cartella sono rumore: la chiave e' cio' che si muove.
    assert _combos({"base.grain.duration": [0.01]})[0].label == "grain.duration=0.01"
    assert _combos({"axes.fill_factor.values": [1]})[0].label == "fill_factor=1"
    assert _combos({"stack.seed": [7]})[0].label == "stack.seed=7"


def test_stati_nominati_per_gli_override_non_scalari():
    combos = _combos({"griglia": {
        "fitta": {"axes.fill_factor.values": [0.5, 1, 2, 4]},
        "rada": {"axes.fill_factor.values": [0.5, 4]},
    }})
    assert [c.label for c in combos] == ["griglia=fitta", "griglia=rada"]
    assert combos[1].overrides == {"axes.fill_factor.values": [0.5, 4]}


def test_bundle_vuoto_e_lo_stato_che_non_tocca_niente():
    combos = _combos({"v": {"originale": {}, "mossa": {"base.volume": 3}}})
    assert [c.label for c in combos] == ["v=originale", "v=mossa"]
    assert combos[0].overrides == {}


def test_prodotto_cartesiano_lessicografico():
    # Primo asse dichiarato = piu' esterno (varia piu' lentamente), come negli
    # orderings dello sweep e negli assi di versions.
    combos = _combos({
        "base.distribution": [0, 1],
        "griglia": {"fitta": {"base.volume": 1}, "rada": {"base.volume": 2}},
    })
    assert [c.label for c in combos] == [
        "distribution=0__griglia=fitta", "distribution=0__griglia=rada",
        "distribution=1__griglia=fitta", "distribution=1__griglia=rada",
    ]
    assert combos[2].overrides == {"base.distribution": 1, "base.volume": 1}


# --- parse: le guardie -----------------------------------------------------

def test_valore_non_scalare_manda_agli_stati_nominati():
    # Una lista non puo' diventare un nome di cartella, e un indice anonimo
    # (d0/ d1/) e' il difetto che le take avevano: il nome lo da' l'utente.
    with pytest.raises(SpecError) as e:
        _combos({"axes.fill_factor.values": {"values": [[1, 2], [3, 4]]}})
    assert "stati nominati" in str(e.value)


def test_stato_non_dict_e_errore():
    with pytest.raises(SpecError) as e:
        _combos({"griglia": {"rada": 0.5}})
    assert "bundle di override" in str(e.value)


def test_stato_che_si_chiama_come_un_generatore_e_errore():
    # `base`/`values`/`ramp` come nome di stato farebbero leggere l'asse come
    # manopola singola: l'errore vero sarebbe arrivato molto piu' in la'.
    with pytest.raises(SpecError) as e:
        _combos({"griglia": {"base": {"base.volume": 1}, "rada": {"base.volume": 2}}})
    assert "nessuno stato puo' chiamarsi" in str(e.value)


def test_etichette_gemelle_sono_errore():
    with pytest.raises(SpecError) as e:
        _combos({"base.distribution": [0], "axes.distribution.values": [1]})
    assert "stessa etichetta" in str(e.value)


def test_due_assi_sullo_stesso_path_sono_errore():
    # Il valore finale dipenderebbe dall'ordine di dichiarazione, che qui non
    # e' una precedenza dichiarata.
    with pytest.raises(SpecError) as e:
        _combos({"a": {"x": {"base.volume": 1}}, "b": {"y": {"base.volume": 2}}})
    assert "toccano" in str(e.value)


def test_blocco_vuoto_o_malformato_e_errore():
    for block in ({}, [], "distribution"):
        with pytest.raises(SpecError):
            for_each.parse({"for_each": block})


# --- apply: la patch -------------------------------------------------------

def test_apply_assegna_il_path_e_toglie_il_blocco():
    doc = {"base": {"volume": 0, "grain": {"envelope": "hanning"}},
           "for_each": {"base.volume": [6]}}
    out = for_each.apply(doc, _combos({"base.volume": [6]})[0])
    assert out == {"base": {"volume": 6, "grain": {"envelope": "hanning"}}}
    assert doc["base"]["volume"] == 0          # l'originale non si tocca
    assert "for_each" in doc


def test_apply_crea_una_chiave_nuova_ma_non_una_sezione():
    doc = {"base": {"volume": 0}}
    out = for_each.apply(doc, for_each.Combo("x", (("base.pan_range", 360),)))
    assert out["base"]["pan_range"] == 360
    # `bse.pan_range` sarebbe un refuso che passa in silenzio senza muovere nulla
    with pytest.raises(SpecError) as e:
        for_each.apply(doc, for_each.Combo("x", (("bse.pan_range", 360),)))
    assert "non esiste nel documento" in str(e.value)


def test_apply_di_combinazione_vuota_toglie_comunque_il_blocco():
    # Da qui in giu' il documento e' uno studio normale: nessun parser deve
    # conoscere l'esistenza degli assi esterni.
    assert for_each.apply({"base": {}, "for_each": {"base.volume": [6]}},
                          for_each.EMPTY) == {"base": {}}


# --- CLI: dove si scrive ---------------------------------------------------

_DOC = {
    "study_id": "s_fe",
    "seed": 7,
    "samples_dir": "samples",
    "base": {"onset": 0, "sample": "corpus.wav", "duration": 10, "volume": 0,
             "time_mode": "normalized", "grain": {"envelope": "hanning"}},
    "axes": {"density": {"path": "density", "baseline": 20, "values": [5, 50]}},
    "sweep": {"mode": "envelope", "orders": [1], "plateau": 5, "transition": 5},
    "for_each": {"base.volume": {"values": [0, 6]}},
}


def _studio(tmp_path, monkeypatch, doc=None):
    monkeypatch.setattr(cli, "REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("COMBO", raising=False)
    sdir = tmp_path / "studies" / "s_fe"
    sdir.mkdir(parents=True)
    (sdir / "study.yml").write_text(yaml.safe_dump(doc or _DOC, sort_keys=False))
    return sdir


def test_gen_dir_scende_di_un_livello_solo_con_la_combinazione(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "REPO_ROOT", str(tmp_path))
    assert cli.gen_dir("s1") == os.path.join(str(tmp_path), "generated", "s1")
    monkeypatch.setattr(cli, "_COMBO", for_each.Combo("volume=6", (("base.volume", 6),)))
    assert cli.gen_dir("s1") == os.path.join(str(tmp_path), "generated", "s1", "volume=6")


def test_combo_filtra_e_una_label_sbagliata_e_errore(tmp_path, monkeypatch):
    _studio(tmp_path, monkeypatch)
    assert [c.label for c in cli._combos("s_fe")] == ["volume=0", "volume=6"]
    monkeypatch.setenv("COMBO", "volume=6")
    assert [c.label for c in cli._combos("s_fe")] == ["volume=6"]
    monkeypatch.setenv("COMBO", "volume=99")
    with pytest.raises(SpecError) as e:
        cli._combos("s_fe")
    assert "volume=0, volume=6" in str(e.value)


def _fake_engine(monkeypatch):
    import granstudies.render as render_mod

    def fake(yaml_path, output_path, samples_dir, output_sr=48000,
             per_stream=False, use_cache=False, cache_dir=None, jobs=1):
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w") as fh:
            fh.write(open(yaml_path).read())
        return [output_path]

    monkeypatch.setattr(render_mod.engine_bridge, "render", fake)


def test_il_giro_completo_produce_una_cartella_per_combinazione(tmp_path, monkeypatch):
    _studio(tmp_path, monkeypatch)
    _fake_engine(monkeypatch)
    assert cli.main(["sweep", "s_fe"]) == 0
    assert cli.main(["render", "s_fe", "--no-score"]) == 0

    g = tmp_path / "generated" / "s_fe"
    assert sorted(p.name for p in g.iterdir()) == ["volume=0", "volume=6"]
    for label, atteso in (("volume=0", 0), ("volume=6", 6)):
        # lo snapshot e' il documento PATCHATO: dice da se' i valori della
        # combinazione, senza rimandare al blocco for_each:
        snap = yaml.safe_load((g / label / "study.yml").read_text())
        assert snap["base"]["volume"] == atteso
        assert "for_each" not in snap
        variante = next((g / label / "yaml").rglob("*.yml"))
        assert yaml.safe_load(variante.read_text())["streams"][0]["volume"] == atteso
    # e l'audio delle due combinazioni e' diverso davvero
    a0 = next((g / "volume=0" / "audio").rglob("*.aif")).read_text()
    a6 = next((g / "volume=6" / "audio").rglob("*.aif")).read_text()
    assert a0 != a6


def test_una_patch_su_axes_cambia_le_varianti_generate(tmp_path, monkeypatch):
    doc = dict(_DOC, for_each={"griglia": {
        "corta": {"axes.density.values": [5, 50]},
        "lunga": {"axes.density.values": [5, 20, 50]},
    }})
    _studio(tmp_path, monkeypatch, doc)
    assert cli.main(["sweep", "s_fe"]) == 0
    g = tmp_path / "generated" / "s_fe"
    corta = next((g / "griglia=corta" / "yaml").rglob("*.yml"))
    lunga = next((g / "griglia=lunga" / "yaml").rglob("*.yml"))
    punti = lambda p: len(yaml.safe_load(p.read_text())["streams"][0]["density"]["points"])
    assert punti(lunga) > punti(corta)


def test_combo_restringe_il_giro(tmp_path, monkeypatch):
    _studio(tmp_path, monkeypatch)
    monkeypatch.setenv("COMBO", "volume=6")
    assert cli.main(["sweep", "s_fe"]) == 0
    g = tmp_path / "generated" / "s_fe"
    assert [p.name for p in g.iterdir()] == ["volume=6"]


def test_where_stampa_una_root_per_combinazione(tmp_path, monkeypatch, capsys):
    _studio(tmp_path, monkeypatch)
    assert cli.main(["where", "s_fe"]) == 0
    out = capsys.readouterr().out.split()
    assert out == [str(tmp_path / "generated" / "s_fe" / "volume=0"),
                   str(tmp_path / "generated" / "s_fe" / "volume=6")]


def test_sv_di_combinazioni_diverse_hanno_nomi_diversi(tmp_path, monkeypatch):
    """Sonic Visualiser identifica la sessione dal nome file: due combinazioni
    dello stesso studio devono produrre .sv distinguibili, altrimenti la
    seconda non si apre mentre la prima e' aperta — e il confronto fra
    combinazioni e' il motivo per cui gli assi esterni esistono."""
    import granstudies.sv_export as sv_export

    _studio(tmp_path, monkeypatch)
    _fake_engine(monkeypatch)
    esportati = []
    monkeypatch.setattr(
        sv_export, "variant_to_sv",
        lambda variant, audio, out, layout, markers, markers_scope: esportati.append(out),
    )
    assert cli.main(["sweep", "s_fe"]) == 0
    assert cli.main(["render", "s_fe", "--no-score"]) == 0
    assert cli.main(["sv", "s_fe"]) == 0

    nomi = [os.path.basename(p) for p in esportati]
    assert len(nomi) == 2, nomi          # una variante per combinazione
    assert len(nomi) == len(set(nomi)), nomi
    assert all("volume=0" in n or "volume=6" in n for n in nomi)


def test_senza_for_each_niente_suffisso_e_niente_sottocartella(tmp_path, monkeypatch):
    doc = {k: v for k, v in _DOC.items() if k != "for_each"}
    _studio(tmp_path, monkeypatch, doc)
    _fake_engine(monkeypatch)
    assert cli.main(["sweep", "s_fe"]) == 0
    assert cli.sv_combo_suffix() == ""
    assert (tmp_path / "generated" / "s_fe" / "yaml").is_dir()
