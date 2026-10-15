"""Lectura de gramáticas desde texto (campos del formulario web o archivos de ejemplo).

Formato de producciones (una variable por línea, alternativas con ``|``)::

    S -> A B | a
    A -> B C
    B -> b

Los símbolos se separan con espacios (``A -> B C``). Si un símbolo no está
separado (``A -> BC``) se intenta segmentar usando los símbolos declarados.
Para épsilon se acepta ``ε``, ``λ``, ``epsilon`` o ``&``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .grammar import EPSILON, Grammar

EPSILON_TOKENS = {"ε", "λ", "epsilon", "eps", "&"}
ARROWS = ("->", "→")

# Claves aceptadas en los archivos de ejemplo (sin tildes, en minúscula).
FILE_KEYS = {
    "variables": "variables",
    "terminales": "terminals",
    "inicial": "start",
    "simbolo inicial": "start",
    "producciones": "productions",
}


@dataclass
class ParseResult:
    """Resultado de interpretar el texto de una gramática."""

    grammar: Grammar
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def split_symbol_list(text: str) -> List[str]:
    """Separa una lista de símbolos por comas, punto y coma o espacios."""
    cleaned = text.replace("{", " ").replace("}", " ")
    return [token for token in re.split(r"[,;\s]+", cleaned.strip()) if token]


def _segment_token(token: str, symbols: Sequence[str]) -> Optional[List[str]]:
    """Divide ``token`` en símbolos declarados (prefiere el prefijo más largo)."""
    if token in symbols:
        return [token]
    for length in range(len(token) - 1, 0, -1):
        prefix = token[:length]
        if prefix in symbols:
            rest = _segment_token(token[length:], symbols)
            if rest is not None:
                return [prefix] + rest
    return None


def tokenize_body(text: str, declared: Sequence[str]) -> Tuple[str, ...]:
    """Convierte ``"A B"`` o ``"AB"`` en ``("A", "B")``; épsilon da ``()``."""
    tokens: List[str] = []
    for chunk in text.split():
        if chunk in EPSILON_TOKENS:
            continue
        pieces = _segment_token(chunk, declared)
        tokens.extend(pieces if pieces is not None else [chunk])
    return tuple(tokens)


def _split_arrow(line: str) -> Optional[Tuple[str, str]]:
    for arrow in ARROWS:
        if arrow in line:
            head, _, rest = line.partition(arrow)
            return head.strip(), rest.strip()
    return None


def parse_productions(
    text: str, declared: Sequence[str]
) -> Tuple[List[Tuple[str, Tuple[str, ...]]], List[str]]:
    """Interpreta el bloque de producciones. Devuelve (producciones, errores)."""
    productions: List[Tuple[str, Tuple[str, ...]]] = []
    errors: List[str] = []
    current_head: Optional[str] = None

    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("|") and current_head is not None:
            head, rhs = current_head, line[1:].strip()
        else:
            parts = _split_arrow(line)
            if parts is None:
                errors.append(
                    f"Línea {line_number}: '{line}' no tiene flecha '->'. "
                    "Use el formato  A -> B C | a"
                )
                continue
            head, rhs = parts
            if not head or len(head.split()) != 1:
                errors.append(
                    f"Línea {line_number}: la parte izquierda '{head}' debe ser "
                    "exactamente una variable."
                )
                continue
            current_head = head

        for alternative in rhs.split("|"):
            alternative = alternative.strip()
            if not alternative:
                errors.append(
                    f"Línea {line_number}: hay una alternativa vacía en '{line}'. "
                    f"Para la cadena vacía escriba {EPSILON}."
                )
                continue
            productions.append((head, tokenize_body(alternative, declared)))
    return productions, errors


def parse_grammar(
    variables_text: str, terminals_text: str, start_text: str, productions_text: str
) -> ParseResult:
    """Construye una :class:`Grammar` a partir de los cuatro campos de entrada."""
    variables = split_symbol_list(variables_text)
    terminals = split_symbol_list(terminals_text)
    start = start_text.strip()

    grammar = Grammar(variables, terminals, start)
    result = ParseResult(grammar)

    declared = sorted(set(variables) | set(terminals), key=len, reverse=True)
    productions, errors = parse_productions(productions_text, declared)
    result.errors.extend(errors)

    for head, body in productions:
        if not grammar.add_production(head, body):
            shown = " ".join(body) if body else EPSILON
            result.warnings.append(
                f"La producción duplicada '{head} -> {shown}' fue ignorada."
            )
    return result


def parse_file_text(text: str) -> Dict[str, str]:
    """Lee un archivo ``clave: valor`` y devuelve los cuatro campos de entrada.

    Claves: ``variables``, ``terminales``, ``inicial`` y ``producciones``
    (esta última ocupa todas las líneas siguientes).
    """
    fields = {"variables": "", "terminals": "", "start": "", "productions": ""}
    in_productions = False
    production_lines: List[str] = []

    for raw in text.splitlines():
        stripped = raw.strip()
        if in_productions:
            production_lines.append(raw)
            continue
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition(":")
        normalized = key.strip().lower().replace("í", "i")
        if separator and normalized in FILE_KEYS:
            target = FILE_KEYS[normalized]
            if target == "productions":
                in_productions = True
                if value.strip():
                    production_lines.append(value)
            else:
                fields[target] = value.strip()
    fields["productions"] = "\n".join(production_lines).strip()
    return fields
