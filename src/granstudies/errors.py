"""Errori strutturati di ``study.yml``: cosa, dove (riga), in quale stream.

Un errore di validazione senza coordinate obbliga a cercare a mano la chiave
incriminata dentro il documento — con gli override di stream, in due posti.
``SpecError`` porta i campi che servono a correggere: ``key`` (path della
chiave nel documento), ``axis``, ``stream`` (None = documento base), ``line``
(riga in ``source``), ``hint`` (il rimedio). E' un ``ValueError``: il codice
e i test che catturano ``ValueError`` restano validi.

``ErrCtx`` e' il contesto che il parse porta con se' (posizioni + stream
corrente): ``err`` costruisce un ``SpecError`` risolvendo la riga
override-first, ``wrapping`` riavvolge i ``ValueError`` nudi dei moduli
profondi (``value_generators``, ``x_strategies``) con il contesto dell'asse
corrente, senza toccare quei moduli.
"""
from __future__ import annotations

import textwrap
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Tuple

from .yaml_loc import Locations

KeyPath = Tuple[Any, ...]


def dotted(key: KeyPath) -> str:
    return ".".join(str(k) for k in key)


class SpecError(ValueError):
    """Errore di validazione di ``study.yml`` con coordinate."""

    def __init__(
        self,
        msg: str,
        *,
        key: KeyPath | None = None,
        axis: str | None = None,
        stream: str | None = None,
        hint: str | None = None,
        line: int | None = None,
        source: str | None = None,
    ):
        self.msg = msg
        self.key = tuple(key) if key is not None else None
        self.axis = axis
        self.stream = stream
        self.hint = hint
        self.line = line
        self.source = source
        super().__init__(msg)

    def __str__(self) -> str:
        ctx = []
        if self.line is not None:
            ctx.append(f"{self.source or 'study.yml'}:{self.line}")
        if self.key:
            ctx.append(dotted(self.key))
        if self.stream:
            ctx.append(f"stream '{self.stream}'")
        suffix = f"  [{', '.join(ctx)}]" if ctx else ""
        rimedio = f" Rimedio: {self.hint}" if self.hint else ""
        return self.msg + rimedio + suffix

    def format_block(self) -> str:
        """Blocco multilinea per il terminale (usato dall'handler CLI)."""

        def wrapped(text: str) -> str:
            return textwrap.fill(
                text, width=74, initial_indent="", subsequent_indent=" " * 14
            )

        lines = []
        if self.line is not None or self.key:
            pos = f"{self.source or 'study.yml'}:{self.line}" if self.line else (self.source or "study.yml")
            if self.key:
                pos += f"  ({dotted(self.key)})"
            lines.append(f"  posizione:  {pos}")
        contesto = (
            f"stream '{self.stream}'" if self.stream
            else "documento base (nessuna stream)"
        )
        lines.append(f"  contesto:   {contesto}")
        lines.append(f"  problema:   {wrapped(self.msg)}")
        if self.hint:
            lines.append(f"  rimedio:    {wrapped(self.hint)}")
        return "\n".join(lines)


@dataclass
class ErrCtx:
    """Contesto d'errore del parse: posizioni del documento e stream corrente."""

    locs: Locations | None = None
    stream: str | None = None

    def _line(self, key: KeyPath | None) -> int | None:
        if self.locs is None or key is None:
            return None
        return self.locs.lookup(key, stream=self.stream)

    def err(
        self,
        msg: str,
        *,
        key: KeyPath | None = None,
        axis: str | None = None,
        hint: str | None = None,
    ) -> SpecError:
        return SpecError(
            msg,
            key=key,
            axis=axis,
            stream=self.stream,
            hint=hint,
            line=self._line(key),
            source=self.locs.source if self.locs else None,
        )

    @contextmanager
    def wrapping(
        self,
        *,
        key: KeyPath | None = None,
        axis: str | None = None,
        hint: str | None = None,
    ):
        """Riavvolge i ``ValueError`` nudi in ``SpecError`` col contesto dato."""
        try:
            yield
        except SpecError:
            raise
        except ValueError as e:
            prefix = f"Asse '{axis}': " if axis else ""
            raise self.err(prefix + str(e), key=key, axis=axis, hint=hint) from e
