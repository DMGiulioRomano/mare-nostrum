"""Il pattern compositivo a tre livelli: axes globale / axes di gruppo / spread.

Per comporre servono N gruppi di stream, ognuno con la propria evoluzione
formale nel tempo. Un solo ``axes:`` globale non basta — e' il padre di tutti.
Il livello mancante c'e' gia': ``proto`` in ``spread.expand_spreads`` copia nei
generati tutto cio' che non e' la chiave ``spread``, quindi una entry-spread
puo' portarsi il proprio ``axes:`` accanto a ``spread:``.

I tre livelli:
  1. ``axes:`` globale        -> i default comuni al documento
  2. ``axes:`` nella entry    -> l'evoluzione formale DI QUEL gruppo
  3. ``spread.over``          -> la differenziazione fra le voci del gruppo

Questi test fissano il pattern come regressione: e' la base su cui poggia
l'ascolto verticale a piu' gruppi.
"""
import pytest

from granstudies.errors import SpecError
from granstudies.spread import expand_spreads
from granstudies.stack import generate_stack_document
from granstudies.study_spec import resolve_streams
from granstudies.versions import generate_versions_document

AXIS_NAMES = frozenset({"density"})


def _gruppo(n, livello, *, respiro=None, off="i * 10", base=None, axes_extra=None):
    """Entry-spread: forma locale nel suo ``axes:``, respiro nel suo ``stack:``.

    La manopola per-voce e' la variabile ``off`` dentro il ``let`` dell'asse:
    lo spread scrive solo quella, non ricostruisce l'albero del generatore.
    """
    dens = {"base": base or {"expr": "d + off", "let": {"d": livello, "off": 0}}}
    dens.update(axes_extra or {})
    entry = {
        "axes": {"density": dens},
        "spread": {"n": n, "over": {"axes.density.base.let.off": {"expr": off}}},
    }
    if respiro is not None:
        entry["stack"] = {"density": respiro}
    return entry


def _doc(streams, *, padre=None, **extra):
    d = {
        "study_id": "t",
        "base": {"sample": "x.wav", "onset": 0, "time_mode": "normalized",
                 "duration": 10},
        "axes": {
            "density": padre
            if padre is not None
            else {"baseline": 10, "n": 4, "base": 5, "range": 1}
        },
        "stack": {},
        "streams": streams,
    }
    d.update(extra)
    return d


def _points(stream):
    """Breakpoint di density nel documento engine ({type, points, time_mode})."""
    dens = stream["density"]
    return dens["points"] if isinstance(dens, dict) else dens


def _valori(stream):
    return [v for _, v in _points(stream)]


# --- livello 2: l'axes della entry arriva ai generati ------------------------

def test_axes_entry_propagato_a_ogni_generato():
    streams = {
        "gruppo": _gruppo(
            3, 25, axes_extra={"drift": {"step": 0.12}}
        )
    }
    out = expand_spreads(streams, axis_names=AXIS_NAMES)

    assert list(out) == ["gruppo_1", "gruppo_2", "gruppo_3"]
    for name in out:
        dens = out[name]["axes"]["density"]
        assert dens["base"]["expr"] == "d + off"
        assert dens["drift"] == {"step": 0.12}
        assert dens["base"]["let"]["d"] == 25


def test_due_spread_forme_indipendenti():
    """Due gruppi nello stesso documento, due forme e due livelli distinti."""
    streams = {
        "a": _gruppo(2, 25),
        "b": _gruppo(2, 90, off="i * 5", axes_extra={"drift": {"step": 0.5}}),
    }
    out = expand_spreads(streams, axis_names=AXIS_NAMES)

    assert list(out) == ["a_1", "a_2", "b_1", "b_2"]
    assert out["a_1"]["axes"]["density"]["base"]["let"]["d"] == 25
    assert "drift" not in out["a_1"]["axes"]["density"]
    assert out["b_1"]["axes"]["density"]["base"]["let"]["d"] == 90
    assert out["b_1"]["axes"]["density"]["drift"] == {"step": 0.5}
    # e la differenziazione per voce resta interna al proprio gruppo
    off = lambda k: out[k]["axes"]["density"]["base"]["let"]["off"]
    assert [off("a_1"), off("a_2")] == [0, 10]
    assert [off("b_1"), off("b_2")] == [0, 5]


# --- livello 3: over su un let scrive la variabile, non l'albero -------------

def test_over_su_let_non_cancella_expr():
    streams = {"gruppo": _gruppo(3, 25)}
    out = expand_spreads(streams, axis_names=AXIS_NAMES)

    offs = [out[n]["axes"]["density"]["base"]["let"]["off"] for n in out]
    assert offs == [0, 10, 20]
    for name in out:
        base = out[name]["axes"]["density"]["base"]
        assert base["expr"] == "d + off"     # l'expr fratello sopravvive
        assert base["let"]["d"] == 25        # e anche l'altro let


# --- livello 1: il padre sopravvive dove il gruppo tace ----------------------

def test_merge_col_padre():
    specs = resolve_streams(_doc({"gruppo": _gruppo(2, 25)}))
    assert [s.stream_id for s in specs] == ["gruppo_1", "gruppo_2"]
    for spec in specs:
        # 'baseline' viene dal padre globale (il gruppo non lo ridichiara)
        assert spec.axes[0].baseline == 10
    # ...ma i livelli sono quelli iniettati per voce
    assert specs[0].axes[0].values != specs[1].axes[0].values


# --- respiro-X per gruppo ----------------------------------------------------

def test_stack_walk_per_gruppo():
    """Ogni gruppo ha la sua camminata-X: ``n`` emerge dalla banda integrata,
    quindi due respiri diversi -> due conteggi di breakpoint diversi."""
    doc = _doc(
        {
            "lento": _gruppo(2, 25, respiro={"base": 0.5}, axes_extra={"range": 1}),
            "veloce": _gruppo(2, 90, respiro={"base": 8}, axes_extra={"range": 1}),
        },
        padre={"baseline": 10},  # il padre NON possiede n: camminano i gruppi
    )
    # con la camminata-X i valori non stanno nello spec: nascono al build dello
    # stack (band_at sui tempi reali), quindi si guarda il documento engine.
    out = generate_stack_document(resolve_streams(doc), samples_dir=None)
    per_id = {s["stream_id"]: s for s in out["streams"]}
    assert sorted(per_id) == ["lento_1", "lento_2", "veloce_1", "veloce_2"]

    # 0.5 Hz su 10 s -> ~5 bp ; 8 Hz su 10 s -> ~80 bp
    assert len(_points(per_id["veloce_1"])) > len(_points(per_id["lento_1"])) * 4

    assert min(_valori(per_id["lento_1"])) >= 25
    assert min(_valori(per_id["lento_2"])) >= 35
    assert min(_valori(per_id["veloce_1"])) >= 90
    assert min(_valori(per_id["veloce_2"])) >= 100


def test_padre_con_n_collide_con_camminata_del_gruppo():
    """n-ownership fra livelli: ``n`` nel padre + camminata nel gruppo e'
    errore. Il conteggio ha un solo proprietario, quindi in composizione il
    padre globale va tenuto magro."""
    doc = _doc(
        {"g": _gruppo(2, 25, respiro={"base": 2}, axes_extra={"range": 1})},
        padre={"baseline": 10, "n": 4},
    )
    with pytest.raises(SpecError, match="n"):
        resolve_streams(doc)


# --- convivenza con versions e col documento engine --------------------------

def test_versions_inietta_dentro_axes_di_gruppo():
    """La variabile di ``versions:`` raggiunge il ``let`` di un axes di gruppo,
    e ogni gruppo la usa secondo la PROPRIA formula: e' la manopola condivisa."""
    doc = _doc(
        {
            "a": _gruppo(2, 25, base={"expr": "v + off", "let": {"v": 25, "off": 0}}),
            "b": _gruppo(
                2, 90, base={"expr": "v * 2 + off", "let": {"v": 25, "off": 0}}
            ),
        },
        versions={"duration": 10, "v": {"values": [10, 100]}},
    )
    out = generate_versions_document(doc, samples_dir=None)
    assert sorted(s["stream_id"] for s in out["streams"]) == [
        "a_1__v=10", "a_1__v=100", "a_2__v=10", "a_2__v=100",
        "b_1__v=10", "b_1__v=100", "b_2__v=10", "b_2__v=100",
    ]

    def _dens(sid):
        return _valori(next(s for s in out["streams"] if s["stream_id"] == sid))

    assert 10 <= min(_dens("a_1__v=10")) and max(_dens("a_1__v=10")) < 20
    assert 100 <= min(_dens("a_1__v=100"))
    assert 20 <= min(_dens("b_1__v=10")) and max(_dens("b_1__v=10")) < 30
    assert 200 <= min(_dens("b_1__v=100"))


def test_documento_engine_multistream():
    doc = _doc({"a": _gruppo(3, 25), "b": _gruppo(2, 90, off="i * 5")})
    out = generate_stack_document(resolve_streams(doc), samples_dir=None)

    assert [s["stream_id"] for s in out["streams"]] == [
        "a_1", "a_2", "a_3", "b_1", "b_2"
    ]
    centri = {
        s["stream_id"]: sum(_valori(s)) / len(_valori(s)) for s in out["streams"]
    }
    # gruppo a: 25 + i*10 ; gruppo b: 90 + i*5 — ogni voce sul proprio centro
    assert 25 <= centri["a_1"] < 30
    assert 35 <= centri["a_2"] < 40
    assert 45 <= centri["a_3"] < 50
    assert 90 <= centri["b_1"] < 95
    assert 95 <= centri["b_2"] < 100


def test_gain_compensation_su_piu_gruppi():
    """Con piu' gruppi la compensazione resta una trasformazione dei volumi.
    Senza ``samples_dir`` e' no-op: qui si verifica solo che la struttura regga
    (l'effetto udibile su livelli molto diversi va valutato sul render)."""
    doc = _doc(
        {"a": _gruppo(2, 25), "b": _gruppo(2, 90)},
        gain_compensation={"alpha": 0.7, "max_shift": 12},
    )
    out = generate_stack_document(resolve_streams(doc), samples_dir=None)
    assert len(out["streams"]) == 4
