"""Ponte verso PythonGranularEngine (incluso come submodule in ``engine/``).

Dall'introduzione dell'API programmatica ``pge.api`` (refactor library/CLI
dell'engine, Fasi 1-4) questo modulo e' un wrapper sottile: niente piu'
replica di ``main._build_renderer`` ne' monkey-patch di ``PATHSAMPLES`` —
la directory dei sample viaggia come parametro ``samples_dir`` dell'API.

Resta ``_ensure_engine_on_path`` perche' il submodule non e' installato nel
venv: si usa inserendo ``engine/src`` in ``sys.path`` (in alternativa si
potrebbe fare ``pip install -e engine/``; decisione rimandata).
"""
from __future__ import annotations

import os
import sys
from typing import List, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
ENGINE_SRC = os.path.join(REPO_ROOT, "engine", "src")


def _ensure_engine_on_path() -> None:
    """Inserisce ``engine/src`` in ``sys.path`` se non gia' presente."""
    if not os.path.isdir(ENGINE_SRC):
        raise RuntimeError(
            "Submodule 'engine' non inizializzato. Esegui:\n"
            "  git submodule update --init --recursive"
        )
    if ENGINE_SRC not in sys.path:
        sys.path.insert(0, ENGINE_SRC)
    _patch_volume_ceiling()


# Tetto di volume (dB) voluto dallo studio, piu' alto del +12 dB dell'engine.
# Sopra 0 dBFS il renderer non normalizza: e' clipping vero, non headroom.
VOLUME_MAX_DB = 24.0


def _patch_volume_ceiling() -> None:
    """Alza ``max_val`` di ``volume`` nel registry dell'engine.

    ponytail: patch a runtime perche' l'engine e' un submodule e non espone
    un override dei bounds (``get_parameter_definition`` parametrizza solo
    ``sample_dur_sec`` e ``output_sr``). Il registry viene letto a ogni
    chiamata, quindi la mutazione vale per parser, api e ``bounds.py``.
    Da rimuovere se l'engine rendera' configurabili i bounds.
    """
    from dataclasses import replace

    from pge.parameters import parameter_definitions as pd

    current = pd.GRANULAR_PARAMETERS["volume"]
    if current.max_val != VOLUME_MAX_DB:
        pd.GRANULAR_PARAMETERS["volume"] = replace(
            current, max_val=VOLUME_MAX_DB
        )


def _silence_loggers(log_dir: str) -> None:
    """Disattiva il logging su console dell'engine, file su ``log_dir``.

    I ``configure_*`` sono API pubblica dell'engine: vanno chiamati prima
    di ``load_generator`` (la libreria non configura mai i logger da se').
    """
    from pge import configure_clip_logger, configure_engine_logger

    configure_clip_logger(
        enabled=False, console_enabled=False, file_enabled=False
    )
    configure_engine_logger(yaml_name="granstudies", log_dir=log_dir)


def expand_compact_env(compact: list) -> List[List[float]]:
    """Espande la forma compatta a cicli dell'engine in breakpoint ``[[t, y], ...]``.

    ``[pattern, end_time, n_reps, interp?, time_dist?, wrap?]`` (vedi
    ``engine/docs/reference/yaml.md`` §5). L'espansione e' quella dell'engine,
    non una riscritta: la stessa forma scritta in ``base:`` (che passa verbatim
    al parser dell'engine) e in un ``let:`` deve produrre gli stessi tempi, e
    ``time_dist``/``wrap`` vivono la'.
    """
    _ensure_engine_on_path()
    _silence_loggers(os.path.join(REPO_ROOT, "generated", ".logs"))
    from pge.envelopes.envelope_builder import EnvelopeBuilder

    return [[float(t), y] for t, y in EnvelopeBuilder.parse(list(compact))]


def load_generator(
    yaml_path: str,
    samples_dir: Optional[str] = None,
    log_dir: Optional[str] = None,
):
    """Carica un Generator dell'engine con streams gia' materializzati."""
    _ensure_engine_on_path()
    _silence_loggers(log_dir or os.path.join(REPO_ROOT, "generated", ".logs"))
    from pge import api

    return api.load_generator(str(yaml_path), samples_dir=samples_dir)


def render(
    yaml_path: str,
    output_path: str,
    samples_dir: str,
    output_sr: int = 48000,
    per_stream: bool = False,
    use_cache: bool = False,
    cache_dir: Optional[str] = None,
    jobs: int = 1,
) -> List[str]:
    """Renderizza un YAML in audio con il renderer NumPy (MIX di default).

    ``per_stream``: STEMS mode (un file per stream, engine ``--per-stream``)
    invece del MIX unico di default. ``use_cache`` attiva il caching
    incrementale per-stream dell'engine (``StreamCacheManager``): solo gli
    stream con fingerprint cambiato vengono ri-renderizzati. Ha effetto solo
    in combinazione con ``per_stream`` (e' l'unico caso con build
    incrementale per stream, vedi engine ``pge/cli.py``).

    ``jobs``: worker del parallelismo INTERNO dell'engine (chunk di grani in
    MIX, stream in STEMS). Va distinto da quello di ``render_variants``, che
    parallelizza tra varianti: su uno studio con poche varianti lunghe e' solo
    questo a usare la macchina.

    Il GC degli stem orfani resta disattivato (``run_cache_gc=False``) come
    nel bridge pre-API: questo modulo non cancella file gia' generati.

    Returns: lista dei path audio generati (1 elemento in MIX mode, N in
    STEMS mode).
    """
    gen = load_generator(yaml_path, samples_dir=samples_dir)
    from pge import api

    cache_manifest_path = None
    if use_cache:
        yaml_basename = os.path.splitext(os.path.basename(str(yaml_path)))[0]
        cdir = cache_dir or "cache"
        os.makedirs(cdir, exist_ok=True)
        cache_manifest_path = os.path.join(cdir, f"{yaml_basename}.json")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    result = api.render(
        gen,
        str(output_path),
        renderer="numpy",
        per_stream=per_stream,
        run_cache_gc=False,
        output_sr=output_sr,
        samples_dir=samples_dir,
        cache_manifest_path=cache_manifest_path,
        jobs=jobs,
    )
    return result.audio_paths


def stream_envelopes(
    yaml_path: str,
    samples_dir: str,
    punti: int = 600,
    log_dir: Optional[str] = None,
) -> List[dict]:
    """Le curve *realizzate* di uno stream, campionate e gia' normalizzate.

    E' quello che la partitura disegna nella corsia di uno stream
    (``ScoreVisualizer._draw_envelopes``), e viene dalle stesse due funzioni:
    ``envelope_extractor.get_stream_envelopes`` dice QUALI curve ha lo stream,
    ``envelope_display`` quanto sono alte. Non sono gli envelope scritti nello
    YAML ma quelli della IR: le costanti restano fuori, in piu' ci sono le
    curve derivate (``effective_density`` = fill_factor/grain_duration, che il
    motore calcola a ogni onset e non conserva) e gli offset per-voce, e il
    pitch e' gia' risolto nell'unita' attiva dello stream.

    Ogni curva scala sulla **propria** escursione (``display_ranges``, come la
    partitura), il pan sul giro fisso: ``y`` e' in [0, 1] su ``punti`` tempi
    equispaziati fra 0 e la durata dello stream, e ``min``/``max`` sono i
    valori veri, per l'etichetta.

    Lo stream e' il primo del documento: il laboratorio ne compone uno solo.
    """
    # `load_generator` racconta a voce cosa sta caricando (seed, stream): qui
    # non sta rendendo niente, e sulla console del server sarebbero due righe
    # per ogni ascolto.
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        gen = load_generator(yaml_path, samples_dir=samples_dir, log_dir=log_dir)
    streams = list(getattr(gen, "streams", None) or [])
    if not streams:
        return []
    stream = streams[0]

    from pge.rendering import envelope_display as display
    from pge.rendering.envelope_extractor import (
        ENVELOPE_COLORS, base_param_name, get_stream_envelopes)
    from pge.rendering.visualizer_config import ENVELOPE_RANGES, EnvelopeDisplay

    curve = get_stream_envelopes(stream, show_static=False,
                                 show_voice_offsets=True)
    durata = float(stream.duration)
    cfg = EnvelopeDisplay()
    onset = float(stream.onset)
    ranges = display.display_ranges(curve, onset, onset, onset + durata,
                                    pad_ratio=cfg.pad_ratio, samples=cfg.samples)
    unita = getattr(stream, "pitch_unit", None)
    pan = ENVELOPE_RANGES["pan"]
    n = max(2, punti)
    tempi = [durata * i / (n - 1) for i in range(n)]
    out: List[dict] = []
    for nome, envelope in curve.items():
        base = base_param_name(nome)
        valori = [float(envelope.evaluate(t)) for t in tempi]
        out.append({
            "nome": nome,
            "colore": ENVELOPE_COLORS.get(base, "#888888"),
            "min": min(valori),
            "max": max(valori),
            # L'etichetta e' quella della partitura: millisecondi per la grana,
            # dB per il volume, il simbolo dell'unita' attiva per il pitch.
            "da": display.value_label(base, min(valori), unita),
            "a": display.value_label(base, max(valori), unita),
            # float() esplicito: `normalize` passa da numpy, e json.dumps
            # non sa cosa farsene di un np.float64.
            "y": [round(float(display.normalize(nome, v, ranges, pan_range=pan)), 4)
                  for v in valori],
        })
    return out


def score_pdf(
    yaml_path: str,
    pdf_path: str,
    samples_dir: Optional[str] = None,
    config: Optional[dict] = None,
) -> str:
    """Esporta la partitura grafica (PDF) di un YAML via ScoreVisualizer."""
    gen = load_generator(yaml_path, samples_dir=samples_dir)
    from pge import api

    os.makedirs(os.path.dirname(os.path.abspath(pdf_path)), exist_ok=True)
    return api.export_score_pdf(
        gen, str(pdf_path), config=config, samples_dir=samples_dir
    )


def parameter_bounds(output_sr: Optional[int] = None) -> dict:
    """Bounds dei parametri via ``pge.api.parameter_bounds`` (engine #163).

    Senza argomenti equivale al registry statico ``GRANULAR_PARAMETERS``.
    Con ``output_sr`` il minimo di ``grain_duration`` diventa 1 campione
    (``1/output_sr``), lo stesso pavimento dinamico usato dall'engine in
    render (issue #17 di questo repo).
    """
    _ensure_engine_on_path()
    from pge import api

    return api.parameter_bounds(output_sr=output_sr)


def pitch_bounds(unit: str):
    """``ParameterBounds`` dell'unita' di pitch, dall'engine.

    ``unit`` e' il nome dell'unita' come appare nel blocco ``pitch:`` dello
    YAML (``semitones``, ``cents``, ``ratio``, ...). Le unita' sconosciute
    sollevano l'errore dell'engine: qui non si duplica la lista dei preset.
    """
    _ensure_engine_on_path()
    from pge.parameters.pitch_unit import make_pitch_unit

    return make_pitch_unit(unit).value_bounds()


def pitch_units() -> frozenset:
    """Nomi delle unita' di pitch note all'engine (preset di ``pitch_unit``)."""
    _ensure_engine_on_path()
    from pge.parameters.pitch_unit import PITCH_UNIT_PRESETS

    return frozenset(PITCH_UNIT_PRESETS)


def parameter_schema_paths() -> dict:
    """Mappa ``path YAML dotted -> chiave del registry`` da ``ALL_SCHEMAS``.

    Il path dotted e' quello usato nello ``study.yml``: gli schema ``stream`` e
    ``density`` portano gia' il path completo (``grain.duration``, ``density``),
    quello ``pointer`` e' relativo alla sezione (``start`` ->
    ``pointer.start``). I path segnaposto (``_dummy_fixed_zero_``,
    ``_internal_calc_``) non sono chiavi YAML e restano fuori.
    """
    _ensure_engine_on_path()
    from pge.parameters.parameter_schema import ALL_SCHEMAS

    out: dict = {}
    for section, schema in ALL_SCHEMAS.items():
        for spec in schema:
            if spec.yaml_path.startswith("_"):
                continue
            prefix = f"{section}." if section == "pointer" else ""
            out[f"{prefix}{spec.yaml_path}"] = spec.name
    return out


def default_output_sr() -> int:
    """Sample rate di render di default (costante engine, single source)."""
    _ensure_engine_on_path()
    from pge import DEFAULT_OUTPUT_SR

    return DEFAULT_OUTPUT_SR


def parameter_defaults() -> dict:
    """Mappa ``yaml_path -> default`` da tutti gli schema dell'engine.

    Single source of truth per i valori a riposo dei parametri: invece di
    duplicare i default nello ``study.yml``, l'asse che omette ``baseline`` lo
    risolve da qui (vedi ``study_spec.parse_study_spec``). I path con
    ``default=None`` (es. ``density``) restano fuori dalla risoluzione e
    richiedono un baseline esplicito.
    """
    _ensure_engine_on_path()
    from pge.parameters.parameter_schema import ALL_SCHEMAS

    out: dict = {}
    for schema in ALL_SCHEMAS.values():
        for spec in schema:
            out[spec.yaml_path] = spec.default
    return out


def window_names() -> frozenset:
    """Nomi di finestra (``grain.envelope``) noti all'engine, alias inclusi."""
    _ensure_engine_on_path()
    from pge.controllers.window_registry import WindowRegistry

    return frozenset(WindowRegistry.all_names())
