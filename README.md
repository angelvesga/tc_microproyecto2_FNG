# Conversor FNC → FNG paso a paso (Microproyecto #2)

Aplicación web (Python + Flask) que valida una gramática en Forma Normal de Chomsky y la convierte
a Forma Normal de Greibach, mostrando cada sustitución, la eliminación de recursividad izquierda,
las variables auxiliares, las gramáticas intermedias y la validación final.

## Ejecutar en local
```
pip install -r requirements.txt
python app.py          # http://localhost:5000
python -m unittest discover -s tests -t .
```

## Estructura
- `fng/` núcleo (sin dependencias): `grammar`, `parser`, `validator`, `converter`, `history`, `equivalence`, `formatting`
- `app.py` API Flask (`/api/validate`, `/api/convert`, `/api/examples`, `/api/parse-file`)
- `templates/`, `static/` interfaz web (modo automático y modo "Siguiente paso")
- `examples/` gramáticas de ejemplo · `tests/` pruebas

## Despliegue en Render
Conectar el repositorio como *Web Service* (o usar `render.yaml`):
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app --bind 0.0.0.0:$PORT`
