"""Errores comprensibles del proceso de conversión."""

from __future__ import annotations

from typing import List


class ConversionError(Exception):
    """La gramática de entrada no puede convertirse (con mensajes comprensibles)."""

    def __init__(self, messages: List[str]) -> None:
        super().__init__("\n".join(messages))
        self.messages = messages
