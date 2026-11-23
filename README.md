# Conversor GLC → FNC → FNG paso a paso (Microproyecto #2)

Aplicación web (Python + Flask) que recibe **cualquier gramática libre de contexto** (no se asume que
esté depurada ni en Forma Normal de Chomsky) y la convierte a Forma Normal de Greibach, mostrando
cada operación y la gramática intermedia tras cada paso:

1. **Depuración inicial:** variables no generadoras (inútiles) y luego inalcanzables.
2. **Nuevo símbolo inicial** `S0 -> S`, si S genera ε y aparece a la derecha.
3. **Producciones nulas** (`A -> ε`), conservando `S -> ε` si ε pertenece al lenguaje.
4. **Producciones unitarias** (`A -> B`), con clausura (admite ciclos).
5. **Depuración final** (inútiles e inalcanzables otra vez).
6. **Forma Normal de Chomsky:** terminales en producciones largas (`T1 -> a`, `T2 -> b`, …) y división en `X_i`.
7. **Forma Normal de Greibach**, para cada variable Ai en orden: primero la **recursividad
   indirecta** (sustituir `Ai -> Aj γ` con j < i) y luego la **recursividad inmediata**
   (`Ai -> Ai α`, nueva variable `Zi`); después, la sustitución hacia atrás y la sustitución en las `Zi`.
8. Validación FNG y verificación de equivalencia con la gramática ingresada (cadenas de longitud ≤ 6).

Las gramáticas que crecen demasiado durante la conversión se rechazan con un mensaje claro
(límites en `fng/converter.py`) para no agotar la memoria del servidor.

## Ejecutar en local
```
pip install -r requirements.txt
python app.py          # http://localhost:5000
python -m unittest discover -s tests -t .
```

## Estructura
- `fng/` núcleo (sin dependencias): `grammar`, `parser`, `validator`, `cleanup` (depuración y FNC), `converter` (FNG), `history`, `equivalence`, `formatting`, `errors`
- `app.py` API Flask (`/api/validate`, `/api/convert`, `/api/examples`, `/api/parse-file`)
- `templates/`, `static/` interfaz web (modo automático y modo "Siguiente paso")
- `examples/` gramáticas de ejemplo · `tests/` pruebas

## Despliegue en Render
Conectar el repositorio como *Web Service* (o usar `render.yaml`):
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app --bind 0.0.0.0:$PORT`
