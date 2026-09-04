"""Caricamento YAML con posizioni: ``{key-path -> riga}`` accanto ai dati.

``yaml.safe_load`` scarta i mark di posizione, quindi un errore di
validazione non sa dire *dove* vive la chiave incriminata. Qui il documento
viene composto una seconda volta come albero di nodi (``yaml.compose``, che
i mark li conserva) e se ne ricava una tabella laterale ``{tupla di chiavi
-> riga 1-based}``: ``("axes", "density", "base") -> 7``. Gli indici di
lista entrano nel path come interi.

La provenienza attraverso il deep-merge delle stream non richiede di
mergiare la tabella: ``Locations.lookup(path, stream=...)`` prova prima il
path dentro l'override (``("streams", sid) + path``) e poi il base — la
stessa precedenza di ``_deep_merge`` (l'override vince, il base resta;
``_replace_generators`` al piu' *toglie* chiavi, che quindi non vengono
piu' cercate).

Limite accettato: le chiavi vengono indicizzate come stringhe (in
``study.yml`` le chiavi sono sempre nomi), i due parse (dati e posizioni)
leggono lo stesso testo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

import yaml

KeyPath = Tuple[Any, ...]


@dataclass(frozen=True)
class Locations:
    """Tabella ``{key-path -> riga}`` di un documento, con la sua origine."""

    table: Dict[KeyPath, int] = field(default_factory=dict)
    source: str | None = None

    def lookup(self, path: KeyPath, stream: str | None = None) -> int | None:
        """Riga (1-based) della chiave, override-first se ``stream`` e' dato."""
        if stream is not None:
            line = self.table.get(("streams", stream) + tuple(path))
            if line is not None:
                return line
        return self.table.get(tuple(path))


def _walk(node: yaml.Node, path: KeyPath, table: Dict[KeyPath, int]) -> None:
    if isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            key = getattr(key_node, "value", None)
            if not isinstance(key, str):
                continue
            table[path + (key,)] = key_node.start_mark.line + 1
            _walk(value_node, path + (key,), table)
    elif isinstance(node, yaml.SequenceNode):
        for i, item in enumerate(node.value):
            table[path + (i,)] = item.start_mark.line + 1
            _walk(item, path + (i,), table)


def loads(text: str, source: str | None = None) -> tuple[Any, Locations]:
    """Come ``yaml.safe_load``, ma ritorna anche le posizioni delle chiavi."""
    data = yaml.safe_load(text)
    table: Dict[KeyPath, int] = {}
    node = yaml.compose(text, Loader=yaml.SafeLoader)
    if node is not None:
        _walk(node, (), table)
    return data, Locations(table=table, source=source)


def load(path: str) -> tuple[Any, Locations]:
    """Carica un file YAML da disco con le posizioni delle chiavi."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return loads(text, source=path)
