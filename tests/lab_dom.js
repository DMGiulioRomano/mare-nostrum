// La pagina del laboratorio INTERA, in node, su un DOM finto.
//
//   node tests/lab_dom.js <pagina.html> <scenario.js>
//
// I test di `test_graph_js.py` estraggono di solito una funzione e le danno
// intorno quel poco che le serve. Per il giro completo — un documento aperto
// (`carica`), toccato o no, e riscritto (`labDoc`) — i frammenti non bastano:
// passa per i select, le voci, il loop, la storia, la bozza. Qui gira lo
// script com'e', con `__DATA__` gia' sostituito, e lo scenario dopo, nello
// stesso contesto: vede le sue funzioni e le sue variabili come le vedrebbe
// la console del browser.
//
// Il DOM e' finto ma non permissivo dove conta: un <select> a cui si assegna
// un valore che non e' fra le sue opzioni vale "", come in un browser vero
// (e' cosi' che un sample fuori dalla cartella dello studio arriva a
// `labDoc`); `getElementById` di un id che non esiste da' null, perche' la
// pagina ci conta (le voci senza menu di interpolazione). Il resto — canvas,
// Web Audio, rete — risponde qualunque cosa e non fa niente.
"use strict";
const fs = require("fs");
const vm = require("vm");

const REG = new Map();          // id -> elemento

// --- un oggetto che accetta tutto: AudioContext, contesti dei canvas -------
function stub() {
  const store = {};
  const f = function () {};
  return new Proxy(f, {
    get(t, k) {
      if (k === Symbol.toPrimitive) return () => 0;
      if (typeof k === "symbol") return undefined;
      if (k === "then") return undefined;          // non e' una promessa
      if (!(k in store)) store[k] = stub();
      return store[k];
    },
    set(t, k, v) { store[k] = v; return true; },
    apply() { return stub(); },
    construct() { return stub(); },
  });
}

class ClassList {
  constructor(el) { this.el = el; }
  _get() { return (this.el.className || "").split(/\s+/).filter(Boolean); }
  _set(a) { this.el.className = a.join(" "); }
  add(...c) { const a = this._get(); for (const x of c) if (!a.includes(x)) a.push(x); this._set(a); }
  remove(...c) { this._set(this._get().filter(x => !c.includes(x))); }
  contains(c) { return this._get().includes(c); }
  toggle(c, on) {
    const has = this.contains(c);
    const want = on === undefined ? !has : !!on;
    if (want && !has) this.add(c);
    if (!want && has) this.remove(c);
    return want;
  }
}

class El {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.style = {};
    this.dataset = {};
    this.className = "";
    this.classList = new ClassList(this);
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.title = "";
    this.type = "";
    this.textContent = "";
    this.width = 300; this.height = 150;
    this.clientWidth = 800; this.clientHeight = 200;
    this._id = "";
    this._value = "";
    this._sel = undefined;        // <select>: indice scelto, undefined = il primo
    this._ls = {};
    this.paused = true; this.src = ""; this.currentTime = 0;   // <audio>
  }
  get id() { return this._id; }
  set id(v) { this._id = String(v); REG.set(this._id, this); }
  get options() { return this.children.filter(c => c.tagName === "OPTION"); }
  get selectedIndex() {
    const n = this.options.length;
    if (this._sel === undefined) return n ? 0 : -1;
    return this._sel < n ? this._sel : -1;
  }
  set selectedIndex(i) { this._sel = i; }
  get value() {
    if (this.tagName === "SELECT") {
      const i = this.selectedIndex;
      return i >= 0 ? this.options[i].value : "";
    }
    return this._value;
  }
  set value(v) {
    if (this.tagName === "SELECT") {
      this._sel = this.options.findIndex(o => o.value === String(v));
      return;
    }
    this._value = v === null || v === undefined ? "" : String(v);
  }
  get firstChild() { return this.children[0] || null; }
  get lastChild() { return this.children[this.children.length - 1] || null; }
  set innerHTML(html) {
    for (const c of this.children) c.parentNode = null;
    this.children = [];
    parseInto(this, String(html));
  }
  get innerHTML() { return ""; }
  appendChild(c) {
    if (c.parentNode) c.remove();
    c.parentNode = this;
    this.children.push(c);
    return c;
  }
  append(...cs) { for (const c of cs) if (c instanceof El) this.appendChild(c); }
  after(el) {
    const p = this.parentNode;
    if (!p) return;
    if (el.parentNode) el.remove();
    el.parentNode = p;
    p.children.splice(p.children.indexOf(this) + 1, 0, el);
  }
  remove() {
    const p = this.parentNode;
    if (!p) return;
    p.children.splice(p.children.indexOf(this), 1);
    this.parentNode = null;
  }
  closest(sel) {
    for (let e = this; e; e = e.parentNode) if (matches(e, sel)) return e;
    return null;
  }
  querySelectorAll(sel) { return queryAll(this, sel); }
  querySelector(sel) { return queryAll(this, sel)[0] || null; }
  addEventListener(t, f) { (this._ls[t] = this._ls[t] || []).push(f); }
  removeEventListener(t, f) { this._ls[t] = (this._ls[t] || []).filter(g => g !== f); }
  dispatchEvent(e) {
    if (typeof this["on" + e.type] === "function") this["on" + e.type](e);
    for (const f of this._ls[e.type] || []) f(e);
    return true;
  }
  getBoundingClientRect() { return {left: 0, top: 0, width: 800, height: 200}; }
  getContext() { return stub(); }
  focus() {} blur() {} click() { this.dispatchEvent(new Event("click")); }
  play() { this.paused = false; return Promise.resolve(); }
  pause() { this.paused = true; }
}

// --- selettori: quanto basta alla pagina (tag, .classe, #id, discendenti) --
function matchesSimple(el, s) {
  const m = s.match(/^([a-zA-Z0-9]*)((?:[.#][\w:-]+)*)$/);
  if (!m) return false;
  if (m[1] && el.tagName !== m[1].toUpperCase()) return false;
  for (const part of m[2].match(/[.#][\w:-]+/g) || []) {
    if (part[0] === "#" && el.id !== part.slice(1)) return false;
    if (part[0] === "." && !el.classList.contains(part.slice(1))) return false;
  }
  return true;
}

function matches(el, sel) {
  const parts = sel.trim().split(/\s+/);
  if (!matchesSimple(el, parts[parts.length - 1])) return false;
  let i = parts.length - 2;
  for (let p = el.parentNode; p && i >= 0; p = p.parentNode)
    if (matchesSimple(p, parts[i])) i--;
  return i < 0;
}

function queryAll(root, sel) {
  const out = [];
  const visit = e => { for (const c of e.children) { if (matches(c, sel)) out.push(c); visit(c); } };
  visit(root);
  return out;
}

// --- un parser HTML minimo: tag, attributi id/class, testo ----------------
const VOID = new Set(["br", "input", "img", "hr", "meta", "link"]);
function parseInto(root, html) {
  html = html.replace(/<!--[\s\S]*?-->/g, "");
  const re = /<\/([a-zA-Z0-9]+)\s*>|<([a-zA-Z0-9]+)([^>]*)>|([^<]+)/g;
  const stack = [root];
  let m;
  while ((m = re.exec(html))) {
    const top = stack[stack.length - 1];
    if (m[1]) {
      if (stack.length > 1) stack.pop();
    } else if (m[2]) {
      const el = new El(m[2]);
      const attrs = m[3] || "";
      const at = name => {
        const r = attrs.match(new RegExp("\\b" + name + "\\s*=\\s*(\"([^\"]*)\"|'([^']*)')"));
        return r ? (r[2] !== undefined ? r[2] : r[3]) : null;
      };
      if (at("id") !== null) el.id = at("id");
      if (at("class") !== null) el.className = at("class");
      if (at("type") !== null) el.type = at("type");
      for (const n of ["width", "height"]) if (at(n) !== null) el[n] = Number(at(n));
      if (/\bhidden\b/.test(attrs.replace(/"[^"]*"|'[^']*'/g, ""))) el.hidden = true;
      top.appendChild(el);
      if (!VOID.has(m[2].toLowerCase()) && !/\/\s*$/.test(attrs)) stack.push(el);
    } else if (m[4] && m[4].trim()) {
      top.textContent += m[4];
    }
  }
}

// --- document e window -----------------------------------------------------
const body = new El("body");
const document = {
  body,
  activeElement: null,
  getElementById: id => REG.get(String(id)) || null,
  createElement: tag => new El(tag),
  querySelectorAll: sel => queryAll(body, sel),
  querySelector: sel => queryAll(body, sel)[0] || null,
  addEventListener() {}, removeEventListener() {},
};

class Event { constructor(type) { this.type = type; } preventDefault() {} }

function Option(text, value) {
  const o = new El("option");
  o.textContent = text === undefined ? "" : String(text);
  o._value = value === undefined ? o.textContent : String(value);
  return o;
}

const storage = new Map();
const g = globalThis;
Object.assign(g, {
  window: g,
  document,
  Event,
  Option,
  localStorage: {
    getItem: k => (storage.has(k) ? storage.get(k) : null),
    setItem: (k, v) => storage.set(k, String(v)),
    removeItem: k => storage.delete(k),
  },
  AudioContext: function () { return stub(); },
  ResizeObserver: class { observe() {} },
  Path2D: function () { return stub(); },
  requestAnimationFrame() { return 0; },
  addEventListener() {}, removeEventListener() {},
  confirm: () => true,
  alert() {},
  getComputedStyle: () => ({color: "#000", backgroundColor: "#fff"}),
  innerWidth: 1280, innerHeight: 800, devicePixelRatio: 1,
  // Nessun server: `stato()` e `post()` lo trattano come `file://`.
  fetch: () => Promise.reject(new Error("niente rete nel test")),
});

// --- la pagina, poi lo scenario -------------------------------------------
// `prima`, se c'e', gira prima della pagina: e' il posto per preparare quello
// che la pagina legge appena si apre (la bozza in localStorage, il /stato del
// server), cioe' un refresh.
const [pagina, scenario, prima] = process.argv.slice(2);
if (prima) vm.runInThisContext(fs.readFileSync(prima, "utf8"), {filename: "prima.js"});
const html = fs.readFileSync(pagina, "utf8");
const markup = html.slice(html.indexOf("</style>") + "</style>".length, html.indexOf("<script>"));
parseInto(body, markup);
const script = html.slice(html.indexOf("<script>") + "<script>".length, html.lastIndexOf("</script>"));
vm.runInThisContext(script, {filename: "graph_page.js"});
// `avvio()` e' asincrona (chiede /stato al server): lo scenario parte quando
// ha finito, come l'utente che apre un file a pagina gia' carica.
setTimeout(() => vm.runInThisContext(fs.readFileSync(scenario, "utf8"),
                                     {filename: "scenario.js"}), 0);
