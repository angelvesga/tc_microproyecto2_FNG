"""Pruebas del núcleo: parser, validador y conversión FNC -> FNG."""

import glob
import os
import unittest

from fng.converter import ConversionError, convert_to_gnf
from fng.equivalence import equivalent_up_to
from fng.parser import parse_file_text, parse_grammar
from fng.validator import check_cnf, check_gnf, validate_input

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "examples")


def grammar_from(variables, terminals, start, productions):
    result = parse_grammar(variables, terminals, start, productions)
    assert not result.errors, result.errors
    return result.grammar


class ValidationTests(unittest.TestCase):
    def test_missing_elements(self):
        errors = validate_input(grammar_from("", "", "", "A -> a"))
        self.assertGreaterEqual(len(errors), 3)

    def test_start_not_in_variables(self):
        errors = validate_input(grammar_from("A", "a", "S", "A -> a"))
        self.assertTrue(any("no pertenece" in e for e in errors))

    def test_undeclared_symbol(self):
        errors = validate_input(grammar_from("S", "a", "S", "S -> a x"))
        self.assertTrue(any("no declarados" in e for e in errors))

    def test_not_cnf(self):
        g = grammar_from("S A", "a b", "S", "S -> a A\nA -> a b\nS -> A")
        self.assertEqual(len(check_cnf(g)), 3)

    def test_epsilon_only_if_start_not_on_right(self):
        ok = grammar_from("S A", "a", "S", "S -> ε | A A\nA -> a")
        self.assertEqual(check_cnf(ok), [])
        bad = grammar_from("S A", "a", "S", "S -> ε | S A\nA -> a")
        self.assertTrue(check_cnf(bad))

    def test_duplicate_productions_ignored(self):
        result = parse_grammar("S", "a", "S", "S -> a | a")
        self.assertEqual(result.grammar.productions_of("S"), [("a",)])
        self.assertTrue(result.warnings)

    def test_compact_notation(self):
        g = grammar_from("S A B", "a b", "S", "S -> AB\nA -> a\nB -> b")
        self.assertEqual(g.productions_of("S"), [("A", "B")])

    def test_syntax_error_message(self):
        result = parse_grammar("S", "a", "S", "S a")
        self.assertTrue(result.errors and "flecha" in result.errors[0])


class ConversionTests(unittest.TestCase):
    def assert_converts(self, grammar):
        history = convert_to_gnf(grammar)
        self.assertEqual(history.gnf_errors, [])
        self.assertEqual(check_gnf(history.final_grammar), [])
        same, _, _ = equivalent_up_to(grammar, history.final_grammar, 7)
        self.assertTrue(same)
        for head, bodies in history.final_grammar.productions.items():
            self.assertEqual(len(bodies), len(set(bodies)), f"duplicados en {head}")
        return history

    def test_all_examples(self):
        files = sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.txt")))
        self.assertGreaterEqual(len(files), 5)
        for path in files:
            with open(path, encoding="utf-8") as handle:
                f = parse_file_text(handle.read())
            g = grammar_from(f["variables"], f["terminals"], f["start"], f["productions"])
            with self.subTest(example=os.path.basename(path)):
                self.assert_converts(g)

    def test_direct_left_recursion_creates_auxiliary(self):
        g = grammar_from("S A", "a b", "S", "S -> S A | a\nA -> b")
        history = self.assert_converts(g)
        # Variable auxiliar Xi.1 de la guía (S queda enumerada como X1).
        self.assertIn("X1.1", history.final_grammar.variables)
        self.assertTrue(any(s.kind == "left_recursion" for s in history.steps))

    def test_enumeration_avoids_terminal_names(self):
        g = grammar_from("S A", "a X1", "S", "S -> S A | a\nA -> X1")
        history = self.assert_converts(g)
        final = history.final_grammar
        self.assertEqual(len(set(final.variables)), len(final.variables))
        self.assertFalse(set(final.variables) & set(final.terminals))
        self.assertIn("V1.1", final.variables)

    def test_epsilon_is_preserved(self):
        g = grammar_from("S A B", "a b", "S", "S -> ε | A B\nA -> A B | a\nB -> b")
        history = self.assert_converts(g)
        final = history.final_grammar
        self.assertIn((), final.productions_of(final.start))

    def test_deterministic_history(self):
        g = grammar_from("S A B", "a b", "S", "S -> A B\nA -> B S | a\nB -> S A | b")
        first = convert_to_gnf(g).to_text()
        second = convert_to_gnf(g).to_text()
        self.assertEqual(first, second)

    def test_non_cnf_input_is_normalized(self):
        g = grammar_from("S", "a", "S", "S -> a a")
        self.assert_converts(g)


class CleanupTests(unittest.TestCase):
    """Depuración de GLC generales antes de pasar a FNC y FNG."""

    assert_converts = ConversionTests.assert_converts

    def kinds(self, history):
        return [s.kind for s in history.steps]

    def test_unit_cycle(self):
        g = grammar_from("S A B", "a b", "S", "S -> A | a S\nA -> B | b\nB -> A | a")
        history = self.assert_converts(g)
        self.assertIn("unit", self.kinds(history))

    def test_nullable_chain(self):
        g = grammar_from("S A B C", "a b", "S", "S -> A B C a\nA -> B | ε\nB -> C\nC -> ε | b")
        self.assert_converts(g)

    def test_epsilon_with_start_on_right_uses_new_start(self):
        g = grammar_from("S", "a b", "S", "S -> a S b | ε")
        history = self.assert_converts(g)
        self.assertEqual(history.cnf_grammar["start"], "S0")
        final = history.final_grammar
        self.assertIn((), final.productions_of(final.start))
        self.assertFalse(final.start_appears_in_bodies())

    def test_useless_and_unreachable_removed(self):
        g = grammar_from("S A D E", "a b", "S", "S -> a A | D b\nA -> b\nD -> a D\nE -> a")
        history = self.assert_converts(g)
        self.assertNotIn("D", history.final_grammar.variables)
        self.assertNotIn("E", history.final_grammar.variables)
        first_cleanup = next(s for s in history.steps if s.kind == "cleanup")
        self.assertIn("D", first_cleanup.details[1])  # Variables no generadoras

    def test_empty_language_is_rejected(self):
        g = grammar_from("S A", "a", "S", "S -> a S | A\nA -> A a")
        with self.assertRaises(ConversionError):
            convert_to_gnf(g)

    def test_terminals_in_long_bodies(self):
        g = grammar_from("S", "a b c", "S", "S -> a S b c | c")
        self.assert_converts(g)

    def test_name_collisions(self):
        g = grammar_from(
            "S S0 T1 X1", "a b", "S",
            "S -> a S b | S0 | ε\nS0 -> T1 X1\nT1 -> a | b\nX1 -> b",
        )
        history = self.assert_converts(g)
        final = history.final_grammar
        self.assertEqual(len(final.variables), len(set(final.variables)))
        self.assertNotEqual(final.start, "S0")

    def test_terminal_variables_are_numbered(self):
        g = grammar_from("S", "a b", "S", "S -> a S b | a b")
        history = convert_to_gnf(g)
        cnf_heads = {p["head"]: p["bodies"] for p in history.cnf_grammar["productions"]}
        # Como en la guía: A1 -> a, B1 -> b para terminales y Y1, Y2, ... para largas.
        self.assertEqual(cnf_heads.get("A1"), ["a"])
        self.assertEqual(cnf_heads.get("B1"), ["b"])
        self.assertEqual(cnf_heads.get("Y1"), ["S B1"])
        self.assertEqual(cnf_heads.get("S"), ["A1 Y1", "A1 B1"])

    def test_cnf_stages_follow_the_guide(self):
        g = grammar_from("S A", "a b", "S", "S -> A S A | a b | ε\nA -> S | a")
        history = convert_to_gnf(g)
        stages = [s.title for s in history.steps if s.phase == "fnc"]
        self.assertEqual(
            stages,
            [
                "Eliminación de símbolos no generadores",
                "Eliminación de símbolos no alcanzables",
                "Eliminación de producciones ε",
                "Eliminación de producciones unitarias",
                "Reemplazar terminales por variables",
                "Reemplazar producciones de 3 o más variables",
                "Gramática en Forma Normal de Chomsky",
            ],
        )
        cnf = {p["head"]: p["bodies"] for p in history.cnf_grammar["productions"]}
        self.assertEqual(history.cnf_grammar["start"], "S0")
        self.assertIn("ε", cnf["S0"])

    def test_guide_exercise(self):
        """Ejercicio de guia_FNC_FNG.pdf: misma FNC (pág. 4) y misma enumeración (pág. 5)."""
        g = grammar_from(
            "S A B C D E F G", "a b c d", "S",
            "S -> A | B C a | a D c d | E D F\nA -> a A b | c\n"
            "B -> C D | b | E C d | A d\nC -> C c | B b | A a E | ε\n"
            "D -> a D d | D d | ε\nE -> a a E B | E F G\nF -> a F d | d",
        )
        history = self.assert_converts(g)
        cnf = {p["head"]: " | ".join(p["bodies"]) for p in history.cnf_grammar["productions"]}
        self.assertEqual(cnf, {
            "S": "A1 Y1 | c | B Y2 | B A1 | C A1 | a | A1 Y3 | A1 Y4",
            "Y1": "A B1", "Y2": "C A1", "Y3": "D Y4", "Y4": "C1 D1",
            "A": "A1 Y1 | c",
            "B": "C D | C C1 | c | B B1 | b | A1 Y5 | A1 D1 | D D1 | d | A D1",
            "Y5": "D D1",
            "C": "C C1 | c | B B1 | b",
            "D": "A1 Y5 | A1 D1 | D D1 | d",
            "A1": "a", "B1": "b", "C1": "c", "D1": "d",
        })
        order = next(s for s in history.steps if s.kind == "order")
        self.assertEqual(
            order.details[:14],
            [f"X{i} = {v}" + (" (símbolo inicial)" if i == 1 else "") for i, v in enumerate(
                "S Y1 Y2 Y3 Y4 B Y5 C D A A1 B1 C1 D1".split(), start=1)],
        )
        aux = {v for v in history.final_grammar.variables if "." in v}
        self.assertTrue({"X6.1", "X8.1", "X9.1"} <= aux)

    def test_large_grammar_fails_cleanly(self):
        from unittest import mock

        g = grammar_from("S A B", "a b", "S", "S -> A B | a\nA -> B S | b\nB -> S A | a")
        with mock.patch("fng.converter.MAX_TOTAL_PRODUCTIONS", 12):
            with self.assertRaises(ConversionError) as caught:
                convert_to_gnf(g)
        self.assertIn("demasiado", caught.exception.messages[0])

    def test_indirect_for_all_variables_before_immediate(self):
        """Fase 1 (indirecta) en todas las variables antes de la fase 2 (inmediata)."""
        g = grammar_from("S A B", "a b", "S", "S -> A B | a\nA -> B S | b\nB -> S A | a")
        history = self.assert_converts(g)
        stages = [s.stage for s in history.steps if s.stage.startswith("Fase ")]
        first_phase2 = next(i for i, st in enumerate(stages) if st.startswith("Fase 2"))
        self.assertTrue(all(st.startswith("Fase 1") for st in stages[:first_phase2]))
        self.assertTrue(all(st.startswith("Fase 2") for st in stages[first_phase2:]))
        for name in ("X1", "X2", "X3"):
            for phase in ("Fase 1", "Fase 2"):
                self.assertTrue(any(st.startswith(phase) and f" · {name} (" in st for st in stages))

    def test_immediate_brought_forward_only_when_needed(self):
        # En la guía, X8 -> X6 X12 necesita a X6, que tiene X6 -> X6 X12.
        g = grammar_from(
            "S A B C D E F G", "a b c d", "S",
            "S -> A | B C a | a D c d | E D F\nA -> a A b | c\n"
            "B -> C D | b | E C d | A d\nC -> C c | B b | A a E | ε\n"
            "D -> a D d | D d | ε\nE -> a a E B | E F G\nF -> a F d | d",
        )
        history = self.assert_converts(g)
        early = [s for s in history.steps
                 if s.kind == "left_recursion" and s.stage.startswith("Fase 1")]
        self.assertEqual([s.title.split(":")[0] for s in early],
                         ["Eliminación de recursividad izquierda en X6"])
        later = [s.title for s in history.steps
                 if s.kind == "left_recursion" and s.stage.startswith("Fase 2")]
        self.assertEqual(len(later), 2)  # X8 y X9

    def test_equivalence_handles_epsilon_and_unit_cycles(self):
        g = grammar_from("S A", "a", "S", "S -> A | ε\nA -> S | a")
        same, lang, _ = equivalent_up_to(g, g, 3)
        self.assertTrue(same)
        self.assertEqual(lang, {"", "a"})


class ProgressTests(unittest.TestCase):
    """Avance que se muestra mientras el algoritmo corre."""

    GRAMMAR = ("S A B", "a b", "S", "S -> A B | a S b | ε\nA -> B S | a\nB -> S A | b")

    def test_progress_is_monotonic_and_complete(self):
        events = []
        history = convert_to_gnf(grammar_from(*self.GRAMMAR), on_progress=events.append)
        fractions = [e["fraction"] for e in events]
        self.assertEqual(fractions, sorted(fractions))
        self.assertEqual(fractions[-1], 1.0)
        reported = [e["step"]["number"] for e in events if e["step"]]
        self.assertEqual(reported, [s.number for s in history.steps])
        self.assertTrue(any("equivalencia" in e["activity"] for e in events))

    def test_callback_can_cancel(self):
        class Stop(Exception):
            pass

        def stop_in_greibach(event):
            if event["phase"] == "fng":
                raise Stop()

        with self.assertRaises(Stop):
            convert_to_gnf(grammar_from(*self.GRAMMAR), on_progress=stop_in_greibach)


class ParserPerformanceTests(unittest.TestCase):
    def test_segmentation_is_not_exponential(self):
        import time

        start = time.perf_counter()
        result = parse_grammar("S", "a aa", "S", "S -> " + "a" * 200 + "b")
        self.assertLess(time.perf_counter() - start, 0.5)
        self.assertEqual(result.grammar.productions_of("S"), [("a" * 200 + "b",)])

    def test_segmentation_prefers_longest(self):
        g = grammar_from("S", "a aa", "S", "S -> aaa")
        self.assertEqual(g.productions_of("S"), [("aa", "a")])


if __name__ == "__main__":
    unittest.main()
