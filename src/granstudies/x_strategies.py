"""Strategy di X: la sequenza dei *tempi* dei breakpoint, normalizzati in [0, 1].

Due sole forme, riconosciute dalla *presenza* nel blocco ``stack:`` (niente piu'
nome-strategy): l'asse **assente** dal blocco usa ``linear`` (tempi equispaziati,
la Y possiede ``n``); l'asse **presente** con una banda ``base``/``range`` usa
``walk`` (i tempi emergono dalla frequenza, la X possiede ``n``). Le tre cose
restano ortogonali: il generatore di Y decide i valori, la strategy di X i tempi,
``interpolation`` la curva tra i breakpoint. Attenzione alle due "linear": la
strategy-X ``linear`` (tempi equispaziati) non c'entra con l'interpolation
``linear`` (retta tra due punti) — si puo' avere una X accelerando con
interpolation step.

Consumata solo dal processo ``stack``: lo sweep possiede la sua X via
plateau/transition e non passa di qui.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from .value_generators import Threshold, _band_sampler

# Tetto anti-runaway: una banda di frequenza troppo alta (o una durata enorme)
# genererebbe milioni di breakpoint. Meglio un errore esplicito di un file YAML
# ingestibile: e' un errore di configurazione, non un caso d'uso.
MAX_POINTS = 10_000

@dataclass(frozen=True)
class XUnit:
    """Un'unita' della banda della camminata.

    ``to_step`` mappa il valore pescato in banda nel passo in secondi verso il
    punto successivo — e' l'unica cosa che distingue le unita': la meccanica
    del walk (pescaggio, drift, guardie, normalizzazione) resta condivisa.
    ``err``/``runaway`` parametrizzano i messaggi delle due guardie.
    """

    to_step: Callable[[float], float]
    err: str        # valore in banda non positivo (passo infinito o nullo)
    runaway: str    # oltre MAX_POINTS (banda che genera troppi punti)


# Il registro delle unita'. Due sole *famiglie* semantiche: rate (``hz``,
# ``bpm`` = hz riscalato per 60) e periodo (``s``). Un'unita' nuova e' una
# entry qui piu' doc e test — ma la scelta tra rate e periodo non e'
# notazionale: pescaggio in banda, interpolazione degli Env di base/range e
# drift vivono nello spazio scelto (uniforme in periodo != uniforme in rate).
X_UNITS: Dict[str, XUnit] = {
    "hz": XUnit(
        to_step=lambda v: 1.0 / v,
        err="frequenza non positiva",
        runaway="banda base troppo alta",
    ),
    "s": XUnit(
        to_step=lambda v: v,
        err="periodo non positivo",
        runaway="periodo troppo corto",
    ),
    "bpm": XUnit(
        to_step=lambda v: 60.0 / v,
        err="bpm non positivi",
        runaway="banda base troppo alta",
    ),
}


def linear(n: int) -> List[float]:
    """``n`` tempi equispaziati in ``[0, 1]``: ``t_i = i / (n - 1)``.

    E' il default quando l'asse non dichiara una strategy-X: la Y possiede
    ``n`` e i breakpoint si distribuiscono uniformi. Caso ``n == 1``: un solo
    punto a ``0.0``.
    """
    if n < 1:
        raise ValueError(f"linear: n deve essere >= 1 (ricevuto {n})")
    if n == 1:
        return [0.0]
    return [round(i / (n - 1), 9) for i in range(n)]


def walk(
    duration: float,
    base: Threshold,
    range: Threshold = 0.0,
    seed: int = 0,
    distribution: str = "uniform",
    drift: Dict[str, Any] | None = None,
    unit: str = "hz",
) -> List[float]:
    """Tempi di breakpoint generati da una camminata in banda (frequenza o periodo).

    La X possiede ``n``: non si dichiara, emerge dalla banda integrata sulla
    durata. Meccanica: dal punto corrente ``t`` si pesca un valore nella banda
    ``[base(t), base(t) + range(t)]``; con ``unit: hz`` (default, storico) il
    valore e' una *frequenza di generazione* e il punto successivo cade a
    ``t + 1/f``; con ``unit: s`` e' il *periodo* in secondi e il punto cade a
    ``t + p`` — comodo quando gli intervalli sono nell'ordine delle decine di
    secondi (frequenze frazionarie scomode). Si ripete finche' si supera la
    fine; i tempi sono poi normalizzati in ``[0, 1]``. Le altre unita' vivono
    nel registro ``X_UNITS`` (``bpm``: battiti al minuto, ``t + 60/v`` — lo
    spazio-rate di hz riscalato).

    ``unit`` sceglie lo *spazio* della camminata, non una notazione: uniforme
    in periodo non e' uniforme in frequenza, e gli Env di ``base``/``range``
    si interpolano nello spazio scelto (lineare nel periodo != lineare nel
    rate). ``base``/``range`` sono inviluppi mobili nelle stesse forme della
    banda di Y (scalare | ``[a, b]`` | ``[[t, v], ...]`` |
    ``{type, points, curve}``); il pescaggio e' lo stesso della banda di Y
    (``_band_sampler``, modulo condiviso X/Y): ``distribution`` governa come si
    pesca (``uniform`` | ``gaussian``), ``drift`` la rende un random walk
    correlato — ``step`` letto sul tempo reale normalizzato, il dominio di
    ``base``/``range`` in questo registro. ``range`` assente (0) = banda
    collassata: la camminata segue ``base`` deterministicamente (il ``seed``
    non influisce sui tempi). Deterministico via ``seed``. Guardie: valore di
    banda non positivo -> errore (passo infinito o nullo); piu' di
    ``MAX_POINTS`` punti -> errore.
    """
    if duration <= 0:
        raise ValueError(f"walk-X: duration deve essere > 0 (ricevuta {duration})")
    if unit not in X_UNITS:
        opts = " | ".join(sorted(X_UNITS))
        raise ValueError(f"walk-X: unit '{unit}' non ammessa ({opts}).")
    xu = X_UNITS[unit]
    sample = _band_sampler(base, range, seed, distribution, drift, "walk-X")
    times: List[float] = [0.0]
    t = 0.0  # secondi reali
    while True:
        v = sample(t / duration)
        if v <= 0:
            raise ValueError(
                f"walk-X: {xu.err} ({v}) a t={t:.3f}s — "
                "la banda base/range deve restare > 0."
            )
        t += xu.to_step(v)
        # Bordo con tolleranza: l'accumulo float puo' fermarsi un epsilon prima
        # della fine (es. 50 passi da 0.2 -> 9.999...8) e produrre un punto
        # spurio a ~1.0. Un punto sul bordo esatto non e' comunque un plateau.
        if t / duration >= 1.0 - 1e-9:
            return times
        times.append(round(t / duration, 9))
        if len(times) > MAX_POINTS:
            raise ValueError(
                f"walk-X: oltre {MAX_POINTS} breakpoint — {xu.runaway} "
                f"per duration={duration}s."
            )


def x_owns_n(cfg: Dict[str, Any] | None) -> bool:
    """True se l'asse ha una camminata-X nel blocco ``stack:`` (possiede ``n``).

    Nel modello piatto non c'e' piu' un nome-strategy: la *presenza* di una entry
    con ``base`` sotto ``stack.<asse>`` marca la camminata (la X possiede n, i
    tempi emergono dalla frequenza). Assenza dal blocco = linear (n dalla Y).
    """
    return isinstance(cfg, dict) and "base" in cfg


def resolve_x(cfg: Dict[str, Any] | None, n: int) -> List[float]:
    """Risolve i tempi equispaziati (``linear``) quando la Y possiede ``n``.

    Nel modello piatto ``linear`` e' l'assenza dell'asse dal blocco ``stack:``:
    ``cfg`` assente/vuoto -> ``linear(n)``. Una entry con ``base`` e' invece una
    camminata (possiede n): non risolvibile con un ``n`` esterno -> errore.
    """
    if not cfg:
        return linear(n)
    if x_owns_n(cfg):
        raise ValueError(
            "strategy-X: la camminata (banda 'base') possiede n (i tempi emergono "
            "dalla frequenza): non risolvibile con un n dalla Y."
        )
    raise ValueError(
        f"strategy-X: entry stack senza 'base' {sorted(cfg)} — una entry sotto "
        "'stack:' e' una camminata e richiede 'base' (frequenza in Hz)."
    )
