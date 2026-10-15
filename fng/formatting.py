"""Presentación en texto de gramáticas (usada por la GUI y el historial)."""

from __future__ import annotations

from typing import List

from .grammar import Grammar, format_body


def format_grammar_definition(grammar: Grammar) -> str:
    """Muestra G = (V, T, S) en una línea por componente."""
    return (
        f"V = {{{', '.join(grammar.variables)}}}\n"
        f"T = {{{', '.join(grammar.terminals)}}}\n"
        f"S = {grammar.start}"
    )


def format_productions(grammar: Grammar, indent: str = "") -> str:
    """Una línea por variable: ``A -> a B | b``. Las variables sin reglas se omiten."""
    lines: List[str] = []
    for head in grammar.heads_in_order():
        bodies = grammar.productions_of(head)
        if bodies:
            alternatives = " | ".join(format_body(b) for b in bodies)
            lines.append(f"{indent}{head} -> {alternatives}")
    return "\n".join(lines)


def format_grammar(grammar: Grammar, indent: str = "") -> str:
    """Definición completa (V, T, S) seguida de las producciones."""
    return format_grammar_definition(grammar) + "\n" + format_productions(grammar, indent)
