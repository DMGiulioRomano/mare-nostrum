"""Diagnostica **non fatale**: i controlli che segnalano senza fermare.

Un errore ferma il processo perche' il documento non ha un significato; un
warning dice che il documento ne ha uno, ma probabilmente non quello voluto.
Prima di questo modulo la diagnostica non fatale era stampata direttamente
(``_warn_orphans`` in ``__main__``, un ``warnings.warn`` in ``render``), quindi
non riusabile da nessun altro consumatore.

Il vincolo che governa il modulo: ogni controllo e' una **funzione pura**

    (documento parsato, Locations) -> lista di Diagnostic

senza I/O. Chi stampa decide dove; il language server (issue #46) legge la
stessa lista invece di riscrivere il controllo, cosi' le due diagnostiche non
divergono. ``Diagnostic`` riusa ``SpecError.format_block()`` per il layout:
un warning e un errore devono leggersi allo stesso modo.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .errors import KeyPath, SpecError
from .expr import corredo_values, is_corredo, is_expr_node
from .inject import expr_names
from .value_generators import parse_corredo, stable_seed
from .yaml_loc import Locations

# Codici dei controlli: stabili, pensati per essere filtrati da un consumatore
# (un editor che spegne una regola, un test che ne cerca una).
CORREDO_SOTTO_CONSUMATO = "corredo-sotto-consumato"


@dataclass(frozen=True)
class Diagnostic:
    """Un rilievo non fatale, con le stesse coordinate di un ``SpecError``."""

    msg: str
    code: str
    key: KeyPath | None = None
    stream: str | None = None
    hint: str | None = None
    line: int | None = None
    source: str | None = None

    def format_block(self) -> str:
        """Il blocco multilinea del terminale, identico a quello degli errori."""
        return SpecError(
            self.msg,
            key=self.key,
            stream=self.stream,
            hint=self.hint,
            line=self.line,
            source=self.source,
        ).format_block()

    def dedup_key(self) -> tuple:
        """L'identita' del rilievo, per deduplicare fra combinazioni.

        Con ``spread.n`` mosso da ``versions:`` lo stesso corredo produce lo
        stesso rilievo in molte combinazioni: senza deduplica il rumore
        vanifica il segnale.
        """
        return (self.code, self.key, self.stream, self.msg)


@dataclass
class WarnCtx:
    """Il gemello non fatale di ``ErrCtx``: raccoglie invece di alzare."""

    locs: Locations | None = None
    stream: str | None = None
    items: List[Diagnostic] = field(default_factory=list)

    def warn(
        self,
        msg: str,
        *,
        code: str,
        key: KeyPath | None = None,
        hint: str | None = None,
    ) -> None:
        self.items.append(
            Diagnostic(
                msg,
                code=code,
                key=key,
                stream=self.stream,
                hint=hint,
                line=(
                    self.locs.lookup(key, stream=self.stream)
                    if self.locs is not None and key is not None
                    else None
                ),
                source=self.locs.source if self.locs else None,
            )
        )


def dedup(items: List[Diagnostic]) -> List[Diagnostic]:
    """I rilievi senza ripetizioni, nell'ordine di prima apparizione."""
    seen: set = set()
    out: List[Diagnostic] = []
    for d in items:
        k = d.dedup_key()
        if k not in seen:
            seen.add(k)
            out.append(d)
    return out


# --- il corredo sotto-consumato ----------------------------------------------


def check_corredi(data: Dict[str, Any], locs: Locations | None = None) -> List[Diagnostic]:
    """I corredi che lo spread non consuma fino in fondo.

    Un corredo sotto-consumato e' **legittimo** — si sta ascoltando un
    sottoinsieme dell'accordo — ma e' anche il sintomo piu' comune di un
    refuso, quindi warning e non errore.

    Il rilievo e' **per corredo**, non per gruppo: con due corredi di lunghezza
    diversa uno puo' essere sotto-consumato e l'altro no.

    Si guardano solo i corredi che quel gruppo legge **per voce**, cioe' con un
    indice che dipende da ``i``. Un corredo letto con il solo indice costante
    (``ratio[0]``, la fondamentale) non e' sotto-consumato da nessun ``n``: il
    messaggio «gli elementi da indice k non sono usati» sarebbe falso, perche'
    non ne usa nemmeno uno oltre il primo, ed e' esattamente cio' che si voleva.

    Va chiamato sul documento **grezzo**, con il blocco ``let:`` ancora
    presente: ``apply_document_let`` lo consuma e lo rimuove.
    """
    ctx = WarnCtx(locs=locs)
    doc_corredi = _corredi(data.get("let"), "let", data.get("study_id") or "study")
    for name, entry in (data.get("streams") or {}).items():
        if not isinstance(entry, dict) or not isinstance(entry.get("spread"), dict):
            continue
        ctx.stream = name
        gruppo = _corredi(entry.get("let"), f"{name}:let", name)
        visibili = {**doc_corredi, **gruppo}
        if not visibili:
            continue
        scalari = {
            **_scalari(data.get("let")),
            **_scalari(entry.get("let")),
        }
        n = _static_n(entry["spread"], visibili, scalari)
        if n is None:
            continue
        for var, corredo in visibili.items():
            elems = corredo_values(corredo)
            if len(elems) <= n:
                continue
            if not _read_per_voice(entry, var):
                continue
            dove = ("streams", name, "let", var) if var in gruppo else ("let", var)
            inutilizzati = _unused(entry, var, corredo, n, scalari)
            if inutilizzati is None:
                coda = "il corredo non e' consumato tutto."
            else:
                quali = ", ".join(str(k) for k in inutilizzati)
                coda = f"gli elementi agli indici {quali} non sono usati."
            ctx.warn(
                f"il corredo '{var}' del gruppo '{name}' ha {len(elems)} "
                f"elementi, ma lo spread genera {n} voci: {coda}",
                code=CORREDO_SOTTO_CONSUMATO,
                key=dove,
                hint=_hint(entry, var),
            )
    return dedup(ctx.items)


def _corredi(block: Any, seed_prefix: str, _sid: str) -> Dict[str, Dict[str, Any]]:
    """I corredi di un blocco ``let:``, risolti; i valori rotti si saltano.

    Rende il corredo **intero**, non i soli elementi: la politica di ``cycle``
    serve a normalizzare un indice calcolato (su un pattern si avvolge).

    Un corredo malformato e' gia' un **errore** del load, con posizione e
    rimedio: qui si tace, perche' un warning che duplica un errore e' rumore.
    """
    if not isinstance(block, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for name, val in block.items():
        if not is_corredo(val):
            continue
        try:
            out[name] = parse_corredo(
                val, name, seed=stable_seed(f"{seed_prefix}:{name}")
            )
        except ValueError:
            continue
    return out


def _scalari(block: Any) -> Dict[str, Any]:
    """Le manopole scalari di un ``let:``, per valutare uno ``spread.n``-expr."""
    if not isinstance(block, dict):
        return {}
    return {
        k: v
        for k, v in block.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }


def _static_n(
    spread: Dict[str, Any],
    corredi: Dict[str, Dict[str, Any]],
    scalari: Dict[str, Any] | None = None,
) -> int | None:
    """``spread.n`` quando e' decidibile senza generare, altrimenti ``None``.

    Decidibile: un intero letterale, o un nodo-expr che si valuta contro i soli
    corredi visibili (il caso ``{expr: "len(ratio)"}``, che e' la forma con cui
    la popolazione segue il corredo). Non decidibile: ``n`` mosso da
    ``versions:``/``percorso:``, che dipende dal prodotto cartesiano o dalle
    istanze — li' il rilievo puo' nascere solo alla generazione, una volta per
    combinazione, e la deduplica lo riduce a uno.
    """
    n = spread.get("n")
    if isinstance(n, int) and not isinstance(n, bool):
        return n
    if not is_expr_node(n):
        return None
    scope: Dict[str, Any] = dict(scalari or {})
    scope.update(corredi)
    if not expr_names(n["expr"]) <= set(scope):
        return None
    from .expr import eval_expr

    try:
        value = eval_expr(n["expr"], scope)
    except ValueError:
        return None
    return int(value) if isinstance(value, (int, float)) and value == int(value) else None


def _read_per_voice(entry: Dict[str, Any], var: str) -> bool:
    """True se il gruppo indicizza ``var`` con un indice che dipende da ``i``."""
    return any(
        _depends_on_i(text, var) for text in _expr_texts(entry.get("spread"))
    )


def _index_sources(entry: Dict[str, Any], var: str) -> List[str]:
    """I testi degli indici con cui il gruppo legge ``var`` per voce.

    Serve a dire *quali* elementi restano fuori invece di presumerlo: il
    corredo si legge all'indice che c'e' scritto, non necessariamente ``i``.
    """
    out: List[str] = []
    for text in _expr_texts(entry.get("spread")):
        try:
            tree = ast.parse(text, mode="eval")
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == var
            ):
                out.append(ast.unparse(node.slice))
    return out


def _is_identity(entry: Dict[str, Any], var: str) -> bool:
    """True se ``var`` si legge sempre e solo come ``var[i]``."""
    fonti = _index_sources(entry, var)
    return bool(fonti) and all(s == "i" for s in fonti)


def _unused(
    entry: Dict[str, Any],
    var: str,
    corredo: Dict[str, Any],
    n: int,
    scalari: Dict[str, Any],
) -> List[int] | None:
    """Gli indici di ``var`` che le ``n`` voci non toccano, o ``None``.

    ``None`` quando l'indice non e' valutabile staticamente (dipende da una
    manopola che qui non si vede): meglio tacere su *quali* elementi che
    affermare il falso.
    """
    from .expr import eval_expr, is_cyclic

    elems = corredo_values(corredo)
    size = len(elems)
    letti: set = set()
    fonti = _index_sources(entry, var)
    if not fonti:
        return None
    for voce in range(n):
        scope = {**scalari, var: corredo, "i": voce, "n": n}
        for sorgente in fonti:
            try:
                idx = eval_expr(sorgente, scope)
            except ValueError:
                return None
            if not isinstance(idx, (int, float)) or isinstance(idx, bool):
                return None
            if float(idx) != int(idx):
                return None
            idx = int(idx)
            pos = idx % size if is_cyclic(corredo) else idx + size if idx < 0 else idx
            if not 0 <= pos < size:
                return None
            letti.add(pos)
    return sorted(set(range(size)) - letti)


def _hint(entry: Dict[str, Any], var: str) -> str:
    """Il rimedio, che dipende da *come* il corredo viene letto.

    ``n: {expr: "len(var)"}`` consuma il corredo solo se l'indice e' ``i``: su
    un indice traslato alzare ``n`` lo manderebbe fuori range, quindi li' il
    consiglio romperebbe lo studio invece di aggiustarlo.
    """
    base = "e' legittimo (un sottoinsieme dell'accordo)"
    if _is_identity(entry, var):
        return f"{base}; per consumarlo tutto scrivi \"n: {{expr: 'len({var})'}}\"."
    return (
        f"{base}; il corredo si legge a un indice calcolato, quindi per "
        "consumarlo tutto vanno rivisti insieme 'n' e l'indice."
    )


def _expr_texts(node: Any) -> List[str]:
    """I testi di tutti i nodi-expr di una struttura (ricorsivo)."""
    out: List[str] = []
    if is_expr_node(node) and isinstance(node.get("expr"), str):
        out.append(node["expr"])
    if isinstance(node, dict):
        for v in node.values():
            out.extend(_expr_texts(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_expr_texts(v))
    return out


def _depends_on_i(text: str, var: str) -> bool:
    """True se in ``text`` compare ``var[...]`` con ``i`` dentro l'indice."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == var
            and any(
                isinstance(x, ast.Name) and x.id == "i"
                for x in ast.walk(node.slice)
            )
        ):
            return True
    return False


def check_corredi_combos(
    data: Dict[str, Any], locs: Locations | None = None
) -> List[Diagnostic]:
    """``check_corredi`` su ogni combinazione di ``versions:``, deduplicato.

    Con ``spread.n`` (o un corredo) mosso da ``versions:``, il rilievo dipende
    dalla combinazione e non e' decidibile sul solo riposo. Qui si modella
    l'ombreggiamento come lo fa la pipeline — il movimento sovrascrive il
    riposo nel blocco ``let:`` — e si passa il documento risultante allo
    stesso controllo puro. La deduplica riduce a uno il rilievo che si ripete
    in molte combinazioni: senza, il rumore vanificherebbe il segnale.

    Senza blocco ``versions:`` equivale a ``check_corredi``.
    """
    if not isinstance(data.get("versions"), dict):
        return check_corredi(data, locs)
    from .versions import axis_combos, parse_version_axes

    try:
        combos = axis_combos(parse_version_axes(data, locs))
    except ValueError:
        # Un blocco ``versions:`` malformato e' gia' un errore del load, con
        # posizione e rimedio: qui si tace invece di duplicarlo.
        return check_corredi(data, locs)
    out: List[Diagnostic] = []
    for _label, combo in combos:
        moved = {**(data.get("let") or {}), **combo}
        out.extend(check_corredi({**data, "let": moved}, locs))
    return dedup(out)
