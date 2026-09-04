"""Matrice dei risultati (``results.yml``): descrittori + curation manuale.

Una entry per variante con i campi automatici (descrittori, parametri) e i campi
manuali (``kept``, ``tags``, ``notes``). Il merge e' idempotente: rieseguire la
descrizione aggiorna i descrittori senza calpestare le annotazioni dell'utente.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import yaml

from . import descriptors

# Campi manuali da preservare attraverso i merge.
_MANUAL_FIELDS = ("kept", "tags", "notes")


def _blank_entry(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "kept": None,        # None = non ancora valutata; True/False = decisione
        "tags": [],
        "notes": "",
        "descriptors": {},
        "params": {},
    }


def build_results(
    audio_dir: str,
    params_by_name: Dict[str, Dict[str, float]] | None = None,
) -> List[Dict[str, Any]]:
    """Calcola i descrittori per ogni audio e produce le entry dei risultati."""
    params_by_name = params_by_name or {}
    entries: List[Dict[str, Any]] = []
    for fname in sorted(os.listdir(audio_dir)):
        if not fname.endswith((".aif", ".aiff", ".wav", ".flac")):
            continue
        name = os.path.splitext(fname)[0]
        entry = _blank_entry(name)
        entry["descriptors"] = descriptors.describe_file(os.path.join(audio_dir, fname))
        entry["params"] = params_by_name.get(name, {})
        entries.append(entry)
    return entries


def merge_results(
    existing: List[Dict[str, Any]], fresh: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Unisce: campi auto da ``fresh``, campi manuali da ``existing`` (per nome).

    Le entry presenti solo in ``existing`` (audio rimosso) vengono scartate; le
    nuove entry di ``fresh`` sono aggiunte con campi manuali di default.
    """
    by_name = {e["name"]: e for e in existing}
    merged: List[Dict[str, Any]] = []
    for fe in fresh:
        out = dict(fe)
        prev = by_name.get(fe["name"])
        if prev is not None:
            for field in _MANUAL_FIELDS:
                if field in prev:
                    out[field] = prev[field]
        merged.append(out)
    return merged


def load_results(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return list(data.get("variants", []))


def save_results(path: str, entries: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"variants": entries}, fh, sort_keys=False, allow_unicode=True)


def update_results_file(
    path: str,
    audio_dir: str,
    params_by_name: Dict[str, Dict[str, float]] | None = None,
) -> List[Dict[str, Any]]:
    """Ricalcola i descrittori e fonde con il ``results.yml`` esistente."""
    fresh = build_results(audio_dir, params_by_name=params_by_name)
    existing = load_results(path)
    merged = merge_results(existing, fresh)
    save_results(path, merged)
    return merged


def kept_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Solo le varianti marcate ``kept: true``."""
    return [e for e in entries if e.get("kept") is True]
