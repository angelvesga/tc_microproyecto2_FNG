"""Modelo de datos de una Gramática Libre de Contexto (GLC).

Una producción se representa como una tupla de símbolos (``("A", "B")`` para
``X -> A B``). La producción vacía (épsilon) se representa con la tupla vacía.
Las producciones de cada variable se guardan en una lista ordenada *sin
duplicados* (requisito RNF07).
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Sequence, Tuple

EPSILON = "ε"

Body = Tuple[str, ...]


class Grammar:
    """Gramática G = (V, T, S, P) con producciones únicas y ordenadas."""

    def __init__(
        self,
        variables: Sequence[str],
        terminals: Sequence[str],
        start: str,
        productions: Optional[Dict[str, Sequence[Body]]] = None,
    ) -> None:
        self.variables: List[str] = list(dict.fromkeys(variables))
        self.terminals: List[str] = list(dict.fromkeys(terminals))
        self.start: str = start
        self.productions: Dict[str, List[Body]] = {}
        for head, bodies in (productions or {}).items():
            for body in bodies:
                self.add_production(head, body)

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------
    def productions_of(self, head: str) -> List[Body]:
        """Devuelve (sin copiar) las producciones de ``head``."""
        return self.productions.get(head, [])

    def all_productions(self) -> Iterator[Tuple[str, Body]]:
        """Recorre todas las producciones en el orden de las variables."""
        for head in self.heads_in_order():
            for body in self.productions.get(head, []):
                yield head, body

    def heads_in_order(self) -> List[str]:
        """Cabezas de producción: primero las declaradas, luego el resto."""
        ordered = [v for v in self.variables if v in self.productions]
        ordered += [h for h in self.productions if h not in self.variables]
        return ordered

    def is_variable(self, symbol: str) -> bool:
        return symbol in self.variables

    def is_terminal(self, symbol: str) -> bool:
        return symbol in self.terminals

    def symbols_in_bodies(self) -> set:
        return {symbol for _, body in self.all_productions() for symbol in body}

    def start_appears_in_bodies(self) -> bool:
        return any(self.start in body for _, body in self.all_productions())

    # ------------------------------------------------------------------
    # Modificación
    # ------------------------------------------------------------------
    def add_production(self, head: str, body: Sequence[str]) -> bool:
        """Agrega ``head -> body``. Devuelve False si ya existía (sin duplicar)."""
        body = tuple(body)
        bodies = self.productions.setdefault(head, [])
        if body in bodies:
            return False
        bodies.append(body)
        return True

    def set_productions(self, head: str, bodies: Sequence[Body]) -> None:
        """Reemplaza todas las producciones de ``head`` (eliminando duplicados)."""
        self.productions[head] = list(dict.fromkeys(tuple(b) for b in bodies))

    def remove_production(self, head: str, body: Sequence[str]) -> bool:
        bodies = self.productions.get(head, [])
        body = tuple(body)
        if body in bodies:
            bodies.remove(body)
            return True
        return False

    def add_variable(self, name: str, after: Optional[str] = None) -> None:
        """Agrega una variable; si se indica ``after`` se inserta a continuación."""
        if name in self.variables:
            return
        if after is not None and after in self.variables:
            self.variables.insert(self.variables.index(after) + 1, name)
        else:
            self.variables.append(name)

    def remove_variable(self, name: str) -> None:
        if name in self.variables:
            self.variables.remove(name)
        self.productions.pop(name, None)

    def copy(self) -> "Grammar":
        clone = Grammar(self.variables, self.terminals, self.start)
        clone.productions = {h: list(b) for h, b in self.productions.items()}
        return clone

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"Grammar(V={self.variables}, T={self.terminals}, S={self.start})"


def format_body(body: Sequence[str]) -> str:
    """Texto de la parte derecha de una producción (``ε`` si está vacía)."""
    return " ".join(body) if body else EPSILON


def format_production(head: str, body: Sequence[str]) -> str:
    return f"{head} -> {format_body(body)}"
