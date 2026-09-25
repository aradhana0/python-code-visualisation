"use strict";

// ------------------------------------------------------------------ helpers
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const KEYWORDS = new Set(("False None True and as assert async await break class continue def del " +
  "elif else except finally for from global if import in is lambda nonlocal not or pass raise " +
  "return try while with yield match case").split(" "));
const TOKEN_RE = /(#.*$)|([rbfuRBFU]{0,2}(?:"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?))|(\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?j?\b)|([A-Za-z_]\w*)/g;

function highlight(line) {
  let out = "", last = 0, m;
  TOKEN_RE.lastIndex = 0;
  while ((m = TOKEN_RE.exec(line))) {
    out += esc(line.slice(last, m.index));
    const [tok, com, str, num, word] = m;
    if (com) out += `<span class="tok-com">${esc(tok)}</span>`;
    else if (str) out += `<span class="tok-str">${esc(tok)}</span>`;
    else if (num) out += `<span class="tok-num">${esc(tok)}</span>`;
    else if (KEYWORDS.has(word)) out += `<span class="tok-kw">${esc(tok)}</span>`;
    else if (line[TOKEN_RE.lastIndex] === "(") out += `<span class="tok-fn">${esc(tok)}</span>`;
    else out += esc(tok);
    last = TOKEN_RE.lastIndex;
  }
  return out + esc(line.slice(last));
}

const storage = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* ignore */ } },
};

// -------------------------------------------------------------------- state
const state = {
  trace: null,      // {steps, error, truncated}
  lines: [],        // source lines of the traced program
  index: 0,         // current step
  timer: null,      // playback interval
};

// ------------------------------------------------------------------- editor
const codeEl = $("code"), gutterEl = $("gutter");

function updateGutter() {
  const n = codeEl.value.split("\n").length;
  gutterEl.textContent = Array.from({ length: n }, (_, i) => i + 1).join("\n");
  gutterEl.scrollTop = codeEl.scrollTop;
}

codeEl.addEventListener("input", () => { updateGutter(); storage.set("pyviz-code", codeEl.value); });
codeEl.addEventListener("scroll", () => { gutterEl.scrollTop = codeEl.scrollTop; });
codeEl.addEventListener("keydown", (e) => {
  const { selectionStart: s, selectionEnd: end, value } = codeEl;
  if (e.key === "Tab") {
    e.preventDefault();
    codeEl.setRangeText("    ", s, end, "end");
    codeEl.dispatchEvent(new Event("input"));
  } else if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
    // Keep the current indentation, and indent after a trailing colon.
    const lineStart = value.lastIndexOf("\n", s - 1) + 1;
    const line = value.slice(lineStart, s);
    let indent = line.match(/^\s*/)[0];
    if (/:\s*(#.*)?$/.test(line)) indent += "    ";
    e.preventDefault();
    codeEl.setRangeText("\n" + indent, s, end, "end");
    codeEl.dispatchEvent(new Event("input"));
  } else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    run();
  }
});

// ----------------------------------------------------------------- examples
const examplesEl = $("examples");
EXAMPLES.forEach((ex, i) => examplesEl.add(new Option(ex.name, i)));
examplesEl.add(new Option("— your code —", "custom"), 0);
examplesEl.addEventListener("change", () => {
  if (examplesEl.value === "custom") return;
  const ex = EXAMPLES[examplesEl.value];
  codeEl.value = ex.code;
  $("stdin").value = ex.stdin || "";
  updateGutter();
  storage.set("pyviz-code", codeEl.value);
  if (state.trace) edit();
});

// ------------------------------------------------------------------ run/edit
async function run() {
  const btn = $("btn-run");
  btn.disabled = true;
  btn.textContent = "Running…";
  stop();
  try {
    const res = await fetch("api/trace", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: codeEl.value, stdin: $("stdin").value }),
    });
    if (!res.ok) throw new Error(`Server error ${res.status}: ${await res.text()}`);
    const trace = await res.json();
    if (!trace.steps.length) {
      showError(trace.error);
      return;
    }
    state.trace = trace;
    state.lines = codeEl.value.split("\n");
    enterVizMode();
    go(0);
  } catch (err) {
    showError({ type: "Error", message: err.message });
  } finally {
    btn.disabled = false;
    btn.innerHTML = "&#x25B6; Visualise";
  }
}

function showError(error) {
  const where = error && error.line ? ` (line ${error.line})` : "";
  $("stdout").innerHTML = `<span class="err">${esc(error.type)}${where}: ${esc(error.message)}</span>`;
  if (error && error.line) {
    // Select the offending line in the editor.
    const lines = codeEl.value.split("\n");
    const start = lines.slice(0, error.line - 1).join("\n").length + (error.line > 1 ? 1 : 0);
    codeEl.focus();
    codeEl.setSelectionRange(start, start + (lines[error.line - 1] || "").length);
  }
}

function enterVizMode() {
  $("editor").hidden = true;
  $("codeview").hidden = false;
  $("controls").hidden = false;
  $("explain-card").hidden = false;
  $("arrow-legend").hidden = false;
  $("stdin-card").hidden = true;
  $("btn-edit").hidden = false;
  $("placeholder").hidden = true;
  $("viz").hidden = false;
  $("code-title").textContent = "Code (read-only while visualising)";
  $("slider").max = state.trace.steps.length - 1;
  $("codeview").innerHTML = state.lines.map((line, i) =>
    `<div class="cv-line" data-line="${i + 1}"><span class="arrow-cell"></span>` +
    `<span class="ln">${i + 1}</span><span class="src">${highlight(line) || " "}</span></div>`
  ).join("");
}

function edit() {
  stop();
  state.trace = null;
  $("editor").hidden = false;
  $("codeview").hidden = true;
  $("controls").hidden = true;
  $("explain-card").hidden = true;
  $("arrow-legend").hidden = true;
  $("stdin-card").hidden = false;
  $("btn-edit").hidden = true;
  $("placeholder").hidden = false;
  $("viz").hidden = true;
  $("code-title").textContent = "Code";
  $("stdout").textContent = "";
  codeEl.focus();
}

$("btn-run").addEventListener("click", run);
$("btn-edit").addEventListener("click", edit);

// ----------------------------------------------------------------- playback
function go(i) {
  const steps = state.trace.steps;
  state.index = Math.max(0, Math.min(steps.length - 1, i));
  render();
}

function stop() {
  clearInterval(state.timer);
  state.timer = null;
  $("btn-play").classList.remove("playing");
  $("btn-play").innerHTML = "&#x25B6;";
}

function togglePlay() {
  if (state.timer) return stop();
  if (state.index >= state.trace.steps.length - 1) go(0);
  $("btn-play").classList.add("playing");
  $("btn-play").innerHTML = "&#x23F8;";
  state.timer = setInterval(() => {
    if (state.index >= state.trace.steps.length - 1) return stop();
    go(state.index + 1);
  }, Number($("speed").value));
}

$("btn-first").addEventListener("click", () => { stop(); go(0); });
$("btn-prev").addEventListener("click", () => { stop(); go(state.index - 1); });
$("btn-next").addEventListener("click", () => { stop(); go(state.index + 1); });
$("btn-last").addEventListener("click", () => { stop(); go(Infinity); });
$("btn-play").addEventListener("click", togglePlay);
$("speed").addEventListener("change", () => { if (state.timer) { stop(); togglePlay(); } });
$("slider").addEventListener("input", (e) => { stop(); go(Number(e.target.value)); });

document.addEventListener("keydown", (e) => {
  if (!state.trace || /^(TEXTAREA|INPUT|SELECT)$/.test(e.target.tagName) && e.target.id !== "slider") return;
  const actions = {
    ArrowRight: () => { stop(); go(state.index + 1); },
    ArrowLeft: () => { stop(); go(state.index - 1); },
    Home: () => { stop(); go(0); },
    End: () => { stop(); go(Infinity); },
    " ": togglePlay,
  };
  if (actions[e.key]) { e.preventDefault(); actions[e.key](); }
});

// -------------------------------------------------------------- rendering
function render() {
  const { steps } = state.trace;
  const i = state.index;
  const step = steps[i];
  const prev = i > 0 ? steps[i - 1] : null;

  $("slider").value = i;
  $("step-counter").textContent = `Step ${i + 1} of ${steps.length}` +
    (state.trace.truncated && i === steps.length - 1 ? " (stopped: step limit reached)" : "");
  $("btn-first").disabled = $("btn-prev").disabled = i === 0;
  $("btn-next").disabled = $("btn-last").disabled = i === steps.length - 1;

  renderCode(step, prev);
  renderExplanation(step, prev);
  renderStdout(step);
  renderStack(step, prev);
  renderHeap(step, prev);
  requestAnimationFrame(drawArrows);
}

function isFinished(step) {
  return step.event === "return" && step.stack.length === 1;
}

function renderCode(step, prev) {
  const view = $("codeview");
  view.querySelectorAll(".cv-line").forEach((el) => {
    el.classList.remove("next", "prev", "errline");
    el.querySelector(".arrow-cell").textContent = "";
  });
  const mark = (line, cls, symbol) => {
    const el = view.querySelector(`.cv-line[data-line="${line}"]`);
    if (!el) return null;
    el.classList.add(cls);
    el.querySelector(".arrow-cell").textContent = symbol;
    return el;
  };
  if (prev && prev.line !== step.line) mark(prev.line, "prev", "➜");
  let current;
  if (step.event === "uncaught_exception" || step.event === "exception") {
    current = mark(step.line, "errline", "✖");
  } else if (!isFinished(step)) {
    current = mark(step.line, "next", "➜");
  }
  if (current) {
    const top = current.offsetTop, h = current.offsetHeight;
    if (top < view.scrollTop || top + h > view.scrollTop + view.clientHeight) {
      view.scrollTop = top - view.clientHeight / 3;
    }
  }
}

function lineText(n) {
  return (state.lines[n - 1] || "").trim();
}

function renderExplanation(step, prev) {
  const top = step.stack[step.stack.length - 1];
  const parts = [];
  const items = [];

  if (!prev) {
    parts.push(`<div class="headline">&#x1F680; Program starts in the <b>Global frame</b>.</div>`);
  } else if (step.event === "call") {
    parts.push(`<div class="headline">Line ${prev.line} <code>${highlight(lineText(prev.line))}</code> made a function call.</div>`);
  } else if (step.event === "uncaught_exception") {
    parts.push(`<div class="headline error">&#x1F4A5; Uncaught ${esc(step.exception)} on line ${step.line} — the program stops here.</div>`);
  } else {
    parts.push(`<div class="headline">Executed line ${prev.line}: <code>${highlight(lineText(prev.line))}</code></div>`);
  }

  const val = (v) => `<span class="val">${esc(v)}</span>`;
  for (const ef of step.effects || []) {
    const where = ef.frame !== undefined && ef.frame !== top.id ? ` <span class="muted">(in ${esc(ef.frameName)})</span>` : "";
    switch (ef.kind) {
      case "call":
        items.push(`&#x1F4DE; Called <b>${esc(ef.frameName)}</b>(${esc(ef.args)}) — a new frame is pushed onto the call stack.`);
        break;
      case "popped":
        items.push(`&#x2B06;&#xFE0F; <b>${esc(ef.frameName)}</b> finished — its frame is popped off the call stack.`);
        break;
      case "new":
        items.push(`&#x2728; New variable <b>${esc(ef.name)}</b> = ${val(ef.value)}${where}`);
        break;
      case "changed":
        items.push(`&#x270F;&#xFE0F; <b>${esc(ef.name)}</b> changed: ${val(ef.old)} &rarr; ${val(ef.value)}${where}`);
        break;
      case "deleted":
        items.push(`&#x1F5D1;&#xFE0F; <b>${esc(ef.name)}</b> was deleted${where}`);
        break;
      case "mutated":
        items.push(`&#x1F527; ${ef.objects.length > 1 ? "Objects were" : "An object was"} modified in place (outlined) — every variable pointing to it sees the change.`);
        break;
      case "output":
        items.push(`&#x1F5A8;&#xFE0F; Printed ${val(ef.text.replace(/\n$/, ""))}`);
        break;
    }
  }

  if (step.event === "return") {
    if (isFinished(step)) items.push(`&#x2705; <b>Program finished.</b>`);
    else if (step.unwinding) items.push(`<span class="error">${esc(top.name)} exits early because of the exception.</span>`);
    else items.push(`&#x21A9;&#xFE0F; <b>${esc(top.name)}</b> is returning ${val(renderValue(step.returnValue, step.heap))} to its caller.`);
  }
  if (step.event === "exception") {
    items.push(`<span class="error">&#x26A0;&#xFE0F; Raised ${esc(step.exception)}</span> — Python looks for a matching <code>except</code>.`);
  }
  if (!items.length && prev) {
    const src = lineText(prev.line);
    if (/^(if|elif|while)\b/.test(src)) {
      items.push(`<span class="muted">Condition evaluated — execution continues at line ${step.line}.</span>`);
    } else if (/^for\b/.test(src)) {
      items.push(`<span class="muted">Loop finished — no more items.</span>`);
    } else if (/^(def|class)\b/.test(src)) {
      items.push(`<span class="muted">Definition processed.</span>`);
    } else {
      items.push(`<span class="muted">No variables changed.</span>`);
    }
  }

  if (items.length) parts.push(`<ul>${items.map((x) => `<li>${x}</li>`).join("")}</ul>`);

  if (step.event === "call") {
    parts.push(`<div class="nextline">Next: enter <b>${esc(top.name)}</b> at line ${step.line}.</div>`);
  } else if (step.event === "line") {
    parts.push(`<div class="nextline">Next to execute: line ${step.line} <code>${highlight(lineText(step.line))}</code></div>`);
  }
  $("explain").innerHTML = parts.join("");
}

function renderStdout(step) {
  let html = esc(step.stdout);
  if (step.event === "uncaught_exception") html += `<span class="err">${esc(step.exception)}</span>`;
  const el = $("stdout");
  el.innerHTML = html;
  el.scrollTop = el.scrollHeight;
}

function renderValue(enc, heap, seen = new Set()) {
  if ("p" in enc) return enc.p;
  const obj = heap[enc.r];
  if (!obj || seen.has(enc.r)) return "…";
  seen = new Set(seen).add(enc.r);
  const r = (e) => renderValue(e, heap, seen);
  const more = obj.more ? ", …" : "";
  switch (obj.t) {
    case "list": return `[${obj.items.map(r).join(", ")}${more}]`;
    case "tuple": return `(${obj.items.map(r).join(", ")}${obj.items.length === 1 ? "," : ""}${more})`;
    case "set": case "frozenset": return obj.items.length ? `{${obj.items.map(r).join(", ")}${more}}` : "set()";
    case "dict": return `{${obj.items.map(([k, v]) => `${r(k)}: ${r(v)}`).join(", ")}${more}}`;
    case "function": return `<function ${obj.name}>`;
    case "class": return `<class ${obj.name}>`;
    case "instance": return `${obj.name}(${obj.attrs.map(([k, v]) => `${k}=${r(v)}`).join(", ")})`;
    default: return obj.repr;
  }
}

function valueHTML(enc) {
  if ("p" in enc) return `<span class="prim t-${esc(enc.t)}" title="${esc(enc.t)}">${esc(enc.p)}</span>`;
  return `<span class="ref-dot" data-target="${enc.r}"></span>`;
}

function renderStack(step, prev) {
  const changed = new Map();
  let newFrames = new Set();
  for (const ef of step.effects || []) {
    if (ef.kind === "new" || ef.kind === "changed") changed.set(`${ef.frame}:${ef.name}`, ef.kind);
    if (ef.kind === "call") newFrames.add(ef.frame);
  }
  const frames = [...step.stack].reverse();
  const activeId = step.stack[step.stack.length - 1].id;
  $("frames").innerHTML = frames.map((fr) => {
    const rows = fr.vars.map(([name, enc]) => {
      const cls = changed.get(`${fr.id}:${name}`) || "";
      return `<tr class="${cls}"><td class="name">${esc(name)}</td><td>${valueHTML(enc)}</td></tr>`;
    });
    if (fr.id === activeId && step.event === "return" && step.returnValue && !isFinished(step)) {
      rows.push(`<tr class="ret"><td class="name">return</td><td>${valueHTML(step.returnValue)}</td></tr>`);
    }
    const classes = ["frame", fr.id === activeId ? "active" : "", newFrames.has(fr.id) ? "new-frame" : ""].join(" ");
    return `<div class="${classes}">
      <div class="frame-head"><span>${esc(fr.name)}</span><span class="where">line ${fr.line}</span></div>
      ${rows.length ? `<table class="vars">${rows.join("")}</table>` : `<div class="empty">no variables yet</div>`}
    </div>`;
  }).join("");
}

function renderHeap(step, prev) {
  const mutated = new Set();
  for (const ef of step.effects || []) if (ef.kind === "mutated") ef.objects.forEach((o) => mutated.add(String(o)));
  const prevHeap = prev ? prev.heap : {};

  // Order objects by first reference (depth-first from the oldest frame) so
  // related objects sit near each other.
  const order = [], seen = new Set();
  const visit = (enc) => {
    if (!enc || "p" in enc || seen.has(String(enc.r))) return;
    const id = String(enc.r);
    seen.add(id);
    order.push(id);
    const obj = step.heap[id];
    if (!obj) return;
    (obj.items || []).forEach((it) => Array.isArray(it) ? it.forEach(visit) : visit(it));
    (obj.attrs || []).forEach(([, v]) => visit(v));
  };
  step.stack.forEach((fr) => fr.vars.forEach(([, enc]) => visit(enc)));
  if (step.returnValue) visit(step.returnValue);

  $("heap").innerHTML = order.map((id) => {
    const obj = step.heap[id];
    if (!obj) return "";
    const classes = ["heap-obj", mutated.has(id) ? "mutated" : "", prev && !(id in prevHeap) ? "fresh" : ""].join(" ");
    return `<div class="${classes}" id="heap-${id}">
      <div class="heap-label">${esc(heapLabel(obj))}</div>
      <div class="heap-body">${heapBody(obj)}</div>
    </div>`;
  }).join("");
}

function heapLabel(obj) {
  switch (obj.t) {
    case "instance": return `${obj.name} instance`;
    case "class": return `class ${obj.name}`;
    case "function": return "function";
    case "other": return obj.name;
    default: return `${obj.t} (${obj.items.length + (obj.more || 0)} items)`;
  }
}

function heapBody(obj) {
  const more = obj.more ? `<div class="cell"><div class="idx">&nbsp;</div>…+${obj.more}</div>` : "";
  switch (obj.t) {
    case "list": case "tuple": case "set": case "frozenset":
      if (!obj.items.length) return `<div class="seq"><span class="empty-seq">empty</span></div>`;
      return `<div class="seq">${obj.items.map((it, i) =>
        `<div class="cell"><div class="idx">${obj.t === "list" || obj.t === "tuple" ? i : "&nbsp;"}</div>${valueHTML(it)}</div>`
      ).join("")}${more}</div>`;
    case "dict":
      if (!obj.items.length) return `<div class="seq"><span class="empty-seq">empty</span></div>`;
      return `<table class="kv">${obj.items.map(([k, v]) =>
        `<tr><td class="key">${valueHTML(k)}</td><td>${valueHTML(v)}</td></tr>`).join("")}</table>`;
    case "instance": case "class":
      if (!obj.attrs.length) return `<div class="fn-body muted">no attributes</div>`;
      return `<table class="kv">${obj.attrs.map(([k, v]) =>
        `<tr><td class="key">${esc(k)}</td><td>${valueHTML(v)}</td></tr>`).join("")}</table>`;
    case "function":
      return `<div class="fn-body"><span class="tok-kw">def</span> <span class="tok-fn">${esc(obj.name)}</span>${esc(obj.sig)}</div>`;
    default:
      return `<div class="other-body">${esc(obj.repr)}</div>`;
  }
}

// ------------------------------------------------------------------ arrows
function drawArrows() {
  const viz = $("viz"), svg = $("arrows");
  if (!state.trace || viz.hidden) return;
  svg.querySelectorAll("path.link").forEach((p) => p.remove());
  svg.setAttribute("width", viz.scrollWidth);
  svg.setAttribute("height", viz.scrollHeight);
  const base = viz.getBoundingClientRect();

  viz.querySelectorAll(".ref-dot").forEach((dot) => {
    const target = document.querySelector(`#heap-${dot.dataset.target} .heap-body`);
    if (!target) return;
    const d = dot.getBoundingClientRect(), t = target.getBoundingClientRect();
    const sx = d.left + d.width / 2 - base.left, sy = d.top + d.height / 2 - base.top;
    let path;
    if (t.left - base.left > sx + 20) {
      // Frame → heap: enter the object from the left.
      const tx = t.left - base.left - 2, ty = t.top - base.top + Math.min(12, t.height / 2);
      const dx = Math.max(30, (tx - sx) / 2);
      path = `M${sx},${sy} C${sx + dx},${sy} ${tx - dx},${ty} ${tx},${ty}`;
    } else {
      // Heap → heap: loop out to the right, then enter from the top/bottom.
      const tx = t.left - base.left + 14;
      const below = t.top - base.top > sy;
      const ty = below ? t.top - base.top - 2 : t.bottom - base.top + 2;
      const bend = below ? -40 : 40;
      path = `M${sx},${sy} C${sx + 60},${sy} ${tx},${ty + bend} ${tx},${ty}`;
    }
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", path);
    p.setAttribute("class", "link");
    p.setAttribute("marker-end", "url(#arrowhead)");
    svg.appendChild(p);
  });
}
window.addEventListener("resize", () => requestAnimationFrame(drawArrows));

// ------------------------------------------------------------------- init
codeEl.value = storage.get("pyviz-code") || EXAMPLES[0].code;
examplesEl.value = storage.get("pyviz-code") ? "custom" : "0";
updateGutter();
$("viz").hidden = true;
