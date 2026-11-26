# Conversor GLC → FNC → FNG paso a paso (Microproyecto #2)

Aplicación web (Python + Flask) que recibe **cualquier gramática libre de contexto** (no se asume que
esté depurada ni en Forma Normal de Chomsky) y la convierte a Forma Normal de Greibach, mostrando
cada operación y la gramática intermedia tras cada paso:

El proceso sigue la guía del curso (*Ejercicio guía para obtener FNC y FNG* y las diapositivas de
*Forma Normal de Greibach*); con el ejercicio de la guía se obtiene exactamente su misma FNC y su
misma enumeración X1…X14.

**Forma intermedia de Chomsky**

1. **Símbolos no generadores** y luego **no alcanzables** (variables y terminales).
2. **Producciones ε**: con las variables anulables se generan todas las combinaciones (a lo más 2^n).
   Si ε pertenece al lenguaje se conserva: `S0 -> S | ε` si S aparece a la derecha, o `S -> ε` si no.
3. **Producciones unitarias** con pares unitarios; cada `A -> B` se reemplaza en su lugar por las
   producciones no unitarias de B. (Si después quedan símbolos inútiles, se eliminan otra vez.)

**Forma Normal de Chomsky**

4. **Reemplazar terminales por variables**: `A1 -> a`, `B1 -> b`, … (`T1`, `T2`, … si el terminal no es letra).
5. **Reemplazar producciones de 3 o más variables**: `Y -> X α` pasa a `Y -> X Y1` con `Y1 -> α`.

**Forma Normal de Greibach**

6. **Ordenar y enumerar** las variables `X1…Xn` con el inicial como `X1`; cada `Yk` va tras la variable
   que la originó y las variables de terminales al final. Como hace la guía con A, se baja al final
   una variable cuando así quedan menos producciones `Xi -> Xj α` con i > j.
7. **Fase 1, recursividad indirecta en todas las variables**: en cada `Xi` se eliminan las
   producciones `Xi -> Xj α` con j < i sustituyendo `Xj`. Si `Xj` todavía tiene recursividad
   inmediata, a esa variable se le quita antes (la sustitución no terminaría y el atajo de la guía
   perdería cadenas); el paso lo explica.
   **Fase 2, recursividad inmediata en todas las variables**, con la variable auxiliar `Xi.1`:
   `Xi -> β | β Xi.1`, `Xi.1 -> α | α Xi.1`.
8. **Reemplazar de la última variable a la primera** las producciones que empiezan con variable
   (y luego en las `Xi.1`).
9. Validación FNG y verificación de equivalencia con la gramática ingresada (cadenas de longitud ≤ 6).

> En la guía, la recursión entre dos variables se quita sustituyendo solo las producciones "no
> recursivas" de la otra. Ese atajo cambia el lenguaje (en su propio ejercicio se pierde `ccda`, entre
> otras), por eso en la fase 1 se usa el orden X1 < X2 < … para sustituir y, si hace falta, se
> adelanta la recursividad inmediata de la variable que se va a sustituir.

Las gramáticas que crecen demasiado durante la conversión se rechazan con un mensaje claro
(límites en `fng/converter.py`) para no agotar la memoria del servidor.

## Ejecutar en local
```
pip install -r requirements.txt
python app.py          # http://localhost:5000
python -m unittest discover -s tests -t .
```

## Estructura
- `fng/` núcleo (sin dependencias): `grammar`, `parser`, `validator`, `cleanup` (depuración y FNC según la guía), `converter` (FNG), `history`, `equivalence`, `formatting`, `errors`
- `app.py` API Flask (`/api/validate`, `/api/convert`, `/api/convert-stream`, `/api/examples`, `/api/parse-file`).
  `/api/convert-stream` envía el avance mientras el algoritmo corre (NDJSON: una línea por evento), que la
  interfaz muestra como barra de progreso, actividad actual, tiempo restante estimado y últimos pasos.
- `templates/`, `static/` interfaz web (modo automático y modo "Siguiente paso")
- `examples/` gramáticas de ejemplo · `tests/` pruebas

## Despliegue en Render
Conectar el repositorio como *Web Service* (o usar `render.yaml`):
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app --bind 0.0.0.0:$PORT`
