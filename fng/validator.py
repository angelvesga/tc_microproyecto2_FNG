"""Validaciones: datos de entrada, Forma Normal de Chomsky y Forma Normal de Greibach.

Cada función devuelve una lista de mensajes de error en español; una lista
vacía significa que la validación fue exitosa (RNF11, RNF12).
"""

from __future__ import annotations

from typing import List

from .grammar import EPSILON, Body, Grammar, format_production


def validate_input(grammar: Grammar) -> List[str]:
    """Valida la estructura de la gramática (sección 7 del enunciado, sin FNC)."""
    errors: List[str] = []

    if not grammar.variables:
        errors.append("Debe declarar al menos una variable (símbolo no terminal).")
    if not grammar.terminals:
        errors.append("Debe declarar al menos un símbolo terminal.")
    if not grammar.start:
        errors.append("Debe indicar el símbolo inicial.")
    elif grammar.start not in grammar.variables:
        errors.append(
            f"El símbolo inicial '{grammar.start}' no pertenece al conjunto de variables."
        )

    common = sorted(set(grammar.variables) & set(grammar.terminals))
    if common:
        errors.append(
            "Los siguientes símbolos están declarados como variable y terminal a la "
            f"vez: {', '.join(common)}."
        )

    declared = set(grammar.variables) | set(grammar.terminals)
    for head in grammar.productions:
        if head not in grammar.variables:
            errors.append(
                f"La parte izquierda '{head}' no es una variable declarada "
                "(las producciones deben tener una variable a la izquierda)."
            )
    for head, body in grammar.all_productions():
        unknown = [s for s in body if s not in declared]
        if unknown:
            errors.append(
                f"La producción '{format_production(head, body)}' usa símbolos no "
                f"declarados: {', '.join(unknown)}."
            )
    if not any(grammar.productions.values()):
        errors.append("La gramática no tiene producciones.")
    return errors


def has_epsilon_start_rule(grammar: Grammar) -> bool:
    return () in grammar.productions_of(grammar.start)


def check_cnf(grammar: Grammar) -> List[str]:
    """Verifica que cada producción sea ``A -> BC`` o ``A -> a``.

    Se admite ``S -> ε`` únicamente cuando S no aparece en ninguna parte derecha
    (excepción estándar de la FNC para generar la cadena vacía).
    """
    errors: List[str] = []
    for head, body in grammar.all_productions():
        text = format_production(head, body)
        if len(body) == 0:
            if head != grammar.start:
                errors.append(
                    f"'{text}': solo el símbolo inicial puede producir ε en FNC."
                )
            elif grammar.start_appears_in_bodies():
                errors.append(
                    f"'{text}': S -> ε solo es válida si el símbolo inicial no aparece "
                    "en ninguna parte derecha."
                )
        elif len(body) == 1:
            if not grammar.is_terminal(body[0]):
                errors.append(
                    f"'{text}': una producción de un solo símbolo debe ser A -> a "
                    f"(con '{body[0]}' terminal); no se permiten producciones unitarias."
                )
        elif len(body) == 2:
            bad = [s for s in body if not grammar.is_variable(s)]
            if bad:
                errors.append(
                    f"'{text}': en A -> BC ambos símbolos deben ser variables "
                    f"(no lo son: {', '.join(bad)})."
                )
        else:
            errors.append(
                f"'{text}': tiene {len(body)} símbolos a la derecha; en FNC solo se "
                "permite A -> BC o A -> a."
            )
    return errors


def check_gnf(grammar: Grammar) -> List[str]:
    """Verifica que cada producción sea ``A -> a A1 A2 ... An`` (n >= 0)."""
    errors: List[str] = []
    for head, body in grammar.all_productions():
        text = format_production(head, body)
        if not grammar.is_variable(head):
            errors.append(f"'{text}': '{head}' no es una variable.")
        if len(body) == 0:
            if head != grammar.start or grammar.start_appears_in_bodies():
                errors.append(f"'{text}': producción ε no permitida en FNG.")
            continue
        if not grammar.is_terminal(body[0]):
            errors.append(f"'{text}': debe comenzar con un símbolo terminal.")
        rest_bad = [s for s in body[1:] if not grammar.is_variable(s)]
        if rest_bad:
            errors.append(
                f"'{text}': después del terminal solo pueden aparecer variables "
                f"(sobran: {', '.join(rest_bad)})."
            )
    return errors


def describe_cnf_form(body: Body) -> str:
    """Clasificación legible de una parte derecha (usada en el historial)."""
    if not body:
        return EPSILON
    return "A -> a" if len(body) == 1 else "A -> BC"
