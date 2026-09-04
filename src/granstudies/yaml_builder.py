"""Costruzione di YAML engine-compatibili da uno stream base + override.

Gli override sono espressi come path *dotted* (``grain.duration``) -> valore.
Il valore puo' essere uno scalare (variante statica) o una lista di breakpoint
``[[t, v], ...]`` (envelope, usato da ``compose``). In entrambi i casi viene
inserito nella posizione annidata corretta dello stream.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Mapping, Sequence

from .expr import eval_expr, is_expr_node, parse_expr_node


def _resolve_expr_nodes(node: Any, path: str = "") -> Any:
    """Valuta i nodi-expr nei parametri statici dello stream.

    ``base.*`` non passa dalle seam degli Env (axes/stack), ma l'engine
    accetta envelope scritti direttamente nei parametri stream: un nodo-expr
    qui si valuta alla costruzione del documento — il choke point comune a
    sweep/stack/compose — e il risultato (scalare o Env in stile engine)
    passa cosi' come l'utente l'avrebbe scritto a mano.
    """
    if is_expr_node(node):
        try:
            text, let = parse_expr_node(node)
            return eval_expr(text, let)
        except ValueError as exc:
            raise ValueError(f"{path or 'stream'}: {exc}") from exc
    if isinstance(node, dict):
        return {
            k: _resolve_expr_nodes(v, f"{path}.{k}" if path else str(k))
            for k, v in node.items()
        }
    return node


def deep_set(d: Dict[str, Any], dotted_path: str, value: Any) -> None:
    """Imposta ``value`` in ``d`` seguendo un path dotted, creando i dict mancanti.

    Esempio: ``deep_set(s, "grain.duration", 0.2)`` -> ``s["grain"]["duration"] = 0.2``.
    """
    if not dotted_path:
        raise ValueError("dotted_path vuoto")
    keys = dotted_path.split(".")
    node = d
    for key in keys[:-1]:
        nxt = node.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            node[key] = nxt
        node = nxt
    node[keys[-1]] = value


def deep_get(d: Mapping[str, Any], dotted_path: str, default: Any = None) -> Any:
    """Legge un valore da un dict via path dotted (``default`` se assente)."""
    node: Any = d
    for key in dotted_path.split("."):
        if not isinstance(node, Mapping) or key not in node:
            return default
        node = node[key]
    return node


def build_stream(
    base_stream: Mapping[str, Any],
    overrides: Mapping[str, Any],
    *,
    envelope_time_mode: str | None = None,
    envelope_type: str = "linear",
    envelope_types: Mapping[str, str] | None = None,
) -> Dict[str, Any]:
    """Crea un nuovo dict stream = copia di ``base_stream`` con override applicati.

    Se ``envelope_time_mode`` e' valorizzato (es. ``"normalized"``), gli override
    *lista* (breakpoint ``[[t, v], ...]``) vengono wrappati nel dict envelope
    dell'engine ``{type: <tipo>, points: ..., time_mode: <mode>}``. Il ``<tipo>``
    e' preso per-path da ``envelope_types`` (assi con forme diverse nello stesso
    file); in mancanza ricade su ``envelope_type``. Lasciato a ``None`` (default)
    le liste passano grezze: cosi' la pipeline ``compose`` resta invariata.
    """
    types = envelope_types or {}
    stream = copy.deepcopy(dict(base_stream))
    for path, value in overrides.items():
        if envelope_time_mode is not None and isinstance(value, list):
            value = {
                "type": types.get(path, envelope_type),
                "points": value,
                "time_mode": envelope_time_mode,
            }
        deep_set(stream, path, value)
    return _resolve_expr_nodes(stream)


def build_document(
    base_stream: Mapping[str, Any],
    overrides: Mapping[str, Any],
    *,
    title: str | None = None,
    seed: int | None = None,
    duration: float | None = None,
    envelope_time_mode: str | None = None,
    envelope_type: str = "linear",
    envelope_types: Mapping[str, str] | None = None,
) -> Dict[str, Any]:
    """Crea un documento YAML engine completo con un singolo stream.

    Le chiavi top-level (``title``, ``seed``, ``duration``) sono incluse solo se
    fornite, cosi' l'output resta minimale e diff-friendly. ``envelope_time_mode``
    e' inoltrato a ``build_stream`` per il wrapping degli envelope.
    """
    doc: Dict[str, Any] = {}
    if title is not None:
        doc["title"] = title
    if seed is not None:
        doc["seed"] = seed
    if duration is not None:
        doc["duration"] = duration
    doc["streams"] = [
        build_stream(base_stream, overrides, envelope_time_mode=envelope_time_mode, envelope_type=envelope_type, envelope_types=envelope_types)
    ]
    return doc


def build_multi_document(
    streams: Sequence[Mapping[str, Any]],
    *,
    title: str | None = None,
    seed: int | None = None,
    duration: float | None = None,
) -> Dict[str, Any]:
    """Crea un documento YAML engine con N stream gia' costruiti (stack).

    Dove ``build_document`` esplode un solo stream, qui gli stream (tipicamente
    prodotti da ``build_stream``, misti scalare/envelope) vengono *collassati*
    in un unico documento: ``streams: [N]``. Le chiavi top-level restano
    opzionali come in ``build_document``.
    """
    if not streams:
        raise ValueError("build_multi_document: serve almeno uno stream.")
    doc: Dict[str, Any] = {}
    if title is not None:
        doc["title"] = title
    if seed is not None:
        doc["seed"] = seed
    if duration is not None:
        doc["duration"] = duration
    doc["streams"] = [dict(s) for s in streams]
    return doc
