"""Manopole di documento: il blocco top-level ``let:``.

Un dizionario ``{nome: valore}`` di manopole a riposo, risolte al load del
documento e iniettate per nome in ogni nodo-expr che le referenzia — la stessa
meccanica di ``versions._inject``, un livello sopra: ``let:`` dichiara il
riposo, ``versions:``/``percorso:`` il movimento (che iniettano *dopo* e quindi
ombreggiano la manopola). L'aggancio e' il load del documento, unico choke
point comune a tutti i comandi *prima* dei rispettivi processi: agganciarlo
dentro ``resolve_streams`` sarebbe sbagliato perche' versions risolve gli
stream dopo la propria iniezione, e il riposo sovrascriverebbe il movimento.

Valori ammessi: scalare, envelope disegnato (lista ``[[t, v], ...]`` o
``[a, b]``, forma statica di Env che ``eval_expr`` consuma tale e quale),
envelope **generato** (``{linear_env: ...}``, con dentro il vocabolario dei
generatori: lista, ``values``, ``ramp``, banda), la forma compatta a cicli,
**corredo** (``{list: [...]}``: una lista nominata, letta solo per indice), o
nodo-expr derivato (``{expr: "..."}``) che referenzia altre manopole.

Un ``let:`` e' il punto in cui la posizione **non** disambigua i due ruoli di
``values`` (issue #47): ``{values: [2, 3, 4, 7]}`` si legge come una lista e
produceva un envelope. Per questo qui il generatore nudo e' errore e il ruolo
va marcato: ``{linear_env: [2, 3, 4, 7]}``.
"""
from __future__ import annotations

import copy
from typing import Any, Dict

from .errors import ErrCtx
from .expr import (
    CORREDO_KEY,
    CYCLE_KEY,
    eval_expr,
    is_corredo,
    is_cyclic,
    is_expr_node,
)
from .inject import expr_names as _expr_names
from .inject import inject as _inject
from .inject import referenced_names as _referenced_names
from .value_generators import (
    expand_env,
    is_compact_env,
    is_generator_node,
    is_linear_env_node,
    parse_corredo,
    stable_seed,
)
from .yaml_loc import Locations


def apply_document_let(
    data: Dict[str, Any], locs: Locations | None = None
) -> Dict[str, Any]:
    """Documento con le manopole di ``let:`` risolte e iniettate.

    Senza blocco ``let:`` e' un no-op (ritorna ``data`` invariato). Con il
    blocco: risolve i valori (scalari, envelope, derivati), controlla che ogni
    manopola sia referenziata da almeno un'espressione, li inietta negli scope
    ``let`` per nome e rimuove il blocco dal documento.
    """
    ctx = ErrCtx(locs=locs)
    # Guardie che girano al load, prima che l'iniezione consumi i nomi
    # (documento e gruppo spariscono dopo).
    _check_shadowing(data, ctx)
    _check_local_corredi(data, ctx)
    _check_moved_corredi(data, ctx)
    block = data.get("let")
    if block is None:
        return data
    if not isinstance(block, dict):
        raise ctx.err(
            "let: serve un dict {manopola: valore}.",
            key=("let",),
            hint="es. 'let: {g0: 4, d0: 25}'.",
        )
    out = copy.deepcopy(data)
    out.pop("let")
    if not block:
        return out

    sid = data.get("study_id") or "study"
    resolved = resolve_knobs(block, f"{sid}:let", ctx, key_prefix=("let",))
    _guard_referenced(block, resolved, out, ctx)
    _inject(out, resolved)
    return out


def resolve_knobs(
    block: Dict[str, Any],
    seed_prefix: str,
    ctx: ErrCtx,
    *,
    key_prefix: tuple = ("let",),
) -> Dict[str, Any]:
    """Risolve i valori di un blocco di manopole (documento o gruppo).

    Scalari ed envelope statici (liste) sono gia' valori di scope; i corredi
    (``{list: [...]}``) si validano nella prima passata e restano dict; un
    ``linear_env`` e la forma compatta a cicli (``[pattern, 1, n_reps,
    ...]``) si compilano in envelope una volta, con seed
    ``stable_seed(f"{seed_prefix}:{nome}")`` — un pescaggio condiviso; i nodi-
    expr derivati si valutano contro le manopole gia' risolte, a fixpoint
    (l'ordine di dichiarazione non conta). ``key_prefix`` etichetta gli errori
    (``("let",)`` per il documento, ``("streams", nome, "let")`` per un gruppo).
    """
    resolved: Dict[str, Any] = {}
    pending: Dict[str, Any] = {}
    for name, val in block.items():
        if is_corredo(val):
            # I corredi si risolvono nella **prima passata**, prima del
            # fixpoint delle manopole derivate: una lista non e' mai derivata
            # (non e' un valore), e cosi' ``{expr: "ratio[0] * 2"}`` e' una
            # manopola derivata legittima, qualunque sia l'ordine di
            # dichiarazione.
            with ctx.wrapping(key=key_prefix + (name,)):
                resolved[name] = parse_corredo(
                    val, name, seed=stable_seed(f"{seed_prefix}:{name}")
                )
        elif isinstance(val, dict) and CYCLE_KEY in val and not is_expr_node(val):
            # ``cycle`` e' la politica di un corredo: da sola non significa
            # niente, e senza questa guardia il dict finirebbe in scope come
            # «forma non riconosciuta», con un errore che non nomina la causa.
            raise ctx.err(
                f"let: '{name}' dichiara '{CYCLE_KEY}' senza 'list' — "
                f"'{CYCLE_KEY}' e' la politica di un corredo (accordo o "
                "pattern), non un valore a se'.",
                key=key_prefix + (name,),
                hint=f"per un pattern che si ripete: "
                f"'{name}: {{list: [...], {CYCLE_KEY}: true}}'.",
            )
        elif is_expr_node(val):
            pending[name] = val
        elif (
            is_linear_env_node(val) or is_generator_node(val) or is_compact_env(val)
        ):
            # ``is_generator_node`` entra qui apposta: un generatore nudo in un
            # ``let:`` e' Famiglia 1 in posizione di Famiglia 2, e ``expand_env``
            # alza l'errore di migrazione verso ``linear_env:`` (issue #47) —
            # qui, dove c'e' il contesto per dire *quale* manopola.
            with ctx.wrapping(key=key_prefix + (name,)):
                resolved[name] = expand_env(
                    val, seed=stable_seed(f"{seed_prefix}:{name}"), path=name
                )
        else:
            resolved[name] = val  # scalare o envelope statico

    progress = True
    while pending and progress:
        progress = False
        for name in list(pending):
            node = pending[name]
            scope = dict(resolved)
            scope.update(node.get("let") or {})
            if _expr_names(node["expr"]) <= set(scope) | {"pi", "e"}:
                with ctx.wrapping(key=key_prefix + (name,)):
                    resolved[name] = eval_expr(node["expr"], scope)
                del pending[name]
                progress = True

    if pending:
        raise ctx.err(
            "let: manopole con dipendenze cicliche o irrisolvibili: "
            f"{sorted(pending)}.",
            key=key_prefix,
            hint="una manopola derivata puo' referenziare solo altre manopole.",
        )
    return resolved


def _knob_names(block: Any) -> set:
    return set(block) if isinstance(block, dict) else set()


def _check_shadowing(data: Dict[str, Any], ctx: ErrCtx) -> None:
    """Ombreggiare un nome fra livelli e' errore (documento > gruppo > voce).

    Documento e' antenato di ogni gruppo e di ogni ``spread.let``; il gruppo
    e' antenato del proprio ``spread.let``. Due gruppi diversi sono fratelli:
    lo stesso nome non collide. Gira al load, sul documento grezzo, prima che
    l'iniezione consumi i nomi.
    """
    doc = _knob_names(data.get("let"))
    for name, entry in (data.get("streams") or {}).items():
        if not isinstance(entry, dict):
            continue
        group = _knob_names(entry.get("let"))
        spread = entry.get("spread")
        voice = _knob_names(spread.get("let")) if isinstance(spread, dict) else set()
        for var in sorted(doc & group):
            raise ctx.err(
                f"let: il gruppo '{name}' ridichiara la manopola di documento "
                f"'{var}' — ombreggiare fra livelli e' errore.",
                key=("streams", name, "let", var),
                hint="dai un nome diverso alla manopola di gruppo (un valore "
                "diverso vuole un nome diverso, non una precedenza).",
            )
        for var in sorted(doc & voice):
            raise ctx.err(
                f"let: lo spread di '{name}' ridichiara la manopola di "
                f"documento '{var}' — ombreggiare fra livelli e' errore.",
                key=("streams", name, "spread", "let", var),
                hint="dai un nome diverso alla manopola di voce.",
            )
        for var in sorted(group & voice):
            raise ctx.err(
                f"let: lo spread di '{name}' ridichiara la manopola di gruppo "
                f"'{var}' — ombreggiare fra livelli e' errore.",
                key=("streams", name, "spread", "let", var),
                hint="dai un nome diverso alla manopola di voce.",
            )


def _check_local_corredi(data: Dict[str, Any], ctx: ErrCtx) -> None:
    """Un corredo **generato** nel ``let`` locale di un nodo-expr e' errore.

    Un corredo *letterale* li' e' invece ammesso, e non per concessione: e' un
    valore statico come ``[[0, 1], [1, 2]]``, che quel ``let`` accetta gia'.
    Vietarlo sarebbe arbitrario.

    Un corredo *generato* no, e la ragione e' precisa: il ``let`` locale entra
    nello scope **cosi' com'e'** — ``resolve_knobs`` lo fonde grezzo
    (``scope.update(node.get("let") or {})``), e nessuna seam lo espande —
    quindi il generatore non verrebbe mai eseguito e non avrebbe un seed da
    cui pescare. E' lo stesso motivo per cui un nodo-generatore in un ``let``
    e' errore, non un'analogia con esso.

    Gira **al load, sul documento grezzo**, come ``_check_shadowing``: dopo
    l'iniezione un corredo scritto a mano e uno iniettato sono
    indistinguibili, ma l'iniezione mette in scope corredi gia' *risolti*,
    cioe' letterali — quindi rieseguire questa guardia non produce falsi
    positivi.
    """
    _walk_expr_lets(data, ctx, ())


def _walk_expr_lets(node: Any, ctx: ErrCtx, key: tuple) -> None:
    """Cerca i ``let`` locali dei nodi-expr, ovunque siano nel documento."""
    if is_expr_node(node):
        local = node.get("let")
        if isinstance(local, dict):
            for name, val in local.items():
                if is_corredo(val) and isinstance(val.get(CORREDO_KEY), dict):
                    raise ctx.err(
                        f"expr: il corredo '{name}' nel 'let' locale di un "
                        "nodo-expr e' generato — il 'let' locale entra nello "
                        "scope com'e' scritto, senza espansione e senza seed, "
                        "quindi il generatore non verrebbe mai eseguito.",
                        key=key + ("let", name),
                        hint="dichiaralo in un 'let:' di documento o di gruppo, "
                        "che lo risolve al load e lo inietta gia' fatto; un "
                        "corredo *letterale* qui e' invece ammesso, come ogni "
                        "altro valore statico.",
                    )
    if isinstance(node, dict):
        for k, v in node.items():
            _walk_expr_lets(v, ctx, key + (k,))
    elif isinstance(node, list):
        for k, v in enumerate(node):
            _walk_expr_lets(v, ctx, key + (k,))


# Chiavi di ``percorso:`` che non sono traiettorie (vedi ``percorso.py``).
_PERCORSO_RESERVED = frozenset({"k", "onset", "arco", "passo", "duration"})

# Chiavi riservate di ``versions:`` (vedi ``versions.py``).
_VERSIONS_RESERVED = frozenset({"onset", "duration", "chunk"})


def _declared_corredi(data: Dict[str, Any]) -> Dict[str, Any]:
    """I corredi dichiarati nei ``let:`` di documento e di gruppo."""
    out: Dict[str, Any] = {}
    for block in [data.get("let")] + [
        e.get("let")
        for e in (data.get("streams") or {}).values()
        if isinstance(e, dict)
    ]:
        if isinstance(block, dict):
            out.update({k: v for k, v in block.items() if is_corredo(v)})
    return out


def _check_moved_corredi(data: Dict[str, Any], ctx: ErrCtx) -> None:
    """Il **tipo** lo fissa la dichiarazione in ``let:``.

    ``versions:`` e ``percorso:`` muovono il *valore* di una manopola, mai il
    suo tipo ne' la sua politica. Uno stato che sostituisce un corredo deve
    fornire un corredo, e della stessa politica di ``cycle`` — altrimenti la
    validita' dello studio cambierebbe da una versione all'altra, e un fuori
    range comparirebbe solo in alcune combinazioni del prodotto cartesiano.
    """
    corredi = _declared_corredi(data)
    if not corredi:
        return
    _walk_versions(data.get("versions"), corredi, ctx, ("versions",))
    percorso = data.get("percorso")
    if isinstance(percorso, dict):
        for name in percorso:
            if name in corredi and name not in _PERCORSO_RESERVED:
                raise ctx.err(
                    f"percorso: '{name}' e' dichiarato come corredo nel 'let:' "
                    "— una traiettoria e' una legge sul tempo, non una lista, "
                    "e il tipo lo fissa la dichiarazione.",
                    key=("percorso", name),
                    hint="muovi un'altra manopola, oppure togli il corredo dal "
                    "'let:' se volevi una traiettoria.",
                )


def _walk_versions(
    node: Any, corredi: Dict[str, Any], ctx: ErrCtx, key: tuple
) -> None:
    """Cerca in ``versions:`` i valori assegnati a un nome dichiarato corredo."""
    if not isinstance(node, dict):
        return
    for name, val in node.items():
        if name in _VERSIONS_RESERVED and len(key) == 1:
            continue
        sub = key + (name,)
        if name in corredi:
            _check_replacement(name, corredi[name], val, ctx, sub)
            continue
        _walk_versions(val, corredi, ctx, sub)


def _check_replacement(
    name: str, dichiarato: Any, mosso: Any, ctx: ErrCtx, key: tuple
) -> None:
    """Il valore che ``versions:`` mette al posto di un corredo."""
    if not is_corredo(mosso):
        raise ctx.err(
            f"versions: '{name}' e' dichiarato come corredo nel 'let:', ma "
            f"questo stato lo sostituisce con {mosso!r} — 'versions:' muove il "
            "valore di una manopola, mai il suo tipo.",
            key=key,
            hint=f"dai allo stato un corredo: \"{name}: {{list: [...]}}\".",
        )
    if is_cyclic(mosso) != is_cyclic(dichiarato):
        atteso = "un pattern (cycle: true)" if is_cyclic(dichiarato) else "un accordo"
        raise ctx.err(
            f"versions: '{name}' e' dichiarato come {atteso} nel 'let:', ma "
            "questo stato ne cambia la politica di 'cycle' — la dichiarazione "
            "fissa il tipo, 'versions:' muove solo il valore.",
            key=key,
            hint="altrimenti la validita' dello studio cambierebbe da una "
            "versione all'altra: un fuori range comparirebbe solo in alcune "
            "combinazioni.",
        )


def _guard_referenced(
    block: Dict[str, Any],
    resolved: Dict[str, Any],
    rest: Dict[str, Any],
    ctx: ErrCtx,
) -> None:
    """Ogni manopola dev'essere referenziata da un'espressione: dal resto del
    documento o da un'altra manopola derivata (specchio della guardia di
    versions)."""
    referenced = _referenced_names(rest)
    for val in block.values():
        if is_expr_node(val):
            referenced |= _expr_names(val["expr"])
    for name in block:
        if name not in referenced:
            raise ctx.err(
                f"let: la manopola '{name}' non e' referenziata da nessuna "
                "espressione del documento.",
                key=("let", name),
                hint=f"usala in un nodo-expr (es. \"expr: '{name} * 2'\") "
                "oppure toglila dal blocco.",
            )
