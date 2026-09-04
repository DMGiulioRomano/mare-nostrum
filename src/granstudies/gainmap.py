"""Compensazione di guadagno fra stream che leggono punti diversi del buffer.

Piu' stream che granulano lo *stesso* sample in punti di lettura diversi
arrivano al mix con livelli molto diversi — sul sample dello studio ci sono
~33 dB fra il punto piu' forte e il piu' debole — e chi sta sotto viene
mascherato: l'ascolto verticale si riduce ai due o tre cugini che sfondano.

Il livello e' pero' **prevedibile prima del render**: con ``pointer.speed_ratio: 0``
ogni stream legge sempre la stessa finestra del buffer, quindi basta misurarne
l'RMS (pesato Hanning, come l'inviluppo del grano) su ``[start, start + grana)``.

Due regole tengono la correzione onesta:

1. **Solo il differenziale, mai il livello d'insieme.** Il riferimento e' la
   media degli stream *contemporanei*, non una costante: cosi' resta udibile
   che un grano piu' corto porta meno energia (percetto vero, misurato in 3.9
   dB fra grana 4 e 50 campioni) e si appiattisce solo il mascheramento
   reciproco, che e' artefatto del buffer.
2. **Contemporanei = che si sovrappongono davvero** (``[onset, onset+duration)``).
   Serve gia' senza ``percorso``: le versioni concatenate non suonano mai
   insieme, e una media presa sull'intero documento le normalizzerebbe l'una
   contro l'altra. Su uno stack simultaneo la regola degenera nella media dei
   cugini, quindi non esiste un caso speciale da mantenere.

La correzione si applica **in sottrazione**: gli offset vengono traslati in
blocco perche' il massimo sia 0: si abbassano i forti invece di alzare i
deboli. Il bound engine di ``volume`` e' [-120, +12] dB e la base tipica e' 0,
quindi alzare finirebbe contro il tetto; in piu' l'attenuazione ricrea da se'
l'headroom che N stream sommati richiedono. Lo shift e' **uno solo per
documento**, non per gruppo di sovrapposizione, cosi' i rapporti di livello fra
gruppi restano quelli che erano.
"""
from __future__ import annotations

import math
import os
from statistics import median
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import soundfile as sf

from . import bounds as bounds_mod

# Sotto questa soglia lo stream legge silenzio: non si compensa (alzare il
# silenzio non porta a galla niente) e non entra nel riferimento, altrimenti
# trascina la media di tutti verso il basso.
SILENCE_DB = -100.0

_DEFAULT_ALPHA = 1.0
_DEFAULT_MAX_SHIFT = 24.0

_cache: Dict[str, Tuple[np.ndarray, int]] = {}


def parse_config(data: Mapping[str, Any]) -> Optional[Dict[str, float]]:
    """Legge il blocco top-level ``gain_compensation:`` (None se assente).

    ``alpha`` 0 = nessuna correzione, 1 = stream contemporanei appaiati. Valori
    intorno a 0.7 livellano l'ascolto lasciando che il sample conservi i suoi
    punti forti e deboli. ``max_shift`` limita in dB quanto una singola
    correzione puo' spostare uno stream.
    """
    raw = data.get("gain_compensation")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(
            "gain_compensation: serve un blocco (es. 'gain_compensation: "
            "{alpha: 0.7}'), non un valore secco."
        )
    unknown = set(raw) - {"alpha", "max_shift"}
    if unknown:
        raise ValueError(
            f"gain_compensation: chiavi sconosciute {sorted(unknown)} "
            "(disponibili: alpha, max_shift)."
        )
    # ``alpha``/``max_shift`` sono scalari strutturali: un nodo-expr (o
    # qualunque non-numero) qui non e' valutabile e senza guardia esploderebbe
    # con un ``TypeError`` grezzo su ``float(...)`` (issue #37).
    for label, default in (("alpha", _DEFAULT_ALPHA), ("max_shift", _DEFAULT_MAX_SHIFT)):
        val = raw.get(label, default)
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError(
                f"gain_compensation.{label} deve essere un numero (dato {val!r}); "
                "un nodo-expr non e' ammesso qui."
            )
    alpha = float(raw.get("alpha", _DEFAULT_ALPHA))
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(
            f"gain_compensation.alpha deve stare fra 0 e 1 (dato {alpha})."
        )
    max_shift = float(raw.get("max_shift", _DEFAULT_MAX_SHIFT))
    if max_shift <= 0:
        raise ValueError(
            f"gain_compensation.max_shift deve essere > 0 dB (dato {max_shift})."
        )
    return {"alpha": alpha, "max_shift": max_shift}


def _load_mono(path: str) -> Tuple[np.ndarray, int]:
    hit = _cache.get(path)
    if hit is None:
        x, sr = sf.read(path, always_2d=False)
        if x.ndim > 1:
            x = x.mean(axis=1)
        hit = (np.asarray(x, dtype=np.float64), int(sr))
        _cache[path] = hit
    return hit


def _median_value(node: Any) -> Optional[float]:
    """Valore rappresentativo di un parametro scalare **o** envelope.

    Un envelope si riassume con la mediana dei breakpoint: una costante per
    documento lascia ~0.9 dB di residuo, mentre inseguire ogni breakpoint
    produrrebbe un envelope di volume che si muove alla velocita' della
    camminata (4-10 Hz), cioe' un tremolo non richiesto al posto di una
    correzione.
    """
    if isinstance(node, dict):
        node = node.get("points")
    if isinstance(node, (list, tuple)):
        ys = [
            float(p[1])
            for p in node
            if isinstance(p, (list, tuple)) and len(p) >= 2
        ]
        return median(ys) if ys else None
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return float(node)
    return None


def _window_samples(stream: Mapping[str, Any], sr: int) -> Optional[int]:
    """Finestra che il grano legge, in campioni (``grain.duration_unit``)."""
    grain = stream.get("grain")
    if not isinstance(grain, Mapping):
        return None
    dur = _median_value(grain.get("duration"))
    if dur is None or dur <= 0:
        return None
    if grain.get("duration_unit") == "samples":
        return max(1, int(round(dur)))
    dur_sec = dur * bounds_mod.grain_duration_factor(grain.get("duration_unit"))
    return max(1, int(round(dur_sec * sr)))


def _start_sample(stream: Mapping[str, Any], sr: int, n_frames: int) -> Optional[int]:
    """Punto di lettura in campioni.

    ``pointer.loop_unit`` non eredita da ``time_mode``: assente vale
    ``seconds``, come nell'engine da v9 (issue #222). Solo ``normalized``
    legge lo start come frazione della durata del sample.
    """
    pointer = stream.get("pointer")
    if not isinstance(pointer, Mapping):
        return None
    start = _median_value(pointer.get("start"))
    if start is None:
        return None
    unit = pointer.get("loop_unit")
    pos = start * n_frames if unit == "normalized" else start * sr
    if not 0 <= pos < n_frames:
        return None
    return int(pos)


def _rms_db(x: np.ndarray, start: int, win: int) -> float:
    seg = x[start:start + win]
    if seg.size == 0:
        return SILENCE_DB
    # Pesatura Hanning: e' l'inviluppo del grano, non una finestra d'analisi.
    # `hanning(n+2)[1:-1]` evita che a n=1 o 2 la finestra sia tutta zeri.
    seg = seg * np.hanning(seg.size + 2)[1:-1]
    return 20.0 * math.log10(max(float(np.sqrt(np.mean(seg ** 2))), 1e-12))


def _level_db(
    stream: Mapping[str, Any], samples_dir: Optional[str], sr: int
) -> Optional[float]:
    """Livello atteso dello stream, o None se non e' stimabile."""
    name = stream.get("sample")
    if not name:
        return None
    path = name if os.path.isabs(name) else os.path.join(samples_dir or "", name)
    if not os.path.isfile(path):
        return None
    x, file_sr = _load_mono(path)
    win = _window_samples(stream, file_sr)
    start = _start_sample(stream, file_sr, len(x))
    if win is None or start is None:
        return None
    return _rms_db(x, start, win)


def _span(stream: Mapping[str, Any]) -> Tuple[float, float]:
    onset = float(stream.get("onset") or 0.0)
    return onset, onset + float(stream.get("duration") or 0.0)


def _add_db(stream: Dict[str, Any], offset: float) -> None:
    volume = stream.get("volume", 0.0)
    if isinstance(volume, dict) and isinstance(volume.get("points"), list):
        volume["points"] = [[t, y + offset] for t, y in volume["points"]]
    elif isinstance(volume, list):
        stream["volume"] = [[t, y + offset] for t, y in volume]
    else:
        stream["volume"] = round(float(volume or 0.0) + offset, 2)


def compensate(
    streams: Sequence[Dict[str, Any]],
    *,
    samples_dir: Optional[str] = None,
    alpha: float = _DEFAULT_ALPHA,
    max_shift: float = _DEFAULT_MAX_SHIFT,
    output_sr: int = 48000,
) -> List[Optional[float]]:
    """Scrive l'offset di ``volume`` su ogni stream. Muta ``streams`` sul posto.

    Ritorna gli offset applicati (``None`` per gli stream lasciati stare),
    nell'ordine ricevuto: servono a spiegare nel log cosa e' stato corretto.
    """
    levels = [_level_db(s, samples_dir, output_sr) for s in streams]
    spans = [_span(s) for s in streams]
    audible = [
        lv is not None and lv > SILENCE_DB for lv in levels
    ]

    raw: List[Optional[float]] = []
    for i, level in enumerate(levels):
        if not audible[i]:
            raw.append(None)
            continue
        a0, a1 = spans[i]
        # ponytail: sovrapposizione non pesata (qualunque intersezione conta
        # come contemporaneita' piena) e O(n^2) — con decine di stream e'
        # irrilevante. Pesare per frazione di sovrapposizione se un giorno gli
        # stack sfalsati di `percorso` mostrano che serve.
        peers = [
            levels[j]
            for j in range(len(streams))
            if audible[j] and spans[j][0] < a1 and a0 < spans[j][1]
        ]
        ref = sum(peers) / len(peers)
        raw.append(max(-max_shift, min(max_shift, alpha * (ref - level))))

    applied = [o for o in raw if o is not None]
    if not applied:
        return raw
    # Traslazione in blocco: il massimo va a 0, cosi' si attenua soltanto. Uno
    # shift unico per documento (non per gruppo di sovrapposizione) preserva i
    # rapporti di livello fra gruppi.
    shift = max(applied)
    out: List[Optional[float]] = []
    for stream, offset in zip(streams, raw):
        if offset is None:
            out.append(None)
            continue
        offset = round(offset - shift, 2)
        _add_db(stream, offset)
        out.append(offset)
    return out
