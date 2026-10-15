"""Historial de la conversión: cada operación queda registrada (RNF09, RNF10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .formatting import format_grammar, format_productions
from .grammar import Grammar, format_body


def grammar_snapshot(grammar: Grammar) -> Dict:
    """Copia serializable de la gramática en un instante dado."""
    return {
        "variables": list(grammar.variables),
        "terminals": list(grammar.terminals),
        "start": grammar.start,
        "productions": [
            {"head": head, "bodies": [format_body(b) for b in grammar.productions_of(head)]}
            for head in grammar.heads_in_order()
            if grammar.productions_of(head)
        ],
        "text": format_productions(grammar),
    }


@dataclass
class Step:
    """Una acción del algoritmo, con la gramática resultante tras ejecutarla."""

    kind: str
    title: str
    description: str
    details: List[str] = field(default_factory=list)
    stage: str = ""
    highlight: List[str] = field(default_factory=list)  # variables afectadas
    grammar: Optional[Dict] = None
    number: int = 0

    def to_dict(self) -> Dict:
        return {
            "number": self.number,
            "kind": self.kind,
            "stage": self.stage,
            "title": self.title,
            "description": self.description,
            "details": self.details,
            "highlight": self.highlight,
            "grammar": self.grammar,
        }

    def to_text(self) -> str:
        lines = [f"Paso {self.number}: {self.title}", f"  {self.description}"]
        lines += [f"  - {d}" for d in self.details]
        if self.grammar:
            lines.append("  Gramática resultante:")
            lines += [f"    {l}" for l in self.grammar["text"].splitlines()]
        return "\n".join(lines)


@dataclass
class History:
    """Lista ordenada de pasos más el resultado final de la conversión."""

    steps: List[Step] = field(default_factory=list)
    final_grammar: Optional[Grammar] = None
    gnf_errors: List[str] = field(default_factory=list)

    def add(self, step: Step, grammar: Grammar) -> Step:
        step.number = len(self.steps) + 1
        step.grammar = grammar_snapshot(grammar)
        self.steps.append(step)
        return step

    @property
    def is_gnf(self) -> bool:
        return self.final_grammar is not None and not self.gnf_errors

    def to_dict(self) -> Dict:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "is_gnf": self.is_gnf,
            "gnf_errors": self.gnf_errors,
            "final": grammar_snapshot(self.final_grammar) if self.final_grammar else None,
        }

    def to_text(self) -> str:
        parts = [s.to_text() for s in self.steps]
        if self.final_grammar:
            parts.append("GRAMÁTICA FINAL (FNG)\n" + format_grammar(self.final_grammar))
        return "\n\n".join(parts)
