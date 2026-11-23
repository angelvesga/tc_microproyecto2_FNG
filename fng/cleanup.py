"""Depuración de una GLC cualquiera y conversión a Forma Normal de Chomsky.

Etapas (cada operación se registra como un paso del historial):

1. Depuración inicial: variables no generadoras y luego inalcanzables.
2. Nuevo símbolo inicial S0 -> S, solo si S genera ε y aparece a la derecha.
3. Eliminación de producciones nulas (A -> ε), conservando S -> ε si ε ∈ L(G).
4. Eliminación de producciones unitarias (A -> B), con clausura (admite ciclos).
5. Depuración final: no generadoras e inalcanzables otra vez.
6. FNC: terminales en cuerpos largos (T1 -> a, T2 -> b, ...) y binarización (X_i).
"""

from __future__ import annotations

from itertools import product
from typing import Callable, Dict, List, Set, Tuple

from .errors import ConversionError
from .grammar import Body, Grammar, format_body, format_production, fresh_name
from .validator import check_cnf

LogFunction = Callable[..., object]


class CnfNormalizer:
    """Transforma ``grammar`` (en su lugar) hasta dejarla en FNC depurada."""

    def __init__(
        self,
        grammar: Grammar,
        original: Grammar,
        log: LogFunction,
        check_size: Callable[[], None],
    ) -> None:
        self.grammar = grammar
        self.original = original
        self.log = log
        self.check_size = check_size
        self._terminal_count = 0  # variables T1, T2, ... creadas para terminales

    def run(self) -> None:
        self._remove_useless("Depuración inicial", initial=True)
        self._new_start_symbol()
        self._remove_null_productions()
        self._remove_unit_productions()
        self._remove_useless("Depuración final", initial=False)
        self._to_cnf()

    # ------------------------------------------------------------------
    # Símbolos inútiles
    # ------------------------------------------------------------------
    def _generating(self) -> Set[str]:
        g = self.grammar
        generating: Set[str] = set()
        changed = True
        while changed:
            changed = False
            for head, body in g.all_productions():
                if head not in generating and all(
                    g.is_terminal(s) or s in generating for s in body
                ):
                    generating.add(head)
                    changed = True
        return generating

    def _reachable(self) -> Set[str]:
        g = self.grammar
        reachable = {g.start}
        frontier = [g.start]
        while frontier:
            for body in g.productions_of(frontier.pop()):
                for symbol in body:
                    if g.is_variable(symbol) and symbol not in reachable:
                        reachable.add(symbol)
                        frontier.append(symbol)
        return reachable

    def _remove_useless(self, stage: str, initial: bool) -> None:
        g = self.grammar
        generating = self._generating()
        if g.start not in generating:
            raise ConversionError(
                [
                    f"El símbolo inicial {g.start} no genera ninguna cadena de terminales: "
                    "la gramática genera el lenguaje vacío y no puede convertirse."
                ]
            )
        useless = [v for v in g.variables if v not in generating]
        removed_bodies = [
            format_production(h, b)
            for h, b in g.all_productions()
            if h not in generating or any(g.is_variable(s) and s not in generating for s in b)
        ]
        for variable in useless:
            g.remove_variable(variable)
        for head in list(g.productions):
            g.set_productions(
                head, [b for b in g.productions_of(head) if all(s not in useless for s in b)]
            )
        if useless:
            details = [f"Variables no generadoras: {', '.join(useless)}"]
            if removed_bodies:
                details.append("Producciones eliminadas: " + ", ".join(removed_bodies))
            self.log(
                "cleanup",
                stage,
                "Eliminación de variables no generadoras (inútiles)",
                "Una variable es generadora si deriva alguna cadena de terminales. Las "
                "que no lo son, y toda producción que las use, se eliminan sin cambiar "
                "el lenguaje.",
                details,
                highlight=useless,
            )
        else:
            self.log(
                "cleanup",
                stage,
                "Variables no generadoras: no hay",
                "Todas las variables derivan al menos una cadena de terminales.",
            )

        reachable = self._reachable()
        unreachable = [v for v in g.variables if v not in reachable]
        for variable in unreachable:
            g.remove_variable(variable)
        if unreachable:
            self.log(
                "cleanup",
                stage,
                "Eliminación de variables inalcanzables",
                f"Estas variables no aparecen en ninguna derivación desde {g.start}, "
                "por lo que se eliminan.",
                [f"Eliminadas: {', '.join(unreachable)}"],
                highlight=unreachable,
            )
        else:
            self.log(
                "cleanup",
                stage,
                "Variables inalcanzables: no hay",
                f"Todas las variables se alcanzan desde {g.start}.",
            )
        self.check_size()

    # ------------------------------------------------------------------
    # Producciones nulas
    # ------------------------------------------------------------------
    def _nullable(self) -> Set[str]:
        nullable: Set[str] = set()
        changed = True
        while changed:
            changed = False
            for head, body in self.grammar.all_productions():
                if head not in nullable and all(s in nullable for s in body):
                    nullable.add(head)
                    changed = True
        return nullable

    def _new_start_symbol(self) -> None:
        g = self.grammar
        if g.start not in self._nullable() or not g.start_appears_in_bodies():
            return
        old = g.start
        new = fresh_name("S0", g, self.original)
        g.variables.insert(0, new)
        g.start = new
        g.set_productions(new, [(old,)])
        self.log(
            "start",
            "Nuevo símbolo inicial",
            f"Se crea el símbolo inicial {new} -> {old}",
            f"{old} genera ε y aparece en partes derechas. Para poder conservar la "
            f"cadena vacía con {new} -> ε (sin que {new} aparezca a la derecha) se "
            "agrega un nuevo símbolo inicial.",
            highlight=[new, old],
        )

    def _remove_null_productions(self) -> None:
        g = self.grammar
        stage = "Producciones nulas"
        nullable = self._nullable()
        if not nullable:
            self.log(
                "null",
                stage,
                "Producciones nulas: no hay",
                "Ninguna variable deriva ε, no hay nada que eliminar.",
            )
            return

        total = sum(
            2 ** sum(1 for s in b if s in nullable) for _, b in g.all_productions()
        )
        if total > MAX_EXPANSION:
            raise ConversionError(
                ["Eliminar las producciones nulas genera demasiadas producciones."]
            )

        added: List[str] = []
        removed: List[str] = []
        for head in list(g.heads_in_order()):
            new_bodies: List[Body] = []
            for body in g.productions_of(head):
                if not body:
                    removed.append(format_production(head, body))
                    continue
                options = [((s,), ()) if s in nullable else ((s,),) for s in body]
                for choice in product(*options):
                    candidate = tuple(s for part in choice for s in part)
                    if candidate and candidate not in new_bodies:
                        new_bodies.append(candidate)
                        if candidate != body:
                            added.append(format_production(head, candidate))
            g.set_productions(head, new_bodies)

        keeps_epsilon = g.start in nullable
        if keeps_epsilon:
            g.set_productions(g.start, [()] + list(g.productions_of(g.start)))

        details = [
            f"Variables anulables (derivan ε): {', '.join(v for v in g.variables if v in nullable)}",
            "Producciones ε eliminadas: " + (", ".join(removed) or "ninguna"),
            "Producciones agregadas (omitiendo anulables): " + (", ".join(added) or "ninguna"),
        ]
        if keeps_epsilon:
            details.append(
                f"Como ε pertenece al lenguaje, se conserva {g.start} -> ε "
                f"({g.start} no aparece a la derecha)."
            )
        self.log(
            "null",
            stage,
            "Eliminación de producciones nulas",
            "Se calculan las variables anulables y, en cada producción, se agregan "
            "todas las variantes que omiten alguna de ellas; luego se eliminan las "
            "producciones A -> ε.",
            details,
            highlight=sorted(nullable),
        )
        self.check_size()

    # ------------------------------------------------------------------
    # Producciones unitarias
    # ------------------------------------------------------------------
    def _is_unit(self, body: Body) -> bool:
        return len(body) == 1 and self.grammar.is_variable(body[0])

    def _remove_unit_productions(self) -> None:
        g = self.grammar
        stage = "Producciones unitarias"
        if not any(self._is_unit(b) for _, b in g.all_productions()):
            self.log(
                "unit",
                stage,
                "Producciones unitarias: no hay",
                "Ninguna producción es de la forma A -> B.",
            )
            return

        closures: Dict[str, List[str]] = {}
        for variable in g.variables:
            closure = [variable]
            for current in closure:
                for body in g.productions_of(current):
                    if self._is_unit(body) and body[0] not in closure:
                        closure.append(body[0])
            closures[variable] = closure

        details = [
            f"Pares unitarios de {v}: {', '.join(c[1:])}"
            for v, c in closures.items()
            if len(c) > 1
        ]
        units = [format_production(h, b) for h, b in g.all_productions() if self._is_unit(b)]
        new_productions = {
            v: [b for member in closure for b in g.productions_of(member) if not self._is_unit(b)]
            for v, closure in closures.items()
        }
        for variable, bodies in new_productions.items():
            g.set_productions(variable, bodies)
        details.append("Producciones unitarias eliminadas: " + ", ".join(units))
        self.log(
            "unit",
            stage,
            "Eliminación de producciones unitarias",
            "Para cada par unitario (A, B) —A deriva B usando solo producciones "
            "unitarias— se copian a A las producciones no unitarias de B y se "
            "eliminan las producciones A -> B.",
            details,
            highlight=[v for v, c in closures.items() if len(c) > 1],
        )
        self.check_size()

    # ------------------------------------------------------------------
    # Forma Normal de Chomsky
    # ------------------------------------------------------------------
    def _to_cnf(self) -> None:
        g = self.grammar
        stage = "Forma Normal de Chomsky"
        self._replace_terminals(stage)
        self._binarize(stage)
        errors = check_cnf(g)
        if errors:  # pragma: no cover - no debería ocurrir
            raise ConversionError(["Error interno al construir la FNC:"] + errors)
        self.log(
            "cnf",
            stage,
            "Gramática en Forma Normal de Chomsky",
            "Toda producción es A -> BC o A -> a (y S -> ε solo si S no aparece a la "
            "derecha). Ahora se puede aplicar la conversión a Greibach.",
            highlight=list(g.variables),
        )

    def _terminal_variable(self, terminal: str, created: Dict[str, str]) -> Tuple[str, bool]:
        """Variable cuya única producción es ``terminal`` (reutiliza si ya existe)."""
        if terminal in created:
            return created[terminal], False
        g = self.grammar
        for variable in g.variables:
            if variable != g.start and g.productions_of(variable) == [(terminal,)]:
                created[terminal] = variable
                return variable, False
        while True:  # siguiente T1, T2, ... libre
            self._terminal_count += 1
            name = f"T{self._terminal_count}"
            if fresh_name(name, g, self.original) == name:
                break
        g.add_variable(name)
        g.set_productions(name, [(terminal,)])
        created[terminal] = name
        return name, True

    def _replace_terminals(self, stage: str) -> None:
        g = self.grammar
        created: Dict[str, str] = {}
        new_vars: List[str] = []
        changed: List[str] = []
        for head in list(g.heads_in_order()):
            bodies = []
            for body in g.productions_of(head):
                if len(body) >= 2 and any(g.is_terminal(s) for s in body):
                    replaced = []
                    for s in body:
                        if g.is_terminal(s):
                            variable, is_new = self._terminal_variable(s, created)
                            if is_new:
                                new_vars.append(variable)
                            replaced.append(variable)
                        else:
                            replaced.append(s)
                    changed.append(f"{format_production(head, body)}  ⇒  {format_body(replaced)}")
                    bodies.append(tuple(replaced))
                else:
                    bodies.append(body)
            g.set_productions(head, bodies)
        if not changed:
            self.log(
                "cnf",
                stage,
                "Terminales en producciones largas: no hay",
                "Ninguna producción de longitud ≥ 2 contiene terminales.",
            )
            return
        self.log(
            "cnf",
            stage,
            "Reemplazo de terminales en producciones largas",
            "En las producciones de longitud ≥ 2, cada terminal a se sustituye por "
            "una variable cuya única producción es a.",
            ["Variables usadas: " + ", ".join(f"{v} -> {t}" for t, v in created.items())]
            + changed,
            highlight=new_vars or list(created.values()),
        )
        self.check_size()

    def _binarize(self, stage: str) -> None:
        g = self.grammar
        tails: Dict[Body, str] = {}
        new_vars: List[str] = []
        changed: List[str] = []

        def variable_for(tail: Body) -> str:
            if tail in tails:
                return tails[tail]
            rest = tail if len(tail) == 2 else (tail[0], variable_for(tail[1:]))
            name = fresh_name(f"X{len(new_vars) + 1}", g, self.original)
            g.add_variable(name)
            g.set_productions(name, [rest])
            tails[tail] = name
            new_vars.append(name)
            return name

        for head in list(g.heads_in_order()):
            bodies = []
            for body in g.productions_of(head):
                if len(body) > 2:
                    new_body = (body[0], variable_for(body[1:]))
                    changed.append(f"{format_production(head, body)}  ⇒  {format_body(new_body)}")
                    bodies.append(new_body)
                else:
                    bodies.append(body)
            g.set_productions(head, bodies)

        if not changed:
            self.log(
                "cnf",
                stage,
                "Producciones de más de dos variables: no hay",
                "Todas las producciones tienen a lo sumo dos símbolos.",
            )
            return
        self.log(
            "cnf",
            stage,
            "División de producciones largas",
            "Cada producción A -> B1 B2 ... Bn (n > 2) se divide en A -> B1 X y "
            "X -> B2 ... Bn, repitiendo hasta que todas tengan dos variables.",
            [f"{v} -> {format_body(g.productions_of(v)[0])}" for v in new_vars] + changed,
            highlight=new_vars,
        )
        self.check_size()


MAX_EXPANSION = 5000
