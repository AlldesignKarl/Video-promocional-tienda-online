// Renderiza src/promo.html fotograma a fotograma.
//
//   node tools/render_promo.cjs --stills 0.5,3,8 --out build/stills   → PNG sueltos para revisar
//   node tools/render_promo.cjs --frames 0:100                         → flujo binario por stdout
//
// En modo --frames cada fotograma sale como varias submuestras (desenfoque de movimiento con
// obturador de 180°) que tools/build.py promedia: [u32 índice][u32 n] y n × ([u32 bytes][PNG]).
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const sim = require("./store_sim.cjs");

function arg(name, def) {
  const i = process.argv.indexOf(name);
  return i === -1 ? def : process.argv[i + 1];
}

(async () => {
  const { srv, base } = await sim.startServer();
  const browser = await chromium.launch({ args: ["--force-color-profile=srgb", "--disable-lcd-text"] });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  page.on("pageerror", (e) => process.stderr.write("pageerror: " + e.message + "\n"));
  page.on("console", (m) => { if (m.type() === "error") process.stderr.write("console: " + m.text() + "\n"); });
  await page.goto(base + "/src/promo.html", { waitUntil: "load" });
  await page.evaluate(() => window.PROMO.init());
  const cdp = await page.context().newCDPSession(page);
  const grab = async () => Buffer.from((await cdp.send("Page.captureScreenshot", { format: "png", optimizeForSpeed: true })).data, "base64");
  const render = (t) => page.evaluate((x) => window.PROMO.renderAt(x), t);

  const stills = arg("--stills");
  if (stills) {
    const out = path.resolve(arg("--out", "build/stills"));
    fs.mkdirSync(out, { recursive: true });
    for (const s of stills.split(",")) {
      const t = Number(s);
      await render(t);
      fs.writeFileSync(path.join(out, "t" + t.toFixed(2).padStart(5, "0") + ".png"), await grab());
      process.stderr.write("still " + t + "\n");
    }
  } else {
    const [a, b] = arg("--frames").split(":").map(Number);
    const { fps } = await page.evaluate(() => ({ fps: window.PROMO.fps }));
    const shutter = 0.5;
    const u32 = (n) => { const x = Buffer.alloc(4); x.writeUInt32LE(n); return x; };
    for (let i = a; i < b; i++) {
      const t = i / fps;
      const n = await page.evaluate((x) => window.PROMO.samplesAt(x), t);
      const parts = [u32(i), u32(n)];
      for (let k = 0; k < n; k++) {
        const off = n === 1 ? 0 : ((k + 0.5) / n - 0.5) * shutter / fps;
        await render(Math.max(0, t + off));
        const png = await grab();
        parts.push(u32(png.length), png);
      }
      const buf = Buffer.concat(parts);
      if (!process.stdout.write(buf)) await new Promise((r) => process.stdout.once("drain", r));
    }
  }
  await browser.close();
  srv.close();
})().catch((e) => { process.stderr.write(String(e && e.stack || e) + "\n"); process.exit(1); });
