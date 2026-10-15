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
  showMessage("ok", "✔ La gramática es válida y está en Forma Normal de Chomsky.");
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
  shown = stepByStep ? 1 : data.steps.length;
  $("result-card").classList.remove("hidden");
  render();
  $("result-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderGrammar(el, grammar, highlight) {
  el.replaceChildren();
  grammar.productions.forEach((p) => {
    const line = document.createElement("span");
    if (highlight && highlight.includes(p.head)) line.className = "hl";
    line.textContent = p.head + " -> " + p.bodies.join(" | ") + "\n";
    el.append(line);
  });
}

function stepElement(step, isCurrent) {
  const li = document.createElement("li");
  if (isCurrent) li.className = "current";
  const stage = document.createElement("div");
  stage.className = "stage";
  stage.textContent = step.stage;
  const title = document.createElement("div");
  title.className = "title";
  title.textContent = `Paso ${step.number}: ${step.title}`;
  const desc = document.createElement("div");
  desc.textContent = step.description;
  li.append(stage, title, desc);
  if (step.details.length) {
    const ul = document.createElement("ul");
    step.details.forEach((d) => {
      const item = document.createElement("li");
      item.textContent = d;
      ul.append(item);
    });
    li.append(ul);
  }
  return li;
}

function render() {
  const steps = result.steps;
  const current = steps[shown - 1];
  renderGrammar($("current-grammar"), current.grammar, current.highlight);

  const list = $("history");
  list.replaceChildren();
  steps.slice(0, shown).forEach((step, i) => list.append(stepElement(step, i === shown - 1)));
  list.lastElementChild.scrollIntoView({ block: "nearest" });

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
  $("progress").textContent = `Paso ${shown} de ${steps.length}`;
  $("prev-btn").disabled = shown <= 1;
  $("next-btn").disabled = finished;
  $("all-btn").disabled = finished;
}

function exportHistory() {
  const lines = [];
  result.steps.forEach((s) => {
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
