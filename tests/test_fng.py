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
        self.assertIn("Z1", history.final_grammar.variables)
        self.assertTrue(any(s.kind == "left_recursion" for s in history.steps))

    def test_auxiliary_name_avoids_collisions(self):
        g = grammar_from("S A Z1", "a b", "S", "S -> S A | a\nA -> b\nZ1 -> a")
        history = self.assert_converts(g)
        self.assertEqual(len(set(history.final_grammar.variables)), len(history.final_grammar.variables))
        self.assertIn("Z1_2", history.final_grammar.variables)

    def test_epsilon_is_preserved(self):
        g = grammar_from("S A B", "a b", "S", "S -> ε | A B\nA -> A B | a\nB -> b")
        history = self.assert_converts(g)
        self.assertIn((), history.final_grammar.productions_of("S"))

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
        final = history.final_grammar
        self.assertEqual(final.start, "S0")
        self.assertIn((), final.productions_of("S0"))
        self.assertFalse(final.start_appears_in_bodies())

    def test_useless_and_unreachable_removed(self):
        g = grammar_from("S A D E", "a b", "S", "S -> a A | D b\nA -> b\nD -> a D\nE -> a")
        history = self.assert_converts(g)
        self.assertNotIn("D", history.final_grammar.variables)
        self.assertNotIn("E", history.final_grammar.variables)
        first_cleanup = next(s for s in history.steps if s.kind == "cleanup")
        self.assertIn("D", first_cleanup.details[0])

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
        self.assertEqual(cnf_heads.get("T1"), ["a"])
        self.assertEqual(cnf_heads.get("T2"), ["b"])

    def test_large_grammar_fails_cleanly(self):
        from unittest import mock

        g = grammar_from("S A B", "a b", "S", "S -> A B | a\nA -> B S | b\nB -> S A | a")
        with mock.patch("fng.converter.MAX_TOTAL_PRODUCTIONS", 12):
            with self.assertRaises(ConversionError) as caught:
                convert_to_gnf(g)
        self.assertIn("demasiado", caught.exception.messages[0])

    def test_indirect_before_direct_for_each_variable(self):
        g = grammar_from("S A", "a b", "S", "S -> A S | b\nA -> S A | a")
        history = self.assert_converts(g)
        for name in ("S", "A"):
            stages = [s.stage for s in history.steps if s.stage.startswith(name + " (")]
            self.assertTrue(stages)
            first_direct = next(i for i, st in enumerate(stages) if "inmediata" in st)
            self.assertTrue(all("indirecta" in st for st in stages[:first_direct]))
            self.assertTrue(all("inmediata" in st for st in stages[first_direct:]))

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
