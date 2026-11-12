/* Stick Citizen v3 screen. Talks to Python through window.pywebview.api (see webapi.py). */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const h = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "html") e.innerHTML = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
};

const S = {
  state: null, view: "sticks", stick: null, mode: "flight",
  images: {}, aspect: {}, live: {}, axes: {}, sel: null, othersOpen: false,
  lastPress: null, drag: null,
};
let API = null;

const DIR_ORDER = ["up", "up-right", "right", "down-right", "down", "down-left", "left", "up-left", "push", ""];
const DIR_ARROW = { up: "▲", down: "▼", left: "◀", right: "▶", "up-left": "◤", "up-right": "◥", "down-left": "◣", "down-right": "◢", push: "●" };
const HAT_DIR = { u: "up", d: "down", l: "left", r: "right" };
const PLACEHOLDER = "placeholder.svg";

/* ---------------- data helpers ---------------- */
const sticks = () => (S.state ? S.state.sticks : []);
const stickBySlot = (slot) => sticks().find((s) => s.slot === slot);
const shown = () => {
  const all = sticks();
  if (!all.length) return [];
  if (S.stick === "both" && all.length > 1) return all;
  return [stickBySlot(S.stick) || all.find((s) => s.side === "R") || all[0]];
};
const inMode = (b) => S.mode === "all" || b.mode === S.mode || b.mode === "general";
const bindsFor = (stick, key) => (key ? stick.binds[key] || [] : []).filter(inMode);
const AXES = ["X axis", "Y axis", "Z axis", "RotX", "RotY", "RotZ", "Slider 1", "Slider 2"];
const shortKey = (k) => (k[0] === "b" ? "B" + k.slice(1) : k[0] === "h" ? `H${k.slice(1, -1)}${DIR_ARROW[HAT_DIR[k.slice(-1)]]}` : AXES[+k.slice(1)] || k.toUpperCase());
const tagFor = (act) => (/hold/.test(act || "") ? "HOLD" : /double/.test(act || "") ? "2×" : "");

/* group the stick map's controls into on-screen labels */
function groupsOf(stick) {
  const groups = [];
  const byName = {};
  for (const c of stick.controls) {
    const g = c.group || "#" + c.id;
    if (!byName[g]) {
      byName[g] = { id: g, name: c.group || c.label, members: [], dot: c.dot || [0.5, 0.5], hat: !!c.group };
      groups.push(byName[g]);
    }
    byName[g].members.push(c);
  }
  for (const g of groups) g.members.sort((a, b) => DIR_ORDER.indexOf(a.dir) - DIR_ORDER.indexOf(b.dir));
  return groups;
}

function summary(stick, g) {
  // primary line: first member with a base binding in this mode
  let main = null, extra = 0, shift = null;
  for (const m of g.members) {
    const base = m.inputs.base ? bindsFor(stick, m.inputs.base) : [];
    const sh = m.inputs.shift ? bindsFor(stick, m.inputs.shift) : [];
    if (base.length) { if (!main) main = { m, b: base[0], more: base.length - 1 }; else extra++; }
    if (sh.length && !shift) shift = { m, b: sh[0] };
  }
  const unset = g.members.every((m) => !m.inputs.base);
  return { main, extra, shift, unset };
}

/* controls in the order the setup walkthrough asks for them: top of the stick down;
   inside a hat: the four main directions, the push, then the diagonals */
const SETUP_DIRS = ["up", "right", "down", "left", "push", "up-right", "down-right", "down-left", "up-left", ""];
const DIAGONAL = (d) => /-/.test(d || "");
function setupOrder(stick) {
  const gs = groupsOf(stick).sort((a, b) => (a.dot[1] - b.dot[1]) || (a.dot[0] - b.dot[0]));
  return gs.flatMap((g) => [...g.members].sort((a, b) => SETUP_DIRS.indexOf(a.dir) - SETUP_DIRS.indexOf(b.dir))
    .filter((m) => !m.inputs.base).map((m) => ({ g, m })));
}

/* ---------------- boot ---------------- */
async function boot() {
  API = window.pywebview ? window.pywebview.api : window.MOCK_API;
  if (!API) { document.body.textContent = "Stick Citizen: no backend"; return; }
  wire();
  await refresh();
  S.stick = sticks().length > 1 ? "both" : (sticks()[0] || {}).slot;
  render();
  if (S.state.fresh) toast("Fresh start: older stick maps were moved to the backups folder. Run Set up.");
  pollLoop();
}
let booted = false;
const once = () => { if (!booted) { booted = true; boot(); } };
if (window.MOCK_API) window.addEventListener("DOMContentLoaded", once);
else if (window.pywebview && window.pywebview.api) once();
else window.addEventListener("pywebviewready", once);

async function refresh() {
  S.state = await API.get_state();
  for (const s of S.state.sticks) {
    if (s.has_image && !S.images[s.name]) {
      const url = await API.get_image(s.slot);
      if (url) S.images[s.name] = url;
    }
    if (!s.has_image) delete S.images[s.name];
  }
}

async function apply(res) {
  if (!res) return;
  if (res.state) S.state = res.state;
  if (res.msg) toast(res.msg);
  render();
}

/* ---------------- render ---------------- */
function render() {
  if (!S.state) return;
  const app = $("#app");
  const list = shown();
  app.classList.toggle("both", list.length > 1);
  app.classList.toggle("edit", S.view === "edit");
  renderTabs();
  renderModes();
  $("#btnVoice").classList.toggle("off", !S.state.speech);
  $("#btnSave").classList.toggle("dirty", S.state.layout.dirty);
  $("#btnSave").textContent = S.state.layout.dirty ? "Save for Star Citizen •" : "Save for Star Citizen";
  $("#hint").textContent = S.view === "edit"
    ? "Edit: drag numbered dots onto the buttons · click a label to bind · Map a control to add one"
    : `${S.state.layout.name} · ${S.state.layout.count} bindings · SC ${S.state.catalog.sc_version}`;
  const need = shown().filter((x) => x.unassigned && x.unassigned.length);
  const sb = $("#btnSetup");
  if (sb) {
    sb.hidden = !need.length || !!S.wiz;
    if (need.length) sb.textContent = `Set up ${need[0].side === "L" ? "left" : need[0].side === "R" ? "right" : "this"} stick · ${need[0].unassigned.length} to learn`;
  }
  renderStage();
  renderOthers();
}

function renderTabs() {
  const box = $("#stickTabs");
  box.innerHTML = "";
  const all = sticks();
  if (all.length < 2) { box.hidden = true; return; }
  box.hidden = false;
  for (const s of all) {
    const label = s.side === "L" ? "Left" : s.side === "R" ? "Right" : s.name;
    box.append(h("button", { class: S.stick === s.slot ? "on" : "", role: "tab", title: s.name + (s.connected ? "" : " (not connected)"),
      onclick: () => { S.stick = s.slot; render(); } }, label));
  }
  box.append(h("button", { class: S.stick === "both" ? "on" : "", role: "tab", onclick: () => { S.stick = "both"; render(); } }, "Both"));
}

function renderModes() {
  const box = $("#modes");
  box.querySelectorAll(".chip").forEach((c) => c.remove());
  for (const m of S.state.modes) {
    box.append(h("button", { class: "chip" + (S.mode === m.id ? " on" : ""), onclick: () => { S.mode = m.id; render(); } }, m.label));
  }
}

function imgFor(stick) {
  return S.images[stick.name] || PLACEHOLDER;
}

function aspectOf(stick, src) {
  const k = src;
  if (S.aspect[k]) return S.aspect[k];
  const im = new Image();
  im.onload = () => { S.aspect[k] = im.naturalWidth / im.naturalHeight; render(); };
  im.src = src;
  return 0.78;
}

function renderStage() {
  const stage = $("#stage");
  const svg = $("#lines");
  stage.querySelectorAll(".stick,.stick-cap,.dot,.card,.photo-btn").forEach((e) => e.remove());
  svg.innerHTML = "";
  const list = shown();
  const empty = $("#empty");
  if (!list.length) {
    empty.hidden = false;
    empty.innerHTML = "<div><h2>No sticks found</h2><p>Plug in your sticks, or open a bindings file with the folder button.</p></div>";
    return;
  }
  empty.hidden = true;
  const W = stage.clientWidth, H = stage.clientHeight;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const both = list.length > 1;
  const pad = 8;
  const cardW = both ? Math.max(150, Math.min(196, W * 0.12)) : Math.max(220, Math.min(290, W * 0.21));

  list.forEach((stick, i) => {
    const src = imgFor(stick);
    const asp = aspectOf(stick, src);
    // columns: [outer, inner] for both; [left, right] for single
    let colL, colR, areaL, areaR;
    if (!both) {
      colL = pad; colR = W - pad - cardW;
      areaL = colL + cardW + 50; areaR = colR - 50;
    } else if (i === 0) {
      colL = pad; colR = W / 2 - 10 - cardW;
      areaL = colL + cardW * 0.15; areaR = colR - 26;
    } else {
      colL = W / 2 + 10; colR = W - pad - cardW;
      areaL = colL + cardW + 26; areaR = colR + cardW * 0.15;
    }
    const capH = 22;
    let ih = H - capH - 6, iw = ih * asp;
    if (iw > areaR - areaL) { iw = areaR - areaL; ih = iw / asp; }
    const ix = both ? (i === 0 ? areaR - iw : areaL) : (areaL + areaR - iw) / 2;
    const iy = Math.max(0, (H - capH - ih) / 2);
    stage.append(h("img", { class: "stick" + (S.images[stick.name] ? " photo" : ""), src, alt: stick.name,
      style: `left:${ix}px;top:${iy}px;width:${iw}px;height:${ih}px` }));
    const capL = i === 0 ? Math.max(ix, colL + cardW + 8) : ix, capR = i === 0 ? ix + iw : Math.min(ix + iw, colR - 8);
    if (both) stage.append(h("div", { class: "stick-cap", style: `left:${capL}px;top:${iy + ih + 4}px;width:${capR - capL}px` },
      (stick.side === "L" ? "LEFT" : stick.side === "R" ? "RIGHT" : "") + " · " + stick.name.toUpperCase() + (stick.connected ? "" : " · NOT CONNECTED")));
    if (S.view === "edit" && S.showPhotoBtn) stage.append(h("button", { class: "photo-btn", style: `left:${ix + iw / 2}px;top:${iy + ih - 34}px`,
      onclick: () => setPhoto(stick) }, S.images[stick.name] ? "Change stick photo" : "Set stick photo"));

    const groups = groupsOf(stick);
    if (!groups.length) {
      stage.append(h("div", { class: "card", style: `left:${both ? (i === 0 ? colL : colR) : colL}px;top:${H / 2 - 50}px;width:${cardW}px;cursor:default`,
        onclick: () => setView("edit") },
        h("div", { class: "hd" }, h("span", { class: "name" }, "NOT MAPPED YET")),
        h("div", { class: "a" }, "Map this stick"),
        h("div", { class: "s none" }, "Edit → Map a control")));
      return;
    }
    // which column does each label go in? the side of the picture its dot is on
    const placed = groups.map((g) => {
      const x = ix + g.dot[0] * iw, y = iy + g.dot[1] * ih;
      let left = g.dot[0] < 0.5;
      if (both) left = i === 0 ? g.dot[0] < 0.4 : g.dot[0] < 0.6;
      return { g, x, y, left };
    });
    [...placed].sort((a, b) => (a.y - b.y) || (a.x - b.x)).forEach((p, k) => (p.num = k + 1));
    const cols = { L: placed.filter((p) => p.left), R: placed.filter((p) => !p.left) };
    for (const side of ["L", "R"]) {
      const col = cols[side].sort((a, b) => a.y - b.y);
      if (!col.length) continue;
      const gap = 6;
      let ch = both ? 54 : 74;
      const compact = both || (col.length * (ch + gap) > H);
      if (compact && !both) ch = 50;
      while (col.length * (ch + gap) > H && ch > 34) ch -= 2;
      // stack near each dot, then push apart and back into the stage
      let y = -Infinity;
      for (const p of col) { p.cy = Math.max(p.y - ch / 2, y + ch + gap); y = p.cy; }
      const over = y + ch - H;
      if (over > 0) { let lim = H - ch; for (let k = col.length - 1; k >= 0; k--) { col[k].cy = Math.min(col[k].cy, lim); lim = col[k].cy - ch - gap; } }
      if (col[0].cy < 0) { let yy = 0; for (const p of col) { p.cy = Math.max(p.cy, yy); yy = p.cy + ch + gap; } }
      const cx = side === "L" ? colL : colR;
      for (const p of col) {
        drawCard(stage, svg, stick, p, cx, p.cy, cardW, ch, side, compact);
      }
    }
  });
}

function drawCard(stage, svg, stick, p, x, y, w, ch, side, compact) {
  const g = p.g;
  const { main, extra, shift, unset } = summary(stick, g);
  const target = S.coach && S.coach.slot === stick.slot && g.members.some((m) => m.id === S.coach.cid);
  const hotKeys = S.live[stick.slot] || new Set();
  let hot = false, hotShift = false, hotMember = null;
  for (const m of g.members) {
    if (m.inputs.base && hotKeys.has(m.inputs.base)) { hot = true; hotMember = m; }
    if (m.inputs.shift && hotKeys.has(m.inputs.shift)) { hot = true; hotShift = true; hotMember = m; }
  }
  const isShiftCtl = !main && !shift && /shift|modifier/i.test(g.name);
  const sel = S.sel && S.sel.slot === stick.slot && S.sel.group === g.id;
  const cls = ["card", compact && "compact", hot && "hot", hotShift && "shift", (sel || target) && "sel", isShiftCtl && "shiftctl", unset && "unset", target && "target"].filter(Boolean).join(" ");
  const codes = g.members.some((m) => m.dir) ? `${g.members.length} DIR`
    : (g.members.flatMap((m) => Object.entries(m.inputs).map(([l, k]) => (l === "shift" ? "⇧" : "") + shortKey(k))).join(" · ") || "NOT SET");
  // when a hat is pressed, show that direction's action
  let a, aTag = "";
  const pick = hotMember && g.hat ? { m: hotMember, b: bindsFor(stick, hotShift ? hotMember.inputs.shift : hotMember.inputs.base)[0] } : null;
  const shown_ = pick && pick.b ? pick : main;
  if (shown_ && shown_.b) {
    a = (g.hat ? (DIR_ARROW[shown_.m.dir] || "") + " " : "") + shown_.b.label;
    aTag = tagFor(shown_.b.activation);
  }
  const more = (main ? main.more : 0) + extra;
  const card = h("button", { class: cls, style: `left:${x}px;top:${y}px;width:${w}px;height:${ch}px`,
    onclick: () => openDrawer(stick.slot, g.id) },
    h("div", { class: "hd" }, h("span", { class: "n" }, String(p.num)), h("span", { class: "name" }, g.name.toUpperCase()), h("span", { class: "code" }, codes)),
    h("div", { class: "a" + (a ? "" : " none") }, a || (target ? `Press it now${g.hat ? " · " + (DIR_ARROW[(stick.controls.find((c) => c.id === S.coach.cid) || {}).dir] || "") : ""}` : unset ? "Not set up · press to learn" : isShiftCtl ? "Hold for ⇧ layer" : "—"),
      aTag ? h("span", { class: "tag" }, aTag) : null, more > 0 ? h("span", { class: "tag" }, "+" + more) : null),
    (!compact || (ch >= 48 && (shift || isShiftCtl))) ? h("div", { class: "s" + (shift ? "" : " none") },
      shift ? ["⇧ " + shift.b.label, tagFor(shift.b.activation) ? h("span", { class: "tag" }, tagFor(shift.b.activation)) : null]
        : (isShiftCtl ? "stick firmware" : "⇧ —")) : null);
  stage.append(card);
  // leader line from the card edge to the dot
  const ex = side === "L" ? x + w : x;
  const elbow = side === "L" ? ex + 18 : ex - 18;
  const cy = y + ch / 2;
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", `M${ex},${cy} H${elbow} L${p.x},${p.y}`);
  if (hot) path.setAttribute("class", "hot" + (hotShift ? " shift" : ""));
  svg.append(path);
  const dot = h("div", { class: ["dot", hot && "hot", hotShift && "shift", (sel || target) && "sel", target && "target", unset && "unset", isShiftCtl && "shiftkey"].filter(Boolean).join(" "),
    style: `left:${p.x}px;top:${p.y}px`, title: g.name }, String(p.num));
  if (S.view === "edit") dot.addEventListener("pointerdown", (e) => startDrag(e, stick, g, dot));
  stage.append(dot);
}

/* ---------------- unmapped strip ---------------- */
function renderOthers() {
  const box = $("#others");
  const list = shown();
  const items = [];
  for (const s of list) for (const k of s.others) items.push({ s, k });
  box.hidden = !items.length;
  if (!items.length) return;
  const head = $("#othersHead");
  head.setAttribute("aria-expanded", S.othersOpen);
  head.innerHTML = "";
  head.append(h("span", {}, `${S.othersOpen ? "▾" : "▸"}  Unmapped inputs · ${items.length}`),
    h("span", { class: "sub" }, S.view === "edit" ? "Click one to map it to a control" : "Inputs that are bound or fired but aren't on your stick map"));
  head.onclick = () => { S.othersOpen = !S.othersOpen; renderOthers(); };
  const body = $("#othersBody");
  body.hidden = !S.othersOpen;
  body.innerHTML = "";
  if (!S.othersOpen) return;
  for (const { s, k } of items) {
    const b = bindsFor(s, k);
    const hot = (S.live[s.slot] || new Set()).has(k);
    body.append(h("button", { class: "ochip" + (hot ? " hot" : ""), onclick: () => (S.view === "edit" ? mapFlow(s.slot, k) : openDrawer(s.slot, "@" + k)) },
      h("b", {}, (list.length > 1 ? (s.side || "js" + s.slot) + " " : "") + shortKey(k)),
      b.length ? b[0].label : h("span", { class: "x" }, "unbound")));
  }
}

/* ---------------- drawer: bindings for one control ---------------- */
function drawerGroup(slot, gid) {
  const stick = stickBySlot(slot);
  if (!stick) return null;
  if (gid.startsWith("@")) {
    const k = gid.slice(1);
    return { stick, g: { id: gid, name: shortKey(k), hat: false, members: [{ id: null, label: shortKey(k), dir: "", inputs: { base: k } }] } };
  }
  const g = groupsOf(stick).find((x) => x.id === gid);
  return g ? { stick, g } : null;
}

function openDrawer(slot, gid, adding = null) {
  S.sel = { slot, group: gid, adding };
  renderDrawer();
  render();
}
function closeDrawer() { S.sel = null; $("#drawer").hidden = true; render(); }

function renderDrawer() {
  const d = $("#drawer");
  if (!S.sel) { d.hidden = true; return; }
  const found = drawerGroup(S.sel.slot, S.sel.group);
  if (!found) { closeDrawer(); return; }
  const { stick, g } = found;
  d.hidden = false;
  d.innerHTML = "";
  const modeLabel = (S.state.modes.find((m) => m.id === S.mode) || {}).label;
  d.append(h("div", { class: "dr-head" },
    h("div", {}, h("h2", {}, g.name), h("div", { class: "sub" }, `${stick.side === "L" ? "LEFT" : stick.side === "R" ? "RIGHT" : "JS" + stick.slot} STICK · SHOWING ${S.mode === "all" ? "ALL MODES" : modeLabel.toUpperCase() + " + GENERAL"}`)),
    h("button", { class: "icon", "aria-label": "Close", onclick: closeDrawer, html: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>' })));
  const body = h("div", { class: "dr-body" });
  for (const m of g.members) {
    const title = g.hat ? `${DIR_ARROW[m.dir] || ""} ${m.label}` : m.label;
    const sec = h("div", { class: "member" }, h("h3", {}, title.toUpperCase(),
      h("span", { class: "k" }, Object.entries(m.inputs).map(([l, k]) => (l === "shift" ? "⇧" : "") + shortKey(k)).join(" · "))));
    for (const layer of ["base", "shift"]) {
      const key = m.inputs[layer];
      const row = h("div", { class: "layer" + (layer === "shift" ? " shift" : "") }, h("div", { class: "ln" }, layer === "shift" ? "⇧ SHIFT" : "BASE"));
      const col = h("div", {});
      if (!key) {
        if (layer === "shift" && m.id && m.inputs.base) col.append(h("button", { class: "add shift", onclick: () => pressFlow(stick.slot, m, "shift") }, "+ Add a shift layer (press it with shift held)"));
        else if (layer === "base" && m.id) col.append(h("button", { class: "add", onclick: () => pressFlow(stick.slot, m, "base") }, "Not set up · press the control to learn it"));
        else col.append(h("div", { class: "s none", style: "padding-top:8px;color:var(--faint);font-size:12px" }, "—"));
        row.append(col); sec.append(row); continue;
      }
      for (const b of stick.binds[key] || []) {
        const other = !inMode(b);
        const sel = h("select", { "aria-label": "Activation", title: "How the press triggers it",
          onchange: async (e) => apply(await API.set_activation(stick.slot, key, b.map, b.action, e.target.value)) },
          S.state.activations.filter((x) => !b.axis || !x).map((x) => h("option", { value: x, selected: x === b.activation ? true : null }, x ? x.replace(/_/g, " ") : "default")));
        col.append(h("div", { class: "bnd" },
          h("span", { class: "t", title: b.action }, b.label),
          h("span", { class: "m" + (other ? " other" : "") }, b.mode === "general" ? "any" : b.mode),
          b.axis ? null : sel,
          h("button", { class: "rm", "aria-label": "Remove", title: "Remove", onclick: async () => apply(await API.remove(stick.slot, key, b.map, b.action)) }, "×")));
      }
      const adding = S.sel.adding === key;
      if (adding) col.append(searchBox(stick, key));
      else col.append(h("button", { class: "add" + (layer === "shift" ? " shift" : ""), onclick: () => { S.sel.adding = key; renderDrawer(); setTimeout(() => { const i = $("#drawer .search input"); i && i.focus(); }, 0); } }, "+ Bind an action"));
      row.append(col);
      sec.append(row);
    }
    body.append(sec);
  }
  d.append(body);
  // map management
  const foot = h("div", { class: "dr-foot" });
  if (g.members[0].id) {
    foot.append(h("button", { class: "btn", onclick: () => renameFlow(stick.slot, g) }, "Rename"));
    if (g.hat) foot.append(h("button", { class: "btn", onclick: () => addDirFlow(stick.slot, g) }, "Add a direction"));
    foot.append(h("button", { class: "btn danger", onclick: async () => {
      for (const m of g.members) await API.edit_control(stick.slot, m.id, null, null, null, false, true);
      closeDrawer(); apply({ state: await API.get_state(), msg: `Removed ${g.name} from the stick map` });
    } }, "Remove from map"));
  } else {
    foot.append(h("button", { class: "btn go", onclick: () => { closeDrawer(); mapFlow(stick.slot, g.members[0].inputs.base); } }, "Add to stick map…"));
  }
  d.append(foot);
}

function searchBox(stick, key) {
  const wrap = h("div", { class: "search" });
  const input = h("input", { placeholder: "Search actions (gear, quantum, missile…)", "aria-label": "Search actions" });
  const results = h("div", { class: "results" });
  let kb = 0, rows = [];
  async function run() {
    let list = await API.search(input.value, S.mode, 120);
    if (key[0] === "a") list = list.filter((x) => x.axis);            // wheels and levers take axis actions
    results.innerHTML = "";
    rows = list.map((a, i) => h("button", { class: "res" + (i === kb ? " kb" : ""), onclick: () => pick(a) },
      h("span", { class: "t" }, (a.axis ? "⇕ " : "") + a.label), h("span", { class: "g" }, a.group), a.bound ? h("span", { class: "b" }, a.bound) : null));
    rows.forEach((r) => results.append(r));
    if (!list.length) results.append(h("div", { class: "res" }, h("span", { class: "g" }, "No actions match")));
    wrap._list = list;
  }
  async function pick(a) {
    S.sel.adding = null;
    apply(await API.assign(stick.slot, key, a.map, a.action));
    renderDrawer();
  }
  input.addEventListener("input", () => { kb = 0; run(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { S.sel.adding = null; renderDrawer(); }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { kb = Math.max(0, Math.min(rows.length - 1, kb + (e.key === "ArrowDown" ? 1 : -1))); rows.forEach((r, i) => r.classList.toggle("kb", i === kb)); rows[kb] && rows[kb].scrollIntoView({ block: "nearest" }); e.preventDefault(); }
    if (e.key === "Enter" && wrap._list && wrap._list[kb]) pick(wrap._list[kb]);
  });
  wrap.append(input, results);
  run();
  return wrap;
}

/* ---------------- edit flows ---------------- */
function setView(v) {
  if (v === "fly") { API.fly_test().then((r) => toast(r.msg)); return; }
  S.view = v;
  document.querySelectorAll("#views button").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
  render();
}

function modal(content) {
  const m = $("#modal");
  m.innerHTML = "";
  m.append(h("div", { class: "mbox", role: "dialog", "aria-modal": "true" }, content));
  m.hidden = false;
}
function closeModal() { $("#modal").hidden = true; API.cancel_capture(); S.capture = null; }

function waitForPress(slot, title, text, want = "button") {
  return new Promise((resolve) => {
    API.arm_capture(slot || 0, want);
    S.capture = resolve;
    modal([h("h2", {}, title), h("p", {}, text), h("div", { class: "wait" }, h("i"), "Waiting for a press…"),
      h("div", { class: "row" }, h("button", { class: "btn", onclick: () => { closeModal(); resolve(null); } }, "Cancel"))]);
  });
}

async function mapFlow(slot, key) {
  if (!key) {
    const got = await waitForPress(S.stick === "both" ? 0 : (shown()[0] || {}).slot, "Map a control", "Press the button, trigger or hat direction you want to add.");
    if (!got) return;
    slot = got.slot; key = got.key;
  }
  const stick = stickBySlot(slot);
  const groups = [...new Set(stick.controls.map((c) => c.group).filter(Boolean))];
  const isHat = key[0] === "h";
  const name = h("input", { value: isHat ? HAT_DIR[key.slice(-1)] : "", placeholder: "Trigger, Pinky, Red button…" });
  const group = h("input", { list: "grp", value: isHat ? `Hat ${key.slice(1, -1)}` : "", placeholder: "Leave empty for a single button" });
  const dl = h("datalist", { id: "grp" }, groups.map((g) => h("option", { value: g })));
  const dir = h("select", {}, DIR_ORDER.map((d) => h("option", { value: d, selected: isHat && d === HAT_DIR[key.slice(-1)] ? true : null }, d ? `${DIR_ARROW[d]} ${d}` : "—")));
  const save = async () => {
    const lbl = name.value.trim() || (dir.value ? dir.value : shortKey(key));
    const res = await API.map_control(slot, key, lbl, group.value.trim(), group.value.trim() ? dir.value : "", "");
    closeModal();
    if (S.view !== "edit") setView("edit");
    await apply(res);
    toast(`${res.msg} — now drag its dot onto the button`);
  };
  modal([h("h2", {}, `${shortKey(key)} on the ${stick.side === "L" ? "left" : stick.side === "R" ? "right" : "js" + slot} stick`),
    h("p", {}, "Name the physical control. For a hat, give every direction the same group name."),
    h("label", { class: "field" }, "Control name", name),
    h("label", { class: "field" }, "Group (hats: e.g. “8-way hat A1”)", group, dl),
    h("label", { class: "field" }, "Direction (hats only)", dir),
    h("div", { class: "row" }, h("button", { class: "btn", onclick: closeModal }, "Cancel"), h("button", { class: "btn go", onclick: save }, "Add to map"))]);
  setTimeout(() => name.focus(), 0);
  name.addEventListener("keydown", (e) => e.key === "Enter" && save());
}

async function pressFlow(slot, m, layer) {
  const name = m.group ? `${m.group} ${DIR_ARROW[m.dir] || ""} ${m.label}` : m.label;
  const got = await waitForPress(slot, layer === "shift" ? `Shift layer for ${name}` : name,
    layer === "shift" ? "Hold your shift button and press this control." : (m.how || "Press this control on your stick."), m.kind === "axis" ? "axis" : "button");
  if (!got) return;
  closeModal();
  await apply(layer === "base" ? await API.learn(got.slot, m.id, got.keys || [got.key]) : await API.assign_input(got.slot, m.id, layer, got.key));
  renderDrawer();
}

/* ---------------- guided setup wizard ----------------
   One control at a time: the photo zooms in on it, a compass shows which way to push,
   and the raw readout shows what the stick is sending. */
const sideName = (stick) => (stick.side === "L" ? "left" : stick.side === "R" ? "right" : "this");
const memberOf = (stick, id) => stick.controls.find((c) => c.id === id);
const isMini = (g) => /mini-?stick/i.test(g.name);
const isAnalog = (g, m) => isMini(g) && m.kind === "axis";      // the mini-stick's analog mode: two axes

async function setupFlow(stick) {
  const slot = stick.slot;
  const todo = setupOrder(stick).map(({ g, m }) => ({ gid: g.id, id: m.id }));
  if (!todo.length) return;
  S.stick = slot;
  S.wiz = { slot, todo, i: 0, learned: 0, gone: new Set(), note: null, last: null };
  const onMouse = (e) => { if (S.wiz && Math.abs(e.movementX) + Math.abs(e.movementY) > 0) { S.wiz.mouseAt = Date.now(); wizLive(); } };
  window.addEventListener("mousemove", onMouse);
  render();
  const W = S.wiz;
  while (W.i < W.todo.length) {
    const step = W.todo[W.i];
    const st = stickBySlot(slot);
    const m = st && memberOf(st, step.id);
    if (!m || W.gone.has(step.id)) { W.i++; continue; }
    const g = groupsOf(st).find((x) => x.id === step.gid);
    const got = await wizStep(st, g, m);
    if (got === "stop") break;
    if (got === "back") { let k = W.i - 1; while (k >= 0 && W.gone.has(W.todo[k].id)) k--; W.i = Math.max(0, k); W.note = null; continue; }
    if (got === "skip") { W.i++; W.note = null; continue; }
    if (got === "absent") {                       // not on this stick: take the whole control off the map
      const drop = isAnalog(g, m) ? g.members.filter((x) => x.kind === "axis")              // no analog mode: keep the hat
        : g.hat && DIAGONAL(m.dir) ? g.members.filter((x) => DIAGONAL(x.dir))                    // a 4-way hat: keep its 4 directions + push
        : g.members;
      for (const x of drop) { W.gone.add(x.id); await API.edit_control(slot, x.id, null, null, null, false, true); }
      S.state = await API.get_state(); W.note = null; continue;
    }
    // --- a press came in ---
    const keys = got.keys || [got.key];
    let key = keys[0];
    if (g.hat && m.dir) {
      const mine = new Set(g.members.filter((x) => x.id !== m.id).map((x) => x.inputs.base).filter(Boolean));
      if (DIAGONAL(m.dir)) {
        const fresh = keys.find((k) => !mine.has(k));
        if (!fresh) {                              // a diagonal that is just two directions at once
          for (const x of g.members.filter((x) => DIAGONAL(x.dir))) { W.gone.add(x.id); await API.edit_control(slot, x.id, null, null, null, false, true); }
          S.state = await API.get_state();
          W.note = { kind: "ok", text: `${g.name} sends diagonals as two directions at once, so there is nothing more to learn for it.` };
          continue;
        }
        key = fresh;
      }
    }
    const owner = st.controls.find((c) => c.id !== m.id && Object.values(c.inputs).includes(key));
    if (owner && !(owner.group && owner.group === m.group && !m.dir)) {
      const oname = owner.group ? `${owner.group} ${DIR_ARROW[owner.dir] || ""} ${owner.label}` : owner.label;
      const same = owner.group === m.group;
      const pick = await wizAsk(st, g, m, `That sent ${shortKey(key)}, which is already ${oname}.`,
        same ? "Looks like the same direction twice. Push it the way the compass shows." : `You may have pressed ${owner.group || owner.label} instead. The picture shows the one to press.`);
      if (pick !== "use") { W.note = null; continue; }
    }
    const res = await API.learn(slot, m.id, g.hat && m.dir ? [key] : keys);
    if (res.state) S.state = res.state;
    W.learned++;
    W.last = { id: m.id, keys: g.hat && m.dir ? [key] : keys };
    W.note = null;
    W.i++;
  }
  window.removeEventListener("mousemove", onMouse);
  API.cancel_capture(); S.capture = null;
  await wizDone(slot);
}

function wizShell(st, g, m, right) {
  const W = S.wiz;
  const box = $("#wizard");
  box.innerHTML = "";
  box.hidden = false;
  const src = imgFor(st);
  const asp = S.aspect[src] || 0.78;
  const P = Math.min(560, Math.max(320, Math.min(window.innerHeight - 190, window.innerWidth * 0.42)));
  const span = 0.36;                               // share of the photo's width that fits in the zoom
  const iw = P / span, ih = iw / asp;
  let left = P / 2 - g.dot[0] * iw, top = P / 2 - g.dot[1] * ih;
  left = Math.min(0, Math.max(P - iw, left)); top = Math.min(0, Math.max(P - ih, top));
  const zoom = h("div", { class: "wz-zoom", style: `width:${P}px;height:${P}px` },
    h("img", { src, alt: "", style: `left:${left}px;top:${top}px;width:${iw}px;height:${ih}px` }));
  for (const o of groupsOf(st)) {
    const x = left + o.dot[0] * iw, y = top + o.dot[1] * ih;
    if (x < 8 || y < 8 || x > P - 8 || y > P - 8) continue;
    if (o.id === g.id) zoom.append(h("div", { class: "wz-ring", style: `left:${x}px;top:${y}px` }),
      h("div", { class: "wz-tag", style: `left:${x}px;top:${y}px` }, "THIS ONE"));
    else zoom.append(h("div", { class: "wz-other", style: `left:${x}px;top:${y}px`, title: o.name }, h("i"), h("span", {}, o.name)));
  }
  const tw = 86, th = tw / asp;
  zoom.append(h("div", { class: "wz-mini", style: `width:${tw}px;height:${th}px` },
    h("img", { src, alt: "" }), h("b", { style: `left:${g.dot[0] * tw}px;top:${g.dot[1] * th}px` })));
  const n = W.todo.filter((t) => !W.gone.has(t.id)).length;
  const at = W.todo.slice(0, W.i).filter((t) => !W.gone.has(t.id)).length + 1;
  const head = h("div", { class: "wz-head" },
    h("span", { class: "wz-step" }, `${sideName(st).toUpperCase()} STICK · ${Math.min(at, n)} OF ${n}`),
    h("div", { class: "wz-bar" }, h("i", { style: `width:${Math.round((100 * (at - 1)) / Math.max(1, n))}%` })));
  box.append(h("div", { class: "wz-box" }, zoom, h("div", { class: "wz-side" }, head, right)));
}

function compass(st, g, m) {
  const W = S.wiz;
  const cells = ["up-left", "up", "up-right", "left", "push", "right", "down-left", "down", "down-right"];
  return h("div", { class: "wz-compass" }, cells.map((d) => {
    const c = g.members.find((x) => x.dir === d);
    if (!c) return h("div", { class: "wz-cell none" });
    const key = c.inputs.base;
    return h("div", { class: ["wz-cell", c.id === m.id && "now", key && "done"].filter(Boolean).join(" "), "data-key": key || "" },
      h("b", {}, DIR_ARROW[d] || "●"), h("span", {}, key ? shortKey(key) : c.id === m.id ? "PUSH" : ""));
  }));
}

function wizStep(st, g, m) {
  return new Promise((resolve) => {
    const W = S.wiz;
    S.coach = { slot: st.slot, cid: m.id };
    API.arm_capture(st.slot, m.kind === "axis" ? "axis" : "button");
    const finish = (v) => { API.cancel_capture(); S.capture = null; resolve(v); };
    S.capture = (got) => resolve(got);
    const dirWord = m.dir === "push" ? "straight in" : m.dir;
    const title = g.hat && m.dir ? `Push it ${dirWord}` : isAnalog(g, m) ? `Analog mode: ${m.label.replace(/^analog /, "")}` : m.kind === "axis" ? "Move it end to end" : g.hat ? `${m.label}` : "Press it once";
    const how = (g.hat && DIAGONAL(m.dir) ? "If it only clicks four ways, choose “No diagonals (4-way hat)” below. " : "") + (m.how || (g.hat && m.dir === "push" ? "Press the hat straight down into the stick, without tilting it."
      : g.hat && m.dir ? `Tilt the hat ${m.dir} and let go.` : "Press it and let go."));
    const right = [
      h("h2", { class: "wz-name" }, g.name),
      h("div", { class: "wz-do" }, title),
      h("p", { class: "wz-how" }, how),
      g.hat && m.dir ? compass(st, g, m) : null,
      isMini(g) ? h("div", { class: "wz-warn", id: "wzMouse", hidden: true },
        h("b", {}, "Your pointer just moved."), isAnalog(g, m)
          ? " The mini-stick is in mouse mode. Press it straight in to switch modes until moving it no longer moves the pointer or clicks, then push it again."
          : " If that was the mini-stick, it is in mouse mode. Press it straight in to switch to hat mode, then push it again.") : null,
      W.note ? h("div", { class: "wz-note " + W.note.kind }, W.note.text) : null,
      h("div", { class: "wz-raw" }, h("span", {}, "STICK IS SENDING"), h("div", { id: "wzRaw" }, h("em", {}, "nothing yet"))),
      h("div", { class: "wz-btns" },
        h("button", { class: "btn", disabled: W.i === 0 ? true : null, onclick: () => finish("back") }, "Back"),
        h("button", { class: "btn", onclick: () => finish("skip") }, "Skip for now"),
        h("button", { class: "btn", onclick: () => finish("absent") }, isAnalog(g, m) ? "No analog mode" : g.hat && DIAGONAL(m.dir) ? "No diagonals (4-way hat)" : g.hat ? "My stick doesn't have this" : "Not on my stick"),
        h("button", { class: "btn", onclick: () => finish("stop") }, "Stop")),
    ];
    wizShell(st, g, m, right);
    wizLive();
  });
}

function wizAsk(st, g, m, title, text) {
  return new Promise((resolve) => {
    S.coach = { slot: st.slot, cid: m.id };
    wizShell(st, g, m, [
      h("h2", { class: "wz-name" }, g.name),
      h("div", { class: "wz-do warn" }, title),
      h("p", { class: "wz-how" }, text),
      g.hat && g.members.some((x) => x.dir) ? compass(st, g, m) : null,
      h("div", { class: "wz-btns" },
        h("button", { class: "btn go", onclick: () => resolve("again") }, "Try again"),
        h("button", { class: "btn", onclick: () => resolve("use") }, "No, that was right")),
    ]);
  });
}

/* live parts of the wizard: what the stick is sending right now, and the mouse-mode hint */
function wizLive() {
  const W = S.wiz;
  if (!W || $("#wizard").hidden) return;
  const raw = $("#wzRaw");
  const keys = [...(S.live[W.slot] || [])];
  if (raw) {
    if (keys.length) { raw.innerHTML = ""; keys.forEach((k) => raw.append(h("b", {}, shortKey(k)))); W.sent = keys; }
    else if (W.sent) { raw.innerHTML = ""; W.sent.forEach((k) => raw.append(h("b", { class: "old" }, shortKey(k)))); raw.append(h("em", {}, "last press")); }
  }
  document.querySelectorAll("#wizard .wz-cell").forEach((c) => c.classList.toggle("hot", !!c.dataset.key && keys.includes(c.dataset.key)));
  const warn = $("#wzMouse");
  if (warn) warn.hidden = !(W.mouseAt && Date.now() - W.mouseAt < 2500 && !keys.length);
}

async function wizDone(slot) {
  const W = S.wiz;
  S.coach = null;
  S.state = await API.get_state();
  const st = stickBySlot(slot);
  const left = st ? st.unassigned.length : 0;
  const other = sticks().find((x) => x.slot !== slot && x.unassigned.length);
  const close = () => { $("#wizard").hidden = true; S.wiz = null; render(); };
  const box = $("#wizard");
  box.innerHTML = "";
  box.hidden = false;
  box.append(h("div", { class: "wz-box done" }, h("div", { class: "wz-side" },
    h("h2", { class: "wz-name" }, left ? `${sideName(st)} stick: ${W.learned} learned, ${left} left` : `${sideName(st)} stick is set up`),
    h("p", { class: "wz-how" }, left ? "Run Set up again any time to finish the rest." : "Every control on the picture now knows its button. You won't need to do this again."),
    h("div", { class: "wz-btns" },
      other ? h("button", { class: "btn go", onclick: () => { close(); setupFlow(other); } }, `Set up the ${sideName(other)} stick`) : null,
      !other && S.afterSetup ? h("button", { class: "btn go", onclick: async () => { const id = S.afterSetup; S.afterSetup = null; close(); apply(await API.apply_layout(id)); } }, "Apply the layout you picked") : null,
      !other && !S.afterSetup ? h("button", { class: "btn go", onclick: () => { close(); layoutsFlow(); } }, "Pick a starting layout") : null,
      h("button", { class: "btn", onclick: copyMaps }, "Copy my stick maps"),
      h("button", { class: "btn", onclick: close }, "Done")))));
}

/* the learned button numbers as text, to paste into a bug report or send to the developers */
async function copyMaps() {
  const out = {};
  for (const s of sticks()) out[s.name] = Object.fromEntries(s.controls.filter((c) => Object.keys(c.inputs).length).map((c) => [c.id, c.inputs]));
  const text = "Stick Citizen " + S.state.version + " stick maps\n" + JSON.stringify(out, null, 1);
  let ok = false;
  try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {
    const ta = h("textarea", { style: "position:fixed;left:-999px" }); ta.value = text; document.body.append(ta); ta.select();
    try { ok = document.execCommand("copy"); } catch (e2) { ok = false; }
    ta.remove();
  }
  toast(ok ? "Stick maps copied. Paste them anywhere." : "Couldn't copy. The maps are in %APPDATA%\\StickCitizen\\templates");
}

async function addDirFlow(slot, g) {
  const got = await waitForPress(slot, `Add a direction to ${g.name}`, "Press the hat in the new direction.");
  if (!got) return;
  closeModal();
  const dir = got.key[0] === "h" ? HAT_DIR[got.key.slice(-1)] : "";
  apply(await API.map_control(got.slot, got.key, dir || shortKey(got.key), g.name, dir, ""));
  renderDrawer();
}

function renameFlow(slot, g) {
  const m = g.members[0];
  const name = h("input", { value: g.hat ? g.name : m.label });
  const save = async () => {
    const v = name.value.trim();
    if (!v) return;
    let res;
    if (g.hat) for (const x of g.members) res = await API.edit_control(slot, x.id, null, v, null, false, false);
    else res = await API.edit_control(slot, m.id, v, null, null, false, false);
    closeModal();
    S.sel = { slot, group: g.hat ? v : g.id };
    await apply(res);
    renderDrawer();
  };
  modal([h("h2", {}, "Rename"), h("label", { class: "field" }, g.hat ? "Group name" : "Control name", name),
    h("div", { class: "row" }, h("button", { class: "btn", onclick: closeModal }, "Cancel"), h("button", { class: "btn go", onclick: save }, "Save"))]);
  setTimeout(() => name.select(), 0);
  name.addEventListener("keydown", (e) => e.key === "Enter" && save());
}

async function setPhoto(stick) {
  const res = await API.choose_photo(stick.slot);
  if (!res || !res.ok) { if (res && res.msg) toast(res.msg); return; }
  delete S.images[stick.name];
  S.state = res.state;
  await refresh();
  render();
  toast(res.msg);
}

function startDrag(e, stick, g, dot) {
  e.preventDefault();
  const img = [...document.querySelectorAll("#stage .stick")][shown().indexOf(stick)];
  const r = img.getBoundingClientRect();
  const sr = $("#stage").getBoundingClientRect();
  dot.setPointerCapture(e.pointerId);
  const move = (ev) => {
    const fx = (ev.clientX - r.left) / r.width, fy = (ev.clientY - r.top) / r.height;
    g._fx = Math.min(1, Math.max(0, fx)); g._fy = Math.min(1, Math.max(0, fy));
    dot.style.left = ev.clientX - sr.left + "px";
    dot.style.top = ev.clientY - sr.top + "px";
  };
  const up = async () => {
    dot.removeEventListener("pointermove", move);
    dot.removeEventListener("pointerup", up);
    if (g._fx == null) return;
    for (const m of g.members) m.dot = [g._fx, g._fy];
    await API.set_dot(stick.slot, g.members[0].id, g._fx, g._fy);
    render();
  };
  dot.addEventListener("pointermove", move);
  dot.addEventListener("pointerup", up);
}

/* ---------------- live input ---------------- */
async function pollLoop() {
  for (;;) {
    try {
      const r = await API.poll();
      if (r.captured && S.capture) { const f = S.capture; S.capture = null; f(r.captured); }
      let dirty = false;
      for (const ev of r.events) {
        const set = S.live[ev.slot] || (S.live[ev.slot] = new Set());
        if (ev.on) { set.add(ev.key); onPress(ev.slot, ev.key); if (S.wiz && ev.slot === S.wiz.slot) S.wiz.sent = [...set]; } else set.delete(ev.key);
        dirty = true;
      }
      S.axes = r.axes || {};
      if (r.reload) { await refresh(); dirty = true; }
      if (dirty) { renderStage(); if (S.othersOpen) renderOthers(); }
      renderMeters();
      if (S.wiz) wizLive();
    } catch (err) { /* backend busy; try again */ }
    await new Promise((res) => setTimeout(res, 16));
  }
}

function onPress(slot, key) {
  const stick = stickBySlot(slot);
  if (!stick) return;
  const c = stick.controls.find((x) => Object.values(x.inputs).includes(key));
  const layer = c && c.inputs.shift === key ? "shift" : "base";
  const where = c ? (c.group ? `${c.group} ${DIR_ARROW[c.dir] || ""}` : c.label) : shortKey(key);
  const b = bindsFor(stick, key)[0];
  const live = $("#live");
  live.className = "live" + (layer === "shift" ? " shift" : "") + (b ? "" : " none");
  live.textContent = b ? (layer === "shift" ? "⇧ " : "") + b.label : "unbound";
  $("#liveSub").textContent = `${where}${layer === "shift" ? " ⇧" : ""} · ${stick.side === "L" ? "left" : stick.side === "R" ? "right" : "js" + slot} stick`;
  if (b && S.state.speech) API.say(b.action);
  // a single-stick view follows the stick you touch
  if (S.stick !== "both" && S.stick !== slot && sticks().length > 1 && S.view === "sticks") { S.stick = slot; render(); }
}

function renderMeters() {
  const box = $("#meters");
  const list = shown();
  const s = list.length === 1 ? list[0] : list.find((x) => x.side === "R") || list[0];
  const ax = s ? S.axes[s.slot] || [] : [];
  const names = ["ROLL", "PITCH", "YAW"];
  if (!box.children.length) for (const n of names) box.append(h("div", { class: "meter" }, h("span", {}, n), h("div", { class: "trk" }, h("div", { class: "val" }))));
  [0, 1, 5].forEach((ai, i) => {
    const v = Math.max(-1, Math.min(1, ax[ai] || 0));
    const bar = box.children[i] && box.children[i].querySelector(".val");
    if (!bar) return;
    bar.style.left = (v < 0 ? 40 + v * 40 : 40) + "px";
    bar.style.width = Math.max(3, Math.abs(v) * 40) + "px";
  });
}

/* ---------------- misc ---------------- */
let toastT = null;
function toast(msg) {
  if (!msg) return;
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastT);
  toastT = setTimeout(() => (t.hidden = true), 3200);
}

/* wipe one stick's learned map back to the built-in profile, then run setup */
function resetFlow() {
  const go = async (st) => {
    closeModal();
    const res = await API.reset_stick(st.slot);
    delete S.images[st.name];
    await refresh();
    render();
    if (res.msg) toast(res.msg);
    const fresh = stickBySlot(st.slot);
    if (fresh && fresh.unassigned.length) setupFlow(fresh);
  };
  modal([h("h2", {}, "Start a stick over"),
    h("p", {}, "Forgets the buttons Stick Citizen learned for that stick and runs Set up again. The old map is kept in the backups folder. Your bindings are not touched."),
    h("div", { class: "lay-list" }, sticks().map((st) => h("button", { class: "lay", onclick: () => go(st) },
      h("b", {}, `${sideName(st)[0].toUpperCase() + sideName(st).slice(1)} stick`), h("span", {}, st.name)))),
    h("div", { class: "row" }, h("button", { class: "btn", onclick: closeModal }, "Cancel"))]);
}

async function layoutsFlow() {
  const list = await API.list_layouts();
  const pick = async (l, force) => {
    const need = sticks().filter((x) => x.unassigned.length > 3);
    if (l.id !== "blank" && need.length && !force) {
      modal([h("h2", {}, "Set up your sticks first"),
        h("p", {}, `${l.name} puts actions on real buttons, and Stick Citizen doesn't know yours yet (${need.map((x) => `${sideName(x)}: ${x.unassigned.length} to learn`).join(", ")}). Set up takes a couple of minutes per stick.`),
        h("div", { class: "row" }, h("button", { class: "btn", onclick: () => pick(l, true) }, "Apply anyway"),
          h("button", { class: "btn go", onclick: () => { closeModal(); S.afterSetup = l.id; setupFlow(need[0]); } }, "Set up now"))]);
      return;
    }
    closeModal();
    apply(await API.apply_layout(l.id));
  };
  modal([h("h2", {}, "Start from a layout"),
    h("p", {}, "Replaces your current joystick bindings. Undo brings them back."),
    h("div", { class: "lay-list" }, list.map((l) => h("button", { class: "lay", onclick: () => pick(l) },
      h("b", {}, l.name), h("span", {}, l.description), l.for ? h("i", {}, l.for) : null, l.credit ? h("small", {}, l.credit) : null)),
      h("button", { class: "lay", onclick: async () => { closeModal(); const r = await API.open_layout(); S.images = {}; if (r && r.ok) await refresh(); apply(r); } },
        h("b", {}, "From a file…"), h("span", {}, "Open an exported Star Citizen layout or your actionmaps.xml (someone else's layout works too)."))),
    h("div", { class: "row" }, h("button", { class: "btn", onclick: closeModal }, "Cancel"))]);
}

function wire() {
  $("#btnLayouts").onclick = layoutsFlow;
  document.querySelectorAll("#views button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
  $("#btnSave").onclick = async () => apply(await API.save_layout());
  $("#btnOpen").onclick = async () => { const r = await API.open_layout(); S.images = {}; if (r && r.ok) await refresh(); apply(r); };
  $("#btnUndo").onclick = async () => apply(await API.undo());
  $("#btnVoice").onclick = async () => { await API.set_speech(!S.state.speech); S.state.speech = !S.state.speech; render(); };
  window.addEventListener("resize", () => renderStage());
  document.addEventListener("keydown", async (e) => {
    if (e.target.tagName === "INPUT") return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); apply(await API.undo()); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); apply(await API.save_layout()); }
    if (e.key === "Escape") { if (!$("#modal").hidden) closeModal(); else closeDrawer(); }
  });
  // edit mode gets a "Map a control" button in the bar
  const mapBtn = h("button", { class: "chip", id: "btnMap", style: "border-style:dashed;color:var(--cyan-soft)", onclick: () => mapFlow() }, "+ Map a control");
  $(".bar").insertBefore(mapBtn, $("#hint"));
  const setupBtn = h("button", { class: "chip setup", id: "btnSetup", onclick: () => {
    const s = shown().find((x) => x.unassigned.length) ; if (s) setupFlow(s); } }, "");
  $(".bar").insertBefore(setupBtn, $("#hint"));
  const resetBtn = h("button", { class: "chip", id: "btnReset", onclick: resetFlow }, "Start a stick over");
  $(".bar").insertBefore(resetBtn, $("#hint"));
  resetBtn.hidden = true;
  const copyBtn = h("button", { class: "chip", id: "btnCopyMaps", onclick: copyMaps }, "Copy stick maps");
  $(".bar").insertBefore(copyBtn, $("#hint"));
  copyBtn.hidden = true;
  const obs = new MutationObserver(() => { mapBtn.hidden = copyBtn.hidden = resetBtn.hidden = S.view !== "edit"; });
  obs.observe($("#app"), { attributes: true, attributeFilter: ["class"] });
  mapBtn.hidden = true;
}
