"use strict";

const $ = (id) => document.getElementById(id);
const FIELDS = ["variables", "terminals", "start", "productions"];
let result = null; // respuesta de /api/convert
let shown = 0;     // cantidad de pasos visibles

function readInput() {
  const data = {};
  FIELDS.forEach((f) => (data[f] = $(f).value));
  data.remove_unreachable = $("remove-unreachable").checked;
  return data;
}

function fillInput(values) {
  FIELDS.forEach((f) => ($(f).value = values[f] || ""));
  clearMessages();
  $("result-card").classList.add("hidden");
  result = null;
}

function clearMessages() {
  $("messages").replaceChildren();
}

function showMessage(kind, text, items) {
  const box = document.createElement("div");
  box.className = "msg " + kind;
  box.textContent = text;
  if (items && items.length) {
    const list = document.createElement("ul");
    items.forEach((t) => {
      const li = document.createElement("li");
      li.textContent = t;
      list.append(li);
    });
    box.append(list);
  }
  $("messages").append(box);
}

async function post(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return response.json();
}

function reportErrors(data) {
  showMessage("error", "La gramática no es válida. Corrija lo siguiente:", data.errors);
  (data.warnings || []).forEach((w) => showMessage("warn", w));
}

async function validate() {
  clearMessages();
  const data = await post("/api/validate", readInput());
  if (!data.ok) return reportErrors(data);
  showMessage(
    "ok",
    data.is_cnf
      ? "✔ La gramática es válida y ya está en Forma Normal de Chomsky (igual se depurará)."
      : "✔ La gramática es válida. No está en FNC: se depurará y se llevará a FNC antes de convertirla a FNG."
  );
  (data.warnings || []).forEach((w) => showMessage("warn", w));
}

async function convert(stepByStep) {
  clearMessages();
  const data = await post("/api/convert", readInput());
  if (!data.ok) {
    $("result-card").classList.add("hidden");
    return reportErrors(data);
  }
  (data.warnings || []).forEach((w) => showMessage("warn", w));
  result = data;
  openPhases.clear();
  shown = stepByStep ? 1 : data.steps.length;
  $("result-card").classList.remove("hidden");
  render();
  $("result-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

/**
 * Dibuja una gramática. Si se pasa ``previous`` (la gramática del paso
 * anterior), resalta las alternativas nuevas y devuelve cuántas se agregaron
 * y cuántas desaparecieron.
 */
function renderGrammar(target, grammar, highlight, previous) {
  target.replaceChildren();
  const before = new Map();
  if (previous) previous.productions.forEach((p) => before.set(p.head, new Set(p.bodies)));
  let added = 0;
  let removed = 0;
  if (previous) {
    const now = new Map(grammar.productions.map((p) => [p.head, new Set(p.bodies)]));
    before.forEach((bodies, head) => bodies.forEach((b) => {
      if (!now.has(head) || !now.get(head).has(b)) removed++;
    }));
  }

  grammar.productions.forEach((p) => {
    const line = document.createElement("span");
    line.className = "rule" + (highlight && highlight.includes(p.head) ? " hl" : "");
    const old = before.get(p.head);
    const head = document.createElement("span");
    head.className = "head";
    head.textContent = p.head;
    const arrow = document.createElement("span");
    arrow.className = "arrow";
    arrow.textContent = " → ";
    line.append(head, arrow);
    p.bodies.forEach((body, i) => {
      if (i) {
        const bar = document.createElement("span");
        bar.className = "bar";
        bar.textContent = " | ";
        line.append(bar);
      }
      const isNew = previous && (!old || !old.has(body));
      if (isNew) {
        added++;
        const mark = document.createElement("mark");
        mark.className = "new";
        mark.textContent = body;
        line.append(mark);
      } else {
        line.append(body);
      }
    });
    line.append("\n");
    target.append(line);
  });
  return { added, removed };
}

function describeDiff({ added, removed }) {
  const legend = $("diff-legend");
  legend.replaceChildren();
  if (!added && !removed) {
    legend.textContent = "Sin cambios en las producciones.";
    return;
  }
  const parts = [];
  if (added) parts.push(`${added} ${added === 1 ? "producción nueva" : "producciones nuevas"}`);
  if (removed) parts.push(`${removed} ${removed === 1 ? "eliminada" : "eliminadas"}`);
  if (added) {
    const sample = document.createElement("mark");
    sample.textContent = "resaltada";
    legend.append(parts.join(", ") + " respecto al paso anterior; lo nuevo va ", sample, ".");
  } else {
    legend.append(parts.join(", ") + " respecto al paso anterior.");
  }
}

// ---------------------------------------------------------------------
// Presentación agrupada por fases: Entrada · Chomsky · Greibach · Validación
// ---------------------------------------------------------------------
const PHASES = [
  { id: "entrada", short: "Entrada", name: "Entrada", hint: "Validación de los datos" },
  { id: "fnc", short: "Chomsky", name: "Forma Normal de Chomsky",
    hint: "Inútiles, inalcanzables, nulas, unitarias y FNC" },
  { id: "fng", short: "Greibach", name: "Forma Normal de Greibach",
    hint: "Recursividad indirecta e inmediata, sustituciones" },
  { id: "validacion", short: "Validación", name: "Validación", hint: "FNG y equivalencia" },
];
const PHASE_BY_ID = Object.fromEntries(PHASES.map((p) => [p.id, p]));

const KIND_LABELS = {
  input: "Entrada", cleanup: "Depuración", start: "Nuevo inicial", null: "Nulas",
  unit: "Unitarias", cnf: "FNC", epsilon: "ε", order: "Orden",
  substitution: "Indirecta", detect: "Inmediata", left_recursion: "Inmediata",
  stage: "Resumen", back_substitution: "Hacia atrás", aux_substitution: "Auxiliares",
  validation: "Validación", equivalence: "Equivalencia",
};

const openPhases = new Set(); // fases que el usuario dejó abiertas

function phaseRanges() {
  // Para cada fase: índice del primer y último paso (o null si no tiene).
  const ranges = {};
  result.steps.forEach((s, i) => {
    const r = (ranges[s.phase] = ranges[s.phase] || { first: i, last: i });
    r.last = i;
  });
  return ranges;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderPhases(ranges, currentPhase) {
  const list = $("phases");
  list.replaceChildren();
  let reached = true;
  PHASES.forEach((phase, i) => {
    const range = ranges[phase.id];
    const li = el("li");
    const button = el("button", "phase");
    button.type = "button";
    button.dataset.phase = phase.id;
    let state = "pending";
    if (phase.id === currentPhase) { state = "current"; reached = false; }
    else if (reached && range) state = "done";
    button.classList.add(state);
    button.disabled = !range;
    if (state === "current") button.setAttribute("aria-current", "step");
    const count = range ? range.last - range.first + 1 : 0;
    // Franja inferior: cuánto de la fase se ha recorrido.
    let fill = state === "done" ? 1 : 0;
    if (state === "current") fill = (shown - range.first) / count;
    button.style.setProperty("--fill", fill);
    const text = el("span", "phase-text");
    text.append(
      el("span", "phase-name", phase.short),
      el("span", "phase-count", count ? `${count} ${count === 1 ? "paso" : "pasos"}` : "Sin pasos")
    );
    button.append(el("span", "phase-num", state === "done" ? "✓" : String(i + 1)), text);
    button.setAttribute(
      "aria-label",
      `${phase.name}: ${count} ${count === 1 ? "paso" : "pasos"}` + (state === "done" ? ", completa" : "")
    );
    button.title = phase.hint;
    button.addEventListener("click", () => {
      // Fase ya recorrida: ir a su último paso (su resultado). Si no: a su primer paso.
      shown = state === "done" ? range.last + 1 : range.first + 1;
      openPhases.add(phase.id);
      render();
    });
    li.append(button);
    list.append(li);
  });
}

function stepElement(step, isCurrent) {
  const li = el("li", "step" + (isCurrent ? " current" : ""));
  const head = el("div", "step-head");
  // En Greibach la etapa dice si es recursividad indirecta o inmediata.
  const detail = step.stage.split(" · ")[1];
  const label = detail ? detail[0].toUpperCase() + detail.slice(1) : KIND_LABELS[step.kind] || step.kind;
  head.append(el("span", "num", String(step.number)), el("span", "title", step.title));
  // En las fases cortas la etiqueta repetiría el nombre de la fase.
  if (step.phase === "fnc" || step.phase === "fng") head.append(el("span", "kind", label));
  li.append(head, el("div", "desc", step.description));
  if (step.details.length) {
    const ul = el("ul");
    step.details.forEach((d) => ul.append(el("li", "", d)));
    li.append(ul);
  }
  if (!isCurrent) {
    // Cada paso es navegable con el teclado además del ratón.
    li.tabIndex = 0;
    li.setAttribute("role", "button");
    li.setAttribute("aria-label", `Ir al paso ${step.number}: ${step.title}`);
    const go = () => { shown = step.number; render(); };
    li.addEventListener("click", go);
    li.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
    });
  } else {
    li.setAttribute("aria-current", "step");
  }
  return li;
}

function subgroupName(step) {
  // En Greibach se agrupa por variable: "S (A1) · recursividad indirecta" -> "S (A1)".
  return step.stage.split(" · ")[0];
}

function renderHistory(currentPhase) {
  const container = $("history");
  container.replaceChildren();
  const visible = result.steps.slice(0, shown);
  PHASES.forEach((phase) => {
    const steps = visible.filter((s) => s.phase === phase.id);
    if (!steps.length) return;
    const group = el("details", "phase-group phase-" + phase.id);
    group.open = phase.id === currentPhase || openPhases.has(phase.id);
    const summary = el("summary");
    summary.append(
      el("span", "group-name", phase.name),
      el("span", "group-count", `${steps.length} ${steps.length === 1 ? "paso" : "pasos"}`)
    );
    group.append(summary);
    group.addEventListener("toggle", () => {
      if (group.open) openPhases.add(phase.id); else openPhases.delete(phase.id);
    });

    if (phase.id === "fnc" && result.input_was_cnf) {
      group.append(el("p", "note",
        "La entrada ya estaba en FNC: esta fase solo comprueba que esté depurada."));
    }

    // Las fases cortas (entrada, validación) no necesitan subtítulos.
    const withSubstages = phase.id === "fnc" || phase.id === "fng";
    let lastSub = null;
    let sublist = null;
    steps.forEach((step) => {
      const sub = subgroupName(step);
      if (!sublist || (withSubstages && sub !== lastSub)) {
        lastSub = sub;
        if (withSubstages) {
          const title = el("div", "substage");
          if (/\(A\d+\)$/.test(sub)) {
            const [name, order] = sub.split(" (");
            title.append(`Variable ${name} `, el("small", "", `(${order}`));
          } else {
            title.textContent = sub;
          }
          group.append(title);
        }
        sublist = el("ol", "steps");
        group.append(sublist);
      }
      sublist.append(stepElement(step, step.number === shown));
    });
    container.append(group);
  });
  const current = container.querySelector(".step.current");
  if (current) current.scrollIntoView({ block: "nearest" });
}

function render() {
  const steps = result.steps;
  const current = steps[shown - 1];
  const ranges = phaseRanges();
  const currentPhase = current.phase;

  renderPhases(ranges, currentPhase);
  renderHistory(currentPhase);

  const previous = shown > 1 ? steps[shown - 2].grammar : null;
  const diff = renderGrammar($("current-grammar"), current.grammar, current.highlight, previous);
  if (previous) describeDiff(diff); else $("diff-legend").textContent = "Gramática tal como se ingresó.";
  const chip = $("current-phase");
  chip.textContent = (PHASE_BY_ID[currentPhase] || {}).name || "";
  chip.dataset.phase = currentPhase;

  const cnfDone = ranges.fnc && shown > ranges.fnc.last && result.cnf;
  $("cnf-box").classList.toggle("hidden", !cnfDone);
  if (cnfDone) renderGrammar($("cnf-grammar"), result.cnf);

  const finished = shown === steps.length;
  $("final-box").classList.toggle("hidden", !finished);
  if (finished) {
    renderGrammar($("final-grammar"), result.final);
    const status = $("final-status");
    status.className = result.is_gnf ? "ok" : "err";
    status.textContent = result.is_gnf
      ? "✔ La gramática final cumple la Forma Normal de Greibach."
      : "✘ La gramática final NO cumple: " + result.gnf_errors.join(" ");
  }
  $("progress-label").textContent = `Paso ${shown} de ${steps.length}`;
  $("progress").max = steps.length;
  $("progress").value = shown;
  $("prev-btn").disabled = shown <= 1;
  $("reset-btn").disabled = shown <= 1;
  $("next-btn").disabled = finished;
  $("all-btn").disabled = finished;
}

function exportHistory() {
  const lines = [];
  let phase = null;
  result.steps.forEach((s) => {
    if (s.phase !== phase) {
      phase = s.phase;
      lines.push(`===== ${((PHASE_BY_ID[phase] || {}).name || phase).toUpperCase()} =====`, "");
    }
    lines.push(`Paso ${s.number} [${s.stage}]: ${s.title}`, "  " + s.description);
    s.details.forEach((d) => lines.push("  - " + d));
    lines.push("  Gramática resultante:");
    s.grammar.text.split("\n").forEach((l) => lines.push("    " + l));
    lines.push("");
  });
  lines.push("GRAMÁTICA FINAL (FNG)");
  result.final.text.split("\n").forEach((l) => lines.push("  " + l));
  lines.push(result.is_gnf ? "Validación FNG: exitosa" : "Validación FNG: fallida");
  const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "historial_fng.txt";
  link.click();
  URL.revokeObjectURL(link.href);
}

async function loadExamples() {
  try {
    const examples = await (await fetch("/api/examples")).json();
    examples.forEach((ex, i) => {
      const option = document.createElement("option");
      option.value = i;
      option.textContent = ex.title;
      $("example-select").append(option);
    });
    $("example-select").addEventListener("change", (e) => {
      if (e.target.value !== "") fillInput(examples[Number(e.target.value)]);
    });
  } catch (_) {
    /* los ejemplos son opcionales */
  }
}

$("validate-btn").addEventListener("click", validate);
$("auto-btn").addEventListener("click", () => convert(false));
$("step-btn").addEventListener("click", () => convert(true));
$("next-btn").addEventListener("click", () => {
  if (shown < result.steps.length) { shown++; render(); }
});
$("prev-btn").addEventListener("click", () => {
  if (shown > 1) { shown--; render(); }
});
$("all-btn").addEventListener("click", () => { shown = result.steps.length; render(); });
$("reset-btn").addEventListener("click", () => { shown = 1; render(); });
$("export-btn").addEventListener("click", exportHistory);
document.addEventListener("keydown", (e) => {
  if (!result || $("result-card").classList.contains("hidden")) return;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
  if (e.key === "ArrowRight" && shown < result.steps.length) { shown++; render(); }
  else if (e.key === "ArrowLeft" && shown > 1) { shown--; render(); }
});
$("clear-btn").addEventListener("click", () => {
  fillInput({});
  $("example-select").value = "";
});
$("file-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  fillInput(await post("/api/parse-file", { text: await file.text() }));
  e.target.value = "";
});
loadExamples();
