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

    def test_rejects_non_cnf(self):
        g = grammar_from("S", "a", "S", "S -> a a")
        with self.assertRaises(ConversionError):
            convert_to_gnf(g)


if __name__ == "__main__":
    unittest.main()
