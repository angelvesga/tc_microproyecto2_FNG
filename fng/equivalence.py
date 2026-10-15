"""Comprobación de equivalencia de gramáticas por enumeración de cadenas.

Calcula, para cada variable, todas las cadenas de longitud <= ``max_length``
que puede derivar (punto fijo). Dos gramáticas son consideradas equivalentes
hasta esa longitud si generan exactamente las mismas cadenas (RNF06).
"""

from __future__ import annotations

from typing import Dict, Optional, Set

from .grammar import Grammar

DEFAULT_MAX_LENGTH = 6
MAX_STRINGS_PER_VARIABLE = 20000


def language_up_to(grammar: Grammar, max_length: int = DEFAULT_MAX_LENGTH) -> Optional[Set[str]]:
    """Cadenas de longitud <= max_length generadas por el símbolo inicial.

    Devuelve ``None`` si la enumeración excede el límite de seguridad.
    Los terminales se concatenan tal cual (separados por espacio si alguno
    tiene más de un carácter) para evitar ambigüedades.
    """
    separator = " " if any(len(t) > 1 for t in grammar.terminals) else ""
    generated: Dict[str, Set[tuple]] = {v: set() for v in grammar.variables}

    changed = True
    while changed:
        changed = False
        for head, body in grammar.all_productions():
            for word in _expand(grammar, body, generated, max_length):
                bucket = generated.setdefault(head, set())
                if word not in bucket:
                    bucket.add(word)
                    changed = True
                    if len(bucket) > MAX_STRINGS_PER_VARIABLE:
                        return None
    return {separator.join(w) for w in generated.get(grammar.start, set())}


def _expand(grammar: Grammar, body, generated, max_length):
    """Todas las concatenaciones de palabras posibles para ``body``."""
    partial = {()}
    for symbol in body:
        if grammar.is_terminal(symbol):
            options = {(symbol,)}
        else:
            options = generated.get(symbol, set())
        partial = {p + o for p in partial for o in options if len(p) + len(o) <= max_length}
        if not partial:
            break
    return partial


def equivalent_up_to(first: Grammar, second: Grammar, max_length: int = DEFAULT_MAX_LENGTH):
    """Devuelve (equivalentes, lenguaje_1, lenguaje_2); ``None`` si no se pudo decidir."""
    lang_a = language_up_to(first, max_length)
    lang_b = language_up_to(second, max_length)
    if lang_a is None or lang_b is None:
        return None, lang_a, lang_b
    return lang_a == lang_b, lang_a, lang_b
