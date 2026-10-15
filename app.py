"""Aplicación web (Flask) para convertir gramáticas de FNC a FNG paso a paso.

Endpoints:
  GET  /                 Interfaz web.
  GET  /api/examples     Gramáticas de ejemplo (campos de entrada).
  POST /api/validate     Valida los datos de entrada y la Forma Normal de Chomsky.
  POST /api/convert      Devuelve el historial completo de la conversión.
"""

import glob
import os

from flask import Flask, jsonify, render_template, request

from fng.converter import ConversionError, convert_to_gnf
from fng.parser import parse_file_text, parse_grammar
from fng.validator import check_cnf, validate_input

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXAMPLES_DIR = os.path.join(BASE_DIR, "examples")
MAX_FIELD_LENGTH = 20000

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024


def read_grammar_from_request():
    """Interpreta el JSON recibido. Devuelve (resultado_parseo, errores_de_formato)."""
    data = request.get_json(silent=True) or {}
    fields = {k: str(data.get(k, "")) for k in ("variables", "terminals", "start", "productions")}
    if any(len(v) > MAX_FIELD_LENGTH for v in fields.values()):
        return None, ["La entrada es demasiado grande."]
    parsed = parse_grammar(
        fields["variables"], fields["terminals"], fields["start"], fields["productions"]
    )
    return parsed, []


def analyse(parsed):
    """Errores de estructura y de FNC (lista vacía = válida)."""
    errors = list(parsed.errors) + validate_input(parsed.grammar)
    if not errors:
        errors += check_cnf(parsed.grammar)
    return errors


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/examples")
def examples():
    items = []
    for path in sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.txt"))):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        name = os.path.splitext(os.path.basename(path))[0]
        title = name.split("_", 1)[-1].replace("_", " ").capitalize()
        items.append({"title": title, **parse_file_text(text)})
    return jsonify(items)


@app.post("/api/parse-file")
def parse_file():
    text = str((request.get_json(silent=True) or {}).get("text", ""))
    return jsonify(parse_file_text(text[:MAX_FIELD_LENGTH]))


@app.post("/api/validate")
def validate():
    parsed, format_errors = read_grammar_from_request()
    if format_errors:
        return jsonify({"ok": False, "errors": format_errors}), 400
    errors = analyse(parsed)
    return jsonify({"ok": not errors, "errors": errors, "warnings": parsed.warnings})


@app.post("/api/convert")
def convert():
    parsed, format_errors = read_grammar_from_request()
    if format_errors:
        return jsonify({"ok": False, "errors": format_errors}), 400
    errors = analyse(parsed)
    if errors:
        return jsonify({"ok": False, "errors": errors, "warnings": parsed.warnings})
    data = request.get_json(silent=True) or {}
    try:
        history = convert_to_gnf(parsed.grammar, bool(data.get("remove_unreachable", True)))
    except ConversionError as error:
        return jsonify({"ok": False, "errors": error.messages})
    return jsonify({"ok": True, "warnings": parsed.warnings, **history.to_dict()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
