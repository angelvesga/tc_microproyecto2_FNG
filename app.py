"""Aplicación web (Flask): GLC -> depuración -> FNC -> FNG, paso a paso.

Endpoints:
  GET  /                 Interfaz web.
  GET  /api/examples     Gramáticas de ejemplo (campos de entrada).
  POST /api/validate     Valida los datos de entrada (e informa si ya está en FNC).
  POST /api/convert      Devuelve el historial completo de la conversión.
  POST /api/convert-stream  Igual, pero envía el avance paso a paso (NDJSON).
"""

import glob
import json
import os
import queue
import threading

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

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
    """Errores de estructura (lista vacía = válida). No se exige FNC: se depura."""
    return list(parsed.errors) + validate_input(parsed.grammar)


def as_bool(value, default=True):
    """Interpreta booleanos de JSON aceptando también cadenas ("false", "0")."""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "off", "")
    return bool(value)


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
    is_cnf = not errors and not check_cnf(parsed.grammar)
    return jsonify(
        {"ok": not errors, "errors": errors, "warnings": parsed.warnings, "is_cnf": is_cnf}
    )


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
        history = convert_to_gnf(parsed.grammar, as_bool(data.get("remove_unreachable")))
    except ConversionError as error:
        return jsonify({"ok": False, "errors": error.messages})
    return jsonify({"ok": True, "warnings": parsed.warnings, **history.to_dict()})


class ConversionCancelled(Exception):
    """El cliente cerró la conexión: se detiene la conversión en curso."""


@app.post("/api/convert-stream")
def convert_stream():
    """Igual que /api/convert, pero envía el avance mientras el algoritmo corre.

    La respuesta es NDJSON (un objeto JSON por línea):
      {"type": "progress", "fraction", "activity", "phase", "steps", "step"}
      ...
      {"type": "result", "ok": true, ...historial}   o   {"type": "error", "errors": [...]}
    """
    parsed, format_errors = read_grammar_from_request()
    if format_errors:
        return jsonify({"ok": False, "errors": format_errors}), 400
    errors = analyse(parsed)
    if errors:
        return jsonify({"ok": False, "errors": errors, "warnings": parsed.warnings})
    data = request.get_json(silent=True) or {}
    remove_unreachable = as_bool(data.get("remove_unreachable"))

    events: "queue.Queue[dict]" = queue.Queue()
    cancelled = threading.Event()

    def on_progress(event):
        if cancelled.is_set():
            raise ConversionCancelled()
        events.put({"type": "progress", **event})

    def work():
        try:
            history = convert_to_gnf(parsed.grammar, remove_unreachable, on_progress)
            events.put({"type": "result", "ok": True, "warnings": parsed.warnings, **history.to_dict()})
        except ConversionCancelled:
            events.put({"type": "cancelled"})
        except ConversionError as error:
            events.put({"type": "error", "ok": False, "errors": error.messages})
        except Exception:  # pragma: no cover - error inesperado
            app.logger.exception("Error inesperado en la conversión")
            events.put({"type": "error", "ok": False, "errors": ["Error inesperado en el servidor."]})

    def generate():
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        try:
            while True:
                event = events.get()
                yield json.dumps(event, ensure_ascii=False) + "\n"
                if event["type"] != "progress":
                    break
        finally:
            # Si el cliente se desconecta, la próxima llamada de progreso cancela el trabajo.
            cancelled.set()

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
