// Graba la tienda (vista de móvil) fotograma a fotograma con un reloj virtual.
//
// Todas las animaciones CSS de la tienda (título "tinta", destellos, apariciones al hacer
// scroll, ficha de producto, cesta...) se pausan y se colocan en el instante exacto de cada
// fotograma, así la grabación sale perfecta e idéntica en cada render.
//
// Uso: NODE_PATH=$(npm root -g) node tools/capture_store.cjs build/store
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const sim = require("./store_sim.cjs");

const OUT = path.resolve(process.argv[2] || "build/store");
const VIEW = { width: 390, height: 797 }; // pantalla del móvil sin la barra de estado
const DPR = 3;
const ONLY = process.env.SHOTS ? process.env.SHOTS.split(",") : null;

const INIT = `
(() => {
  // Aleatorio con semilla: los destellos dorados salen siempre igual.
  let s = 20261008;
  Math.random = () => { s |= 0; s = (s + 0x6D2B79F5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  // La clase "loaded" (que arranca la animación de portada) espera a que empiece la grabación.
  const add = DOMTokenList.prototype.add;
  window.__hold = true;
  DOMTokenList.prototype.add = function (...a) {
    if (window.__hold && this === document.documentElement.classList && a.includes("loaded")) { window.__pending = true; return; }
    return add.apply(this, a);
  };
  window.__go = () => { window.__hold = false; document.documentElement.classList.add("loaded"); };
  // Reloj virtual: cada animación guarda el instante (virtual) en que apareció.
  const seen = new Map();
  window.__clock = {
    // Empieza un plano nuevo: lo que ya estaba en marcha sigue desde donde iba.
    rebase() {
      for (const a of document.getAnimations()) { a.pause(); seen.set(a, -((a.currentTime || 0) / 1000)); }
    },
    seek(vt) {
      for (const a of document.getAnimations()) {
        if (!seen.has(a)) seen.set(a, vt);
        a.pause();
        a.currentTime = Math.max(0, (vt - seen.get(a)) * 1000);
      }
    },
  };
})();
`;

const CSS = `
html{scroll-behavior:auto!important}
.hero-parallax{transition:none!important}
/* Los precios de las piezas están en Wix y no se inventan: no se muestran en el vídeo. */
.card-price,#pd-price{display:none!important}
`;

const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
// Recorrido por tramos [t0, t1, desde, hasta] con aceleración y frenada suaves.
function path1d(segs, t) {
  let v = segs[0][2];
  for (const [t0, t1, a, b] of segs) {
    if (t >= t1) v = b;
    else if (t > t0) { v = a + (b - a) * ease((t - t0) / (t1 - t0)); break; }
    else break;
  }
  return v;
}

const raf2 = (page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));

async function waitImages(page) {
  await page.evaluate(async () => {
    document.querySelectorAll("img[loading=lazy]").forEach((i) => { i.loading = "eager"; });
    await Promise.all([...document.images].map((i) => (i.complete ? null : new Promise((r) => { i.onload = i.onerror = r; }))));
    await document.fonts.ready;
  });
}

const box = (page, sel) => page.evaluate((s) => {
  const e = document.querySelector(s);
  const b = e.getBoundingClientRect();
  return { x: b.x, y: b.y, w: b.width, h: b.height, top: b.top + scrollY };
}, sel);

async function shoot(page, name, spec, meta) {
  if (ONLY && !ONLY.includes(name)) return;
  const dir = path.join(OUT, name);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const n = Math.round(spec.duration * spec.fps);
  const actions = (spec.actions || []).slice().sort((a, b) => a.t - b.t);
  const taps = [];
  if (spec.before) await spec.before();
  await page.evaluate(() => window.__clock.rebase());
  for (let k = 0; k <= n; k++) {
    const vt = k / spec.fps;
    while (actions.length && actions[0].t <= vt + 1e-9) {
      const a = actions.shift();
      const r = await a.run();
      if (r && r.tap) taps.push({ t: a.t, x: r.tap.x, y: r.tap.y });
    }
    if (spec.scroll) await page.evaluate((y) => window.scrollTo(0, y), spec.scroll(vt));
    if (spec.sheet) await page.evaluate((y) => { document.querySelector(".modal-card").scrollTop = y; }, spec.sheet(vt));
    await raf2(page);
    await page.evaluate((t) => window.__clock.seek(t), vt);
    await page.screenshot({ path: path.join(dir, "f" + String(k).padStart(5, "0") + ".jpg"), type: "jpeg", quality: 95 });
  }
  meta[name] = { fps: spec.fps, frames: n + 1, duration: spec.duration, taps };
  console.log(name, n + 1, "fotogramas", JSON.stringify(taps));
}

// Pulsa en el centro de un elemento y devuelve dónde se ha pulsado (para dibujar el toque).
async function tap(page, sel, after) {
  const b = await box(page, sel);
  const x = b.x + b.w / 2, y = b.y + b.h / 2;
  await page.mouse.click(x, y);
  if (after) await after();
  return { tap: { x, y } };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const { srv, base } = await sim.startServer();
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: VIEW, deviceScaleFactor: DPR, isMobile: true, hasTouch: true, reducedMotion: "no-preference" });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.log("pageerror:", e.message));
  await page.addInitScript(INIT);
  const url = await sim.attach(page, base);
  await page.goto(url, { waitUntil: "networkidle" });
  await page.addStyleTag({ content: CSS });
  await page.waitForFunction(() => window.__pending && document.querySelectorAll(".card").length === 3);
  await waitImages(page);

  const L = await page.evaluate(() => {
    const top = (e) => e.getBoundingClientRect().top + scrollY;
    return {
      shop: top(document.getElementById("colecciones")),
      cards: [...document.querySelectorAll(".card")].map(top),
      gift: top(document.getElementById("tarjeta-regalo")),
      giftCard: top(document.querySelector(".gift-card")),
      amounts: top(document.getElementById("gc-amounts")),
      giftAdd: top(document.getElementById("gc-add")),
      contact: top(document.getElementById("contacto")),
    };
  });
  console.log("posiciones", JSON.stringify(L));
  const meta = { view: VIEW, dpr: DPR, layout: L };

  // 1 · Portada: la animación de entrada real de la tienda.
  await shoot(page, "portada", {
    fps: 60, duration: 4.4,
    before: async () => { await page.evaluate(() => window.__go()); },
  }, meta);

  // 2 · Bajando por la tienda hasta la letra de resina.
  const cardY = (i) => L.cards[i] - 150;
  await shoot(page, "colecciones", {
    fps: 120, duration: 2.2,
    scroll: (t) => path1d([[0.15, 0.95, 0, L.shop + 30], [1.2, 1.95, L.shop + 30, cardY(0)]], t),
  }, meta);

  // 3 · Ficha de la letra de resina: se eligen los dos colores y la foto cambia al momento.
  const resina = `.card[data-id="${sim.ID_RESINA}"]`;
  const imgSrc = () => page.evaluate(() => document.getElementById("pd-img").getAttribute("src") || "");
  const waitNewImg = async (prev) => {
    await page.waitForFunction((p) => {
      const i = document.getElementById("pd-img");
      return (i.getAttribute("src") || "") !== p && i.complete;
    }, prev, { timeout: 10000 });
  };
  const sheetTo = (sel, margin) => page.evaluate(([s, m]) => {
    const c = document.querySelector(".modal-card");
    const e = document.querySelector(s).getBoundingClientRect();
    const cb = c.getBoundingClientRect();
    return Math.max(0, Math.min(c.scrollHeight - c.clientHeight, Math.round(c.scrollTop + e.bottom - cb.bottom + m)));
  }, [sel, margin]);
  const S = { colors: 0, letter: 0 };
  const color = (name) => async () => {
    const prev = await imgSrc();
    await page.evaluate(() => document.getElementById("pd-img").classList.remove("swap"));
    return tap(page, `.swatch[title="${name}"]`, () => waitNewImg(prev));
  };
  await shoot(page, "ficha", {
    fps: 60, duration: 5.9,
    before: async () => { await page.evaluate((y) => window.scrollTo(0, y), cardY(0)); await raf2(page); },
    sheet: (t) => path1d([[0.85, 1.35, 0, S.colors], [4.55, 5.05, S.colors, S.letter]], t),
    actions: [
      { t: 0.15, run: async () => tap(page, resina + " .card-media", async () => {
        await page.waitForFunction(() => document.getElementById("product").classList.contains("open") && document.querySelectorAll(".swatch").length === 10);
        await page.waitForFunction(() => document.getElementById("pd-img").complete && document.getElementById("pd-img").getAttribute("src"));
        S.colors = await sheetTo(".swatches", 30);
        S.letter = await sheetTo("#pd-add", 26);
        console.log("ficha: colores", S.colors, "letra", S.letter);
      }) },
      // 1.º color = flores grandes, 2.º = ramitas. Pulsar el 1.º lo quita y el 2.º pasa a ser el 1.º.
      { t: 1.45, run: color("Amarillo") },
      { t: 2.0, run: color("Azul claro") },
      { t: 2.55, run: color("Amarillo") },
      { t: 3.1, run: color("Rosa oscuro") },
      { t: 3.65, run: color("Azul claro") },
      { t: 4.2, run: color("Morado") },
      { t: 5.15, run: async () => {
        const r = await tap(page, ".letter-input");
        await page.keyboard.type("A");
        return r;
      } },
      // El toque en "Añadir a la cesta" solo se dibuja en el vídeo (no se envía nada).
      { t: 5.65, run: async () => { const b = await box(page, "#pd-add"); return { tap: { x: b.x + b.w / 2, y: b.y + b.h / 2 } }; } },
    ],
  }, meta);

  const metaFile = path.join(OUT, "meta.json");
  const prev = fs.existsSync(metaFile) ? JSON.parse(fs.readFileSync(metaFile, "utf8")) : {};
  fs.writeFileSync(metaFile, JSON.stringify(Object.assign(prev, meta), null, 2));
  await browser.close();
  srv.close();
})().catch((e) => { console.error(e); process.exit(1); });
