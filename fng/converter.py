"""Conversión de una gramática en FNC a Forma Normal de Greibach, paso a paso.

Algoritmo (cada acción se registra como un :class:`~fng.history.Step`):

1. Validar la entrada (datos y FNC) y separar ``S -> ε`` si existe.
2. Ordenar las variables A1..An (el símbolo inicial es A1).
3. Para cada Ai, en orden:
   a. Sustituir toda producción ``Ai -> Aj γ`` con j < i por las producciones de Aj
      (repetidamente, mientras siga habiendo sustituciones posibles).
   b. Detectar recursividad izquierda directa ``Ai -> Ai α`` y eliminarla creando
      una variable auxiliar Zi:  ``Ai -> β | β Zi``  y  ``Zi -> α | α Zi``.
4. Sustitución hacia atrás (de An-1 a A1): las producciones de cada Ai que
   comienzan con variable se sustituyen por las de la variable siguiente, que ya
   comienzan con terminal.
5. Sustituir en las variables auxiliares Zi los inicios con variable.
6. Eliminar variables inalcanzables (opcional), restaurar ``S -> ε`` y validar FNG.
7. Verificar la equivalencia con la gramática original (cadenas hasta longitud 6).
"""

from __future__ import annotations

from typing import Callable, List, Optional

from .equivalence import DEFAULT_MAX_LENGTH, equivalent_up_to
from .grammar import Body, Grammar, format_body, format_production
from .history import History
from .history import Step
from .validator import check_cnf, check_gnf, has_epsilon_start_rule, validate_input

MAX_SUBSTITUTIONS_PER_VARIABLE = 10000


class ConversionError(Exception):
    """La gramática de entrada no puede convertirse (con mensajes comprensibles)."""

    def __init__(self, messages: List[str]) -> None:
        super().__init__("\n".join(messages))
        self.messages = messages


class FngConverter:
    """Ejecuta la transformación FNC -> FNG registrando cada operación."""

    def __init__(self, grammar: Grammar, remove_unreachable: bool = True) -> None:
        self.original = grammar.copy()
        self.grammar = grammar.copy()
        self.remove_unreachable = remove_unreachable
        self.history = History()
        self.order: List[str] = []
        self.auxiliary_variables: List[str] = []
        self._has_epsilon_start = False

    # ------------------------------------------------------------------
    # Punto de entrada
    # ------------------------------------------------------------------
    def run(self) -> History:
        errors = validate_input(self.grammar) + check_cnf(self.grammar)
        if errors:
            raise ConversionError(errors)

        self._log_input()
        self._separate_epsilon_rule()
        self._order_variables()
        for index in range(len(self.order)):
            self._process_variable(index)
        self._back_substitute()
        self._substitute_auxiliary_variables()
        self._remove_unreachable_variables()
        self._restore_epsilon_rule()
        self._final_validation()
        self.history.final_grammar = self.grammar
        return self.history

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------
    def _log(
        self,
        kind: str,
        stage: str,
        title: str,
        description: str,
        details: Optional[List[str]] = None,
        highlight: Optional[List[str]] = None,
    ) -> Step:
        step = Step(
            kind=kind,
            stage=stage,
            title=title,
            description=description,
            details=details or [],
            highlight=highlight or [],
        )
        return self.history.add(step, self.grammar)

    # ------------------------------------------------------------------
    # Etapa 0: entrada
    # ------------------------------------------------------------------
    def _log_input(self) -> None:
        g = self.grammar
        self._log(
            "input",
            "Entrada",
            "Gramática de entrada validada",
            "Se registraron variables, terminales, símbolo inicial y producciones, "
            "y la gramática cumple la Forma Normal de Chomsky "
            "(cada producción es A -> BC o A -> a).",
            [
                f"Variables: {', '.join(g.variables)}",
                f"Terminales: {', '.join(g.terminals)}",
                f"Símbolo inicial: {g.start}",
            ],
        )

    def _separate_epsilon_rule(self) -> None:
        if not has_epsilon_start_rule(self.grammar):
            return
        self._has_epsilon_start = True
        self.grammar.remove_production(self.grammar.start, ())
        self._log(
            "epsilon",
            "Entrada",
            f"Se aparta la producción {self.grammar.start} -> ε",
            "La FNC admite S -> ε (S no aparece a la derecha). Se aparta mientras se "
            "transforma el resto y se restaurará al final, pues la FNG la admite bajo "
            "la misma condición.",
            highlight=[self.grammar.start],
        )

    # ------------------------------------------------------------------
    # Etapa 1: orden de las variables
    # ------------------------------------------------------------------
    def _order_variables(self) -> None:
        g = self.grammar
        self.order = [g.start] + [v for v in g.variables if v != g.start]
        details = [f"A{i + 1} = {name}" for i, name in enumerate(self.order)]
        self._log(
            "order",
            "Ordenamiento de variables",
            "Orden de las variables",
            "Se establece el orden A1 < A2 < ... < An (el símbolo inicial es A1, el "
            "resto sigue el orden de declaración). Este orden guía las sustituciones: "
            "toda producción Ai -> Aj... deberá cumplir j > i.",
            details,
            highlight=list(self.order),
        )

    def _position(self, symbol: str) -> Optional[int]:
        """Posición de ``symbol`` en el orden (None si no es una variable ordenada)."""
        return self.order.index(symbol) if symbol in self.order else None

    # ------------------------------------------------------------------
    # Etapa 2: sustituciones y recursividad izquierda
    # ------------------------------------------------------------------
    def _process_variable(self, index: int) -> None:
        name = self.order[index]
        stage = f"Procesando {name} (A{index + 1})"

        def precedes(symbol: str) -> bool:
            position = self._position(symbol)
            return position is not None and position < index

        substitutions = self._substitute_leading(name, precedes, stage, "substitution")
        recursion_found = self._handle_left_recursion(index, stage)

        summary = []
        if not substitutions:
            summary.append(f"{name} no necesitó sustituciones.")
        if not recursion_found:
            summary.append(f"{name} no tiene recursividad izquierda directa.")
        self._log(
            "stage",
            stage,
            f"Gramática tras procesar {name}",
            f"Las producciones de {name} ahora comienzan con un terminal o con una "
            f"variable posterior a {name} en el orden.",
            summary,
            highlight=[name],
        )

    def _substitute_leading(
        self,
        head: str,
        should_replace: Callable[[str], bool],
        stage: str,
        kind: str,
    ) -> int:
        """Sustituye repetidamente cada ``head -> V γ`` donde ``should_replace(V)``.

        Devuelve cuántas sustituciones se hicieron. Cada una queda registrada.
        """
        count = 0
        while True:
            bodies = self.grammar.productions_of(head)
            position = next(
                (
                    k
                    for k, b in enumerate(bodies)
                    if b and self.grammar.is_variable(b[0]) and b[0] != head
                    and should_replace(b[0])
                ),
                None,
            )
            if position is None:
                return count

            count += 1
            if count > MAX_SUBSTITUTIONS_PER_VARIABLE:
                raise ConversionError(
                    [f"Se excedió el límite de sustituciones al procesar {head}."]
                )
            body = bodies[position]
            variable, tail = body[0], body[1:]
            replacements = [d + tail for d in self.grammar.productions_of(variable)]
            self.grammar.set_productions(
                head, bodies[:position] + replacements + bodies[position + 1:]
            )

            used = [format_production(variable, d) for d in self.grammar.productions_of(variable)]
            if replacements:
                result = " | ".join(format_body(r) for r in replacements)
                outcome = f"{head} -> {result}"
            else:
                outcome = f"{head} pierde esa producción ({variable} no tiene producciones)"
            self._log(
                kind,
                stage,
                f"Sustitución en {head}: {variable}",
                f"Se sustituye {variable} en '{format_production(head, body)}' por cada "
                f"producción de {variable}.",
                [f"Producciones de {variable} usadas: " + (", ".join(used) or "ninguna"),
                 f"Resultado: {outcome}"],
                highlight=[head, variable],
            )

    def _handle_left_recursion(self, index: int, stage: str) -> bool:
        """Detecta y elimina ``Ai -> Ai α``. Devuelve True si había recursividad."""
        name = self.order[index]
        bodies = self.grammar.productions_of(name)
        recursive = [b for b in bodies if b and b[0] == name]
        if not recursive:
            self._log(
                "detect",
                stage,
                f"Recursividad izquierda en {name}: no hay",
                f"Ninguna producción de {name} comienza con {name}.",
                highlight=[name],
            )
            return False

        self._log(
            "detect",
            stage,
            f"Recursividad izquierda directa detectada en {name}",
            f"Las producciones de {name} que comienzan con {name} son recursivas por "
            "la izquierda y deben eliminarse.",
            [format_production(name, b) for b in recursive],
            highlight=[name],
        )

        alphas = [b[1:] for b in recursive if len(b) > 1]
        betas = [b for b in bodies if not (b and b[0] == name)]
        trivial = [b for b in recursive if len(b) == 1]

        aux = self._new_auxiliary_name(index)
        self.grammar.add_variable(aux)
        self.auxiliary_variables.append(aux)

        new_head = list(betas) + [b + (aux,) for b in betas]
        new_aux = list(alphas) + [a + (aux,) for a in alphas]
        self.grammar.set_productions(name, new_head)
        self.grammar.set_productions(aux, new_aux)

        details = [
            f"β (no recursivas): {', '.join(format_body(b) for b in betas) or 'ninguna'}",
            f"α (resto de las recursivas): {', '.join(format_body(a) for a in alphas) or 'ninguna'}",
            f"{name} -> " + (" | ".join(format_body(b) for b in new_head) or "(sin producciones)"),
            f"{aux} -> " + (" | ".join(format_body(b) for b in new_aux) or "(sin producciones)"),
        ]
        if trivial:
            details.append(f"Se descartó {name} -> {name} (no aporta cadenas nuevas).")
        if not betas:
            details.append(
                f"{name} no tiene producciones no recursivas, por lo que no genera "
                "ninguna cadena (variable improductiva)."
            )
        self._log(
            "left_recursion",
            stage,
            f"Eliminación de recursividad izquierda en {name}: nueva variable {aux}",
            f"Se reemplaza {name} -> {name} α | β por {name} -> β | β {aux} y "
            f"{aux} -> α | α {aux}, que generan el mismo lenguaje.",
            details,
            highlight=[name, aux],
        )
        return True

    def _new_auxiliary_name(self, index: int) -> str:
        """Nombre único para la variable auxiliar de Ai (RNF08)."""
        taken = set(self.grammar.variables) | set(self.grammar.terminals)
        taken |= set(self.original.variables) | set(self.original.terminals)
        base = f"Z{index + 1}"
        name, suffix = base, 1
        while name in taken:
            suffix += 1
            name = f"{base}_{suffix}"
        return name

    # ------------------------------------------------------------------
    # Etapa 3: sustitución hacia atrás
    # ------------------------------------------------------------------
    def _back_substitute(self) -> None:
        stage = "Sustitución hacia atrás"
        did_something = False
        for index in range(len(self.order) - 2, -1, -1):
            name = self.order[index]
            count = self._substitute_leading(
                name, lambda s: self._position(s) is not None, stage, "back_substitution"
            )
            did_something = did_something or bool(count)
        self._log(
            "stage",
            stage,
            "Gramática tras la sustitución hacia atrás",
            "Todas las variables del orden original ya comienzan sus producciones "
            "con un símbolo terminal."
            if did_something
            else "No fue necesario sustituir: todas las producciones ya comienzan con terminal.",
            highlight=list(self.order),
        )

    # ------------------------------------------------------------------
    # Etapa 4: variables auxiliares
    # ------------------------------------------------------------------
    def _starts_with_terminal(self, variable: str) -> bool:
        return all(b and self.grammar.is_terminal(b[0]) for b in self.grammar.productions_of(variable))

    def _substitute_auxiliary_variables(self) -> None:
        if not self.auxiliary_variables:
            return
        stage = "Variables auxiliares"
        pending = list(self.auxiliary_variables)
        for _ in range(len(self.grammar.variables) + 2):
            progressed = False
            for aux in pending:
                count = self._substitute_leading(
                    aux,
                    lambda s: s not in pending or self._starts_with_terminal(s),
                    stage,
                    "aux_substitution",
                )
                progressed = progressed or bool(count)
            if not progressed:
                break
        pending_bad = [
            a for a in pending if not self._starts_with_terminal(a)
        ]
        if pending_bad:
            raise ConversionError(
                ["No se pudieron resolver las variables auxiliares: " + ", ".join(pending_bad)]
            )
        self._log(
            "stage",
            stage,
            "Gramática tras sustituir en las variables auxiliares",
            "Las producciones de las variables auxiliares ya comienzan con terminal.",
            highlight=pending,
        )

    # ------------------------------------------------------------------
    # Etapa 5: limpieza, ε y validación
    # ------------------------------------------------------------------
    def _remove_unreachable_variables(self) -> None:
        if not self.remove_unreachable:
            return
        g = self.grammar
        reachable = {g.start}
        frontier = [g.start]
        while frontier:
            head = frontier.pop()
            for body in g.productions_of(head):
                for symbol in body:
                    if g.is_variable(symbol) and symbol not in reachable:
                        reachable.add(symbol)
                        frontier.append(symbol)
        unreachable = [v for v in g.variables if v not in reachable]
        if not unreachable:
            return
        for variable in unreachable:
            g.remove_variable(variable)
        self._log(
            "cleanup",
            "Limpieza",
            "Eliminación de variables inalcanzables",
            "Estas variables no se pueden alcanzar desde el símbolo inicial, por lo "
            "que se eliminan sin cambiar el lenguaje generado.",
            [f"Eliminadas: {', '.join(unreachable)}"],
            highlight=unreachable,
        )

    def _restore_epsilon_rule(self) -> None:
        if not self._has_epsilon_start:
            return
        start = self.grammar.start
        self.grammar.set_productions(start, [()] + list(self.grammar.productions_of(start)))
        self._log(
            "epsilon",
            "Limpieza",
            f"Se restaura {start} -> ε",
            f"{start} no aparece en ninguna parte derecha, por lo que {start} -> ε es "
            "admisible también en FNG.",
            highlight=[start],
        )

    def _final_validation(self) -> None:
        errors = check_gnf(self.grammar)
        self.history.gnf_errors = list(errors)
        if errors:
            self._log(
                "validation",
                "Validación final",
                "La gramática final NO cumple la FNG",
                "Se encontraron producciones que no tienen la forma A -> a A1...An.",
                errors,
            )
        else:
            count = sum(len(b) for b in self.grammar.productions.values())
            self._log(
                "validation",
                "Validación final",
                "Validación FNG exitosa",
                "Toda producción tiene la forma A -> a A1 A2 ... An (n ≥ 0): comienza "
                "con un terminal seguido únicamente de variables.",
                [f"{count} producciones verificadas."],
            )

        result, lang_a, lang_b = equivalent_up_to(self.original, self.grammar)
        if result is None:
            message, ok = (
                "No se pudo comprobar la equivalencia (demasiadas cadenas).",
                True,
            )
        elif result:
            message, ok = (
                f"La gramática original y la final generan exactamente las mismas "
                f"{len(lang_a)} cadenas de longitud ≤ {DEFAULT_MAX_LENGTH}.",
                True,
            )
        else:
            only_a = sorted(lang_a - lang_b)[:5]
            only_b = sorted(lang_b - lang_a)[:5]
            message, ok = (
                "¡Las gramáticas NO son equivalentes! "
                f"Solo en la original: {only_a}; solo en la final: {only_b}.",
                False,
            )
            self.history.gnf_errors.append(message)
        self._log(
            "equivalence",
            "Validación final",
            "Verificación de equivalencia" if ok else "Equivalencia fallida",
            message,
        )


def convert_to_gnf(grammar: Grammar, remove_unreachable: bool = True) -> History:
    """Convierte ``grammar`` (en FNC) a FNG y devuelve el historial completo."""
    return FngConverter(grammar, remove_unreachable).run()
