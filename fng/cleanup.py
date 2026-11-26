"""Depuración de una GLC cualquiera y conversión a Forma Normal de Chomsky.

Sigue el procedimiento de la guía del curso (``guia_FNC_FNG.pdf``). Cada etapa
queda registrada como un paso del historial:

Forma intermedia de Chomsky
1. Símbolos no generadores: se eliminan con todas las producciones que los usan.
2. Símbolos no alcanzables desde el inicial (variables y terminales).
3. Producciones ε: con las variables anulables se generan todas las
   combinaciones en que cada una aparece o no. Si el inicial es anulable se
   conserva la cadena vacía: ``S0 -> S | ε`` si S aparece a la derecha, o
   ``S -> ε`` si no aparece.
4. Producciones unitarias, con pares unitarios: cada ``A -> B`` se reemplaza,
   en su lugar, por las producciones no unitarias de B.
   (Si tras 3 y 4 quedan símbolos inútiles se eliminan otra vez.)

Forma Normal de Chomsky
5. Reemplazar terminales por variables (``A1 -> a``, ``B1 -> b``, ...) en los
   cuerpos de longitud >= 2.
6. Reemplazar producciones de 3 o más variables: ``Y -> X α`` pasa a
   ``Y -> X Y1`` con ``Y1 -> α`` (Y1, Y2, ...), reutilizando la variable cuando
   la misma cola ya fue procesada.

Las producciones conservan el orden en que están escritas (los reemplazos se
hacen en su lugar), como en la guía; así los nombres Y1, Y2, ... salen en el
mismo orden que en el ejercicio de la guía.
"""

from __future__ import annotations

from itertools import product
from typing import Callable, Dict, Iterable, List, Sequence, Set, Tuple

from .errors import ConversionError
from .grammar import Body, Grammar, format_production
from .validator import check_cnf

LogFunction = Callable[..., object]
Production = Tuple[str, Body]

MAX_EXPANSION = 5000

STAGE_USELESS = "Símbolos inútiles"
STAGE_NULL = "Producciones ε"
STAGE_UNIT = "Producciones unitarias"
STAGE_CNF = "Forma Normal de Chomsky"


def _set_text(symbols: Iterable[str], order: Sequence[str]) -> str:
    """Muestra un conjunto en el orden de declaración: { A, B } (o ∅)."""
    symbols = set(symbols)
    items = [s for s in order if s in symbols]
    return "{ " + ", ".join(items) + " }" if items else "∅"


def _productions_text(productions: Iterable[Production]) -> str:
    return ", ".join(format_production(h, b) for h, b in productions) or "ninguna"


def _unique(items: Iterable) -> List:
    return list(dict.fromkeys(items))


class CnfNormalizer:
    """Transforma ``grammar`` (en su lugar) hasta dejarla en FNC depurada."""

    def __init__(
        self,
        grammar: Grammar,
        log: LogFunction,
        check_size: Callable[[], None],
    ) -> None:
        self.grammar = grammar
        self.log = log
        self.check_size = check_size
        # Variables creadas para los terminales (A1 -> a, ...): la fase de
        # Greibach las enumera al final, como en la guía.
        self.terminal_variables: List[str] = []

    def run(self) -> None:
        self._remove_non_generating()
        self._remove_unreachable()
        self._remove_null_productions()
        self._remove_unit_productions()
        self._remove_leftover_useless()
        self._replace_terminals()
        self._reduce_long_productions()
        self._check_cnf()

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _productions(self) -> List[Production]:
        """Pares (cabeza, cuerpo) en el orden en que están escritos."""
        return list(self.grammar.all_productions())

    def _is_unit(self, body: Body) -> bool:
        return len(body) == 1 and self.grammar.is_variable(body[0])

    def _taken(self, name: str) -> bool:
        g = self.grammar
        return name in g.variables or name in g.terminals or name in g.productions

    def _log_step(
        self,
        kind: str,
        stage: str,
        title: str,
        description: str,
        identified: List[str],
        before: List[Production],
        highlight: Sequence[str] = (),
    ) -> None:
        """Registra la etapa con lo identificado y las producciones eliminadas y
        agregadas, calculadas comparando el antes y el después."""
        after = self._productions()
        before_set, after_set = set(before), set(after)
        details = list(identified) + [
            "Producciones eliminadas: "
            + _productions_text(p for p in before if p not in after_set),
            "Producciones agregadas: "
            + _productions_text(p for p in after if p not in before_set),
        ]
        self.log(kind, stage, title, description, details, highlight=list(highlight))
        self.check_size()

    # ------------------------------------------------------------------
    # 1 y 2. Símbolos inútiles: no generadores y no alcanzables
    # ------------------------------------------------------------------
    def _generating(self) -> Set[str]:
        """Variables con alguna producción formada solo por símbolos generadores
        (los terminales y ε son generadores)."""
        g = self.grammar
        generating: Set[str] = set()
        changed = True
        while changed:
            changed = False
            for head, body in self._productions():
                if head not in generating and all(
                    g.is_terminal(s) or s in generating for s in body
                ):
                    generating.add(head)
                    changed = True
        return generating

    def _reachable(self) -> Set[str]:
        """Símbolos (variables y terminales) alcanzables desde el inicial."""
        g = self.grammar
        reachable = {g.start}
        pending = [g.start]
        while pending:
            for body in g.productions_of(pending.pop(0)):
                for symbol in body:
                    if symbol not in reachable:
                        reachable.add(symbol)
                        if g.is_variable(symbol):
                            pending.append(symbol)
        return reachable

    def _drop_variables(self, variables: Sequence[str]) -> None:
        """Quita las variables y toda producción que las use."""
        g = self.grammar
        gone = set(variables)
        for variable in variables:
            g.remove_variable(variable)
        for head in list(g.productions):
            g.set_productions(
                head, [b for b in g.productions_of(head) if not gone.intersection(b)]
            )

    def _remove_non_generating(self) -> None:
        g = self.grammar
        before = self._productions()
        generating = self._generating()
        useless = [v for v in g.variables if v not in generating]
        if g.start not in generating:
            raise ConversionError(
                [
                    f"El lenguaje es vacío: el símbolo inicial {g.start} no genera ninguna "
                    "cadena terminal, por lo que la gramática no puede convertirse."
                ]
            )
        identified = [
            f"Variables generadoras: {_set_text(generating, g.variables)}",
            f"Variables no generadoras: {_set_text(useless, g.variables)}",
        ]
        self._drop_variables(useless)
        self._log_step(
            "cleanup",
            STAGE_USELESS,
            "Eliminación de símbolos no generadores",
            "Los terminales y ε son generadores; una variable es generadora si tiene "
            "por lo menos una producción formada únicamente por símbolos generadores. "
            "Las que no lo son se eliminan junto con toda producción en la que estén.",
            identified,
            before,
            useless,
        )

    def _remove_unreachable(self) -> None:
        g = self.grammar
        before = self._productions()
        order = g.variables + g.terminals
        reachable = self._reachable()
        unreachable_vars = [v for v in g.variables if v not in reachable]
        unreachable_terms = [t for t in g.terminals if t not in reachable]
        identified = [
            f"Símbolos alcanzables: {_set_text(reachable, order)}",
            f"Variables no alcanzables: {_set_text(unreachable_vars, g.variables)}",
            f"Terminales no alcanzables: {_set_text(unreachable_terms, g.terminals)}",
        ]
        self._drop_variables(unreachable_vars)
        for terminal in unreachable_terms:
            g.terminals.remove(terminal)
        self._log_step(
            "cleanup",
            STAGE_USELESS,
            "Eliminación de símbolos no alcanzables",
            f"Se eliminan los símbolos que no se pueden derivar, directa o "
            f"indirectamente, desde el símbolo inicial {g.start}.",
            identified,
            before,
            unreachable_vars,
        )

    # ------------------------------------------------------------------
    # 3. Producciones ε
    # ------------------------------------------------------------------
    def _nullable(self) -> Set[str]:
        """Variables con Y -> ε o con una producción formada solo por anulables."""
        nullable: Set[str] = set()
        changed = True
        while changed:
            changed = False
            for head, body in self._productions():
                if head not in nullable and all(s in nullable for s in body):
                    nullable.add(head)
                    changed = True
        return nullable

    def _new_start_name(self, base: str) -> str:
        name, suffix = base, 1
        while self._taken(name):
            name = f"{base}_{suffix}"
            suffix += 1
        return name

    def _remove_null_productions(self) -> None:
        g = self.grammar
        before = self._productions()
        nullable = self._nullable()
        total = sum(2 ** sum(1 for s in b if s in nullable) for _, b in before)
        if total > MAX_EXPANSION:
            raise ConversionError(
                ["Eliminar las producciones ε genera demasiadas producciones."]
            )

        start_on_right = g.start_appears_in_bodies()
        for head in list(g.heads_in_order()):
            bodies: List[Body] = []
            for body in g.productions_of(head):
                positions = [i for i, s in enumerate(body) if s in nullable]
                # Cada anulable aparece (True) o no (False): a lo más 2^n versiones.
                for keep in product([True, False], repeat=len(positions)):
                    kept = dict(zip(positions, keep))
                    candidate = tuple(s for i, s in enumerate(body) if kept.get(i, True))
                    if candidate:
                        bodies.append(candidate)
            g.set_productions(head, bodies)

        highlight = [v for v in g.variables if v in nullable]
        if g.start not in nullable:
            decision = "el lenguaje no contiene ε"
        elif start_on_right:
            old = g.start
            new = self._new_start_name(old + "0")
            g.variables.insert(0, new)
            g.start = new
            g.set_productions(new, [(old,), ()])
            decision = (
                f"ε pertenece al lenguaje y {old} aparece a la derecha: nuevo símbolo "
                f"inicial {new} -> {old} | ε"
            )
            highlight.insert(0, new)
        else:
            g.set_productions(g.start, list(g.productions_of(g.start)) + [()])
            decision = (
                f"ε pertenece al lenguaje y {g.start} no aparece a la derecha: se "
                f"conserva {g.start} -> ε"
            )

        self._log_step(
            "null",
            STAGE_NULL,
            "Eliminación de producciones ε",
            "Se identifican las variables anulables y, en cada producción, se "
            "contemplan todas las combinaciones en que cada una aparece o no (con n "
            "anulables, a lo más 2^n producciones). Las producciones X -> ε se eliminan.",
            [
                f"Variables anulables: {_set_text(nullable, g.variables)}",
                f"Decisión ε: {decision}",
            ],
            before,
            highlight,
        )

    # ------------------------------------------------------------------
    # 4. Producciones unitarias
    # ------------------------------------------------------------------
    def _unit_closure(self, variable: str) -> Tuple[List[str], List[Body]]:
        """Pares unitarios de ``variable`` (en orden de aparición) y sus
        producciones con cada unitaria reemplazada, en su lugar, por las no
        unitarias de la variable a la que apunta."""
        reached = [variable]
        bodies: List[Body] = []

        def visit(current: str) -> None:
            for body in self.grammar.productions_of(current):
                if not self._is_unit(body):
                    bodies.append(body)
                elif body[0] not in reached:
                    reached.append(body[0])
                    visit(body[0])

        visit(variable)
        return reached, _unique(bodies)

    def _remove_unit_productions(self) -> None:
        g = self.grammar
        before = self._productions()
        units = [(h, b) for h, b in before if self._is_unit(b)]
        closures = {v: self._unit_closure(v) for v in g.heads_in_order()}
        for variable, (_, bodies) in closures.items():
            g.set_productions(variable, bodies)

        pairs = [f"({v}, {w})" for v, (reached, _) in closures.items() for w in reached]
        self._log_step(
            "unit",
            STAGE_UNIT,
            "Eliminación de producciones unitarias",
            "Pares unitarios: (Y, Y) lo es para toda variable, y si (Y, X) lo es y "
            "X -> Z es unitaria, (Y, Z) también. Por cada par (X, Y) se agregan a X las "
            "producciones de Y que no son unitarias, en el lugar de X -> Y.",
            [
                "Producciones unitarias: "
                + (", ".join(format_production(h, b) for h, b in units) or "∅"),
                "Pares unitarios: " + (", ".join(pairs) or "∅"),
            ],
            before,
            [v for v, (reached, _) in closures.items() if len(reached) > 1],
        )

    def _remove_leftover_useless(self) -> None:
        """Al quitar ε y unitarias puede quedar una variable sin producciones o
        inalcanzable; en ese caso se depura otra vez para que la FNC quede limpia."""
        g = self.grammar
        generating = self._generating()
        useless = [v for v in g.variables if v not in generating]
        if useless:
            before = self._productions()
            self._drop_variables(useless)
            self._log_step(
                "cleanup",
                STAGE_UNIT,
                "Eliminación de símbolos no generadores (de nuevo)",
                "Tras quitar las producciones ε y unitarias, estas variables ya no "
                "generan ninguna cadena; se eliminan con las producciones que las usan.",
                [f"Variables no generadoras: {_set_text(useless, g.variables + useless)}"],
                before,
                useless,
            )
        reachable = self._reachable()
        unreachable_vars = [v for v in g.variables if v not in reachable]
        unreachable_terms = [t for t in g.terminals if t not in reachable]
        if unreachable_vars or unreachable_terms:
            before = self._productions()
            order_vars, order_terms = list(g.variables), list(g.terminals)
            self._drop_variables(unreachable_vars)
            for terminal in unreachable_terms:
                g.terminals.remove(terminal)
            self._log_step(
                "cleanup",
                STAGE_UNIT,
                "Eliminación de símbolos no alcanzables (de nuevo)",
                f"Tras quitar las producciones unitarias, estos símbolos ya no se "
                f"alcanzan desde {g.start}; se eliminan.",
                [
                    f"Variables no alcanzables: {_set_text(unreachable_vars, order_vars)}",
                    f"Terminales no alcanzables: {_set_text(unreachable_terms, order_terms)}",
                ],
                before,
                unreachable_vars,
            )

    # ------------------------------------------------------------------
    # 5. Reemplazar terminales por variables
    # ------------------------------------------------------------------
    def _terminal_variable_name(self, terminal: str) -> str:
        """A1 para a, B1 para b, ... (T1, T2, ... si el terminal no es una letra)."""
        base = terminal.upper() if terminal.isalpha() else "T"
        number = 1
        while self._taken(f"{base}{number}"):
            number += 1
        return f"{base}{number}"

    def _replace_terminals(self) -> None:
        g = self.grammar
        before = self._productions()
        needed = {s for _, b in before if len(b) >= 2 for s in b if g.is_terminal(s)}
        created: Dict[str, str] = {}
        for terminal in g.terminals:
            if terminal in needed:
                name = self._terminal_variable_name(terminal)
                g.add_variable(name)
                created[terminal] = name
        for head in list(g.heads_in_order()):
            g.set_productions(
                head,
                [
                    tuple(created.get(s, s) for s in b) if len(b) >= 2 else b
                    for b in g.productions_of(head)
                ],
            )
        for terminal, name in created.items():
            g.set_productions(name, [(terminal,)])
        self.terminal_variables = list(created.values())

        if created:
            identified = [f"Terminal '{t}' reemplazado por la variable {v}" for t, v in created.items()]
        else:
            identified = ["Ningún terminal aparece acompañado en una producción."]
        self._log_step(
            "cnf",
            STAGE_CNF,
            "Reemplazar terminales por variables",
            "Cada terminal que aparece acompañado de otros símbolos en una producción "
            "se reemplaza por una variable nueva cuya única producción es ese terminal.",
            identified,
            before,
            list(created.values()),
        )

    # ------------------------------------------------------------------
    # 6. Reemplazar producciones de 3 o más variables
    # ------------------------------------------------------------------
    def _reduce_long_productions(self) -> None:
        g = self.grammar
        before = self._productions()
        tails: Dict[Body, str] = {}
        last_inserted: Dict[str, str] = {}  # cada Yk se lista tras la variable que la originó
        counter = 0

        def variable_for(tail: Body, creator: str) -> str:
            nonlocal counter
            if tail not in tails:
                while True:
                    counter += 1
                    name = f"Y{counter}"
                    if not self._taken(name):
                        break
                g.add_variable(name, after=last_inserted.get(creator, creator))
                last_inserted[creator] = name
                tails[tail] = name
            return tails[tail]

        new_productions: Dict[str, List[Body]] = {}
        for head in list(g.heads_in_order()):
            for body in g.productions_of(head):
                current, symbols = head, body
                while len(symbols) > 2:
                    tail = symbols[1:]
                    variable = variable_for(tail, head)
                    new_productions.setdefault(current, []).append((symbols[0], variable))
                    current, symbols = variable, tail
                new_productions.setdefault(current, []).append(symbols)
        for head, bodies in new_productions.items():
            g.set_productions(head, bodies)

        if tails:
            identified = [
                f"{v} -> {' '.join(tail)}" for tail, v in sorted(tails.items(), key=lambda i: int(i[1][1:]))
            ]
        else:
            identified = ["No hay producciones de 3 o más variables."]
        self._log_step(
            "cnf",
            STAGE_CNF,
            "Reemplazar producciones de 3 o más variables",
            "Cada producción Y -> X α, con α de dos o más variables, se reemplaza por "
            "Y -> X Z con Z -> α (repitiendo si α tiene más de dos). La misma cola "
            "reutiliza la misma variable.",
            identified,
            before,
            list(tails.values()),
        )

    def _check_cnf(self) -> None:
        g = self.grammar
        errors = check_cnf(g)
        if errors:  # pragma: no cover - no debería ocurrir
            raise ConversionError(["Error interno al construir la FNC:"] + errors)
        self.log(
            "cnf",
            STAGE_CNF,
            "Gramática en Forma Normal de Chomsky",
            "Toda producción es X -> Y Z (dos variables) o W -> v (un terminal), y "
            "S -> ε solo si S no aparece a la derecha. Ahora se puede llevar a Greibach.",
            highlight=list(g.variables),
        )
