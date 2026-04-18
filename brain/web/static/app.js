// Config UI — carrega /api/commands, renderiza por tipo, salva em /api/commands.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const state = { commands: [] };

const TYPE_LABEL = {
  tap:         "Toque (1 tecla)",
  multi_tap:   "Toque múltiplo",
  hold_until:  "Segurar até liberar",
  release:     "Liberar hold",
  sequence:    "Sequência",
};

function status(msg, cls = "") {
  const el = $("#status");
  el.textContent = msg;
  el.className = "status " + cls;
  if (msg) setTimeout(() => { if (el.textContent === msg) { el.textContent = ""; el.className = "status"; } }, 3500);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${txt}`);
  }
  return res.json();
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "value") node.value = v;
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
}

// ---------- renderers por tipo ----------
function renderTypeFields(cmd, container) {
  container.innerHTML = "";

  if (cmd.type === "tap") {
    container.append(
      labeled("Tecla", input("text", cmd.key || "", v => cmd.key = v)),
      labeled("Duração (ms)", input("number", cmd.duration_ms ?? 100, v => cmd.duration_ms = parseInt(v) || 0)),
    );
    return;
  }

  if (cmd.type === "hold_until") {
    container.append(
      labeled("Tecla a segurar", input("text", cmd.key || "", v => cmd.key = v)),
      labeled("Liberado pelo comando (id)", input("text", cmd.released_by || "", v => cmd.released_by = v)),
    );
    return;
  }

  if (cmd.type === "release") {
    container.append(
      labeled("Libera o comando (id)", input("text", cmd.releases || "", v => cmd.releases = v)),
    );
    return;
  }

  if (cmd.type === "multi_tap") {
    container.append(
      labeled("Teclas (separadas por vírgula)", input("text",
        (cmd.keys || []).join(", "),
        v => cmd.keys = v.split(",").map(s => s.trim()).filter(Boolean)
      )),
      labeled("Duração (ms)", input("number", cmd.duration_ms ?? 500, v => cmd.duration_ms = parseInt(v) || 0)),
    );
    return;
  }

  if (cmd.type === "sequence") {
    container.append(renderSteps(cmd));
    return;
  }
}

function renderSteps(cmd) {
  const wrap = el("div", { class: "steps-list" });
  cmd.steps = cmd.steps || [];

  const rerender = () => {
    wrap.innerHTML = "";
    cmd.steps.forEach((step, idx) => {
      const sel = el("select");
      ["tap", "wait_ms", "press", "release"].forEach(opt => {
        const o = el("option", { value: opt }, opt);
        if (step.action === opt) o.selected = true;
        sel.appendChild(o);
      });
      sel.onchange = () => { step.action = sel.value; rerender(); };

      let f1, f2;
      if (step.action === "tap") {
        f1 = input("text", step.key || "", v => step.key = v);
        f1.placeholder = "tecla (ex: f)";
        f2 = input("number", step.duration_ms ?? 80, v => step.duration_ms = parseInt(v) || 0);
        f2.placeholder = "duração ms";
      } else if (step.action === "wait_ms") {
        f1 = input("number", step.value ?? 500, v => step.value = parseInt(v) || 0);
        f1.placeholder = "ms";
        f2 = el("span"); // vazio
      } else {
        f1 = input("text", step.key || "", v => step.key = v);
        f1.placeholder = "tecla";
        f2 = el("span");
      }

      const rm = el("button", { type: "button", class: "btn-remove", title: "remover" }, "×");
      rm.onclick = () => { cmd.steps.splice(idx, 1); rerender(); };

      wrap.appendChild(el("div", { class: "step" }, [sel, f1, f2, rm]));
    });

    const add = el("button", { type: "button", class: "btn-add-step" }, "+ adicionar passo");
    add.onclick = () => { cmd.steps.push({ action: "tap", key: "", duration_ms: 80 }); rerender(); };
    wrap.appendChild(add);
  };

  rerender();
  return labeled("Passos", wrap);
}

function labeled(text, child) {
  return el("label", {}, [el("span", {}, text), child]);
}

function input(type, value, onChange) {
  const i = el("input", { type });
  i.value = value;
  i.oninput = () => onChange(i.value);
  return i;
}

// ---------- card ----------
function renderCard(cmd) {
  const tpl = $("#tpl-command").content.cloneNode(true);
  const card = tpl.querySelector(".card");
  card.dataset.id = cmd.id;
  $(".label", card).textContent = cmd.label || cmd.id;
  $(".desc", card).textContent = cmd.description || "";
  $(".type-badge", card).textContent = TYPE_LABEL[cmd.type] || cmd.type;

  const ta = $("textarea", card);
  ta.value = (cmd.keywords || []).join("\n");
  ta.oninput = () => {
    cmd.keywords = ta.value.split("\n").map(s => s.trim()).filter(Boolean);
  };

  renderTypeFields(cmd, $(".type-fields", card));

  $(".btn-test", card).onclick = async () => {
    try {
      await api(`/api/test/${encodeURIComponent(cmd.id)}`, { method: "POST" });
      status(`Testado: ${cmd.id}`, "ok");
    } catch (e) {
      status(`Erro: ${e.message}`, "err");
    }
  };

  return card;
}

function renderAll() {
  const root = $("#commands");
  root.innerHTML = "";
  for (const cmd of state.commands) {
    root.appendChild(renderCard(cmd));
  }
}

// ---------- ações ----------
async function load() {
  try {
    const data = await api("/api/commands");
    state.commands = data.commands || [];
    renderAll();
  } catch (e) {
    status(`Falha ao carregar: ${e.message}`, "err");
  }
}

async function save() {
  try {
    const res = await api("/api/commands", {
      method: "POST",
      body: JSON.stringify({ commands: state.commands }),
    });
    status(`Salvo (${res.count} comandos).`, "ok");
  } catch (e) {
    status(`Erro ao salvar: ${e.message}`, "err");
  }
}

async function reloadFromDisk() {
  try {
    await api("/api/reload", { method: "POST" });
    await load();
    status("Recarregado do disco.", "ok");
  } catch (e) {
    status(`Erro: ${e.message}`, "err");
  }
}

$("#btn-save").onclick = save;
$("#btn-reload").onclick = reloadFromDisk;

load();
