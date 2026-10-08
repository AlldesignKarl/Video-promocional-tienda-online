// Simulador local de la tienda alldesignkarl.com para grabarla en el vídeo.
//
// Sirve la copia de la tienda (tienda/index.html) y responde a sus llamadas a Wix
// con un catálogo de prueba hecho con las fotos reales de la tienda (assets/img).
// No se conecta a ningún servicio externo: todo se resuelve en local.
//
// Los precios de las piezas viven en Wix y no están en el repositorio, así que no se
// inventan: la grabación oculta los precios de las piezas. Los importes de la tarjeta
// regalo sí son los reales (están copiados en el propio código de la tienda).
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const IMG = path.join(ROOT, "assets", "img");

const MIME = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".cjs": "text/javascript", ".css": "text/css",
  ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
  ".woff2": "font/woff2", ".json": "application/json", ".svg": "image/svg+xml", ".mp4": "video/mp4",
};

function startServer() {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      const u = decodeURIComponent(new URL(req.url, "http://x").pathname);
      const file = path.join(ROOT, u.endsWith("/") ? u + "index.html" : u);
      if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        res.writeHead(404); res.end("not found"); return;
      }
      res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream", "Access-Control-Allow-Origin": "*" });
      fs.createReadStream(file).pipe(res);
    });
    srv.listen(0, "127.0.0.1", () => resolve({ srv, base: "http://127.0.0.1:" + srv.address().port }));
  });
}

/* ---------------- catálogo de prueba ---------------- */
const COLORS = [
  ["Rojo", "rojo", "#D3272F"], ["Naranja", "naranja", "#F08A24"], ["Amarillo", "amarillo", "#F4C21B"],
  ["Verde claro", "verde-claro", "#86CF96"], ["Verde oscuro", "verde-oscuro", "#1F8A4C"],
  ["Azul claro", "azul-claro", "#8DC3EA"], ["Azul oscuro", "azul-oscuro", "#22409A"],
  ["Morado", "morado", "#8C57C8"], ["Rosa claro", "rosa-claro", "#F4B6C6"], ["Rosa oscuro", "rosa-oscuro", "#DE3F78"],
];
const ID_RESINA = "2435d64f-e41d-4995-b730-f3a8cc13ed5a";
const ID_DECORADA = "1ae0ea11-9aec-46e5-b2a1-33d8ce70b33b";
const ID_CACHIRULO = "f4d56313-6834-4f16-93d0-f07d02b35f0a";

const media = (f) => "https://static.wixstatic.com/media/adk_" + f;
const colorOption = () => ({
  id: "opt-color", name: "Color", optionRenderType: "SWATCH_CHOICES",
  choicesSettings: { choices: COLORS.map(([name, slug, hex]) => ({ choiceId: "c-" + slug, name, colorCode: hex, visible: true })) },
});
const letterMod = () => ({
  id: "mod-letra", name: "¿Qué letra quieres?", modifierRenderType: "FREE_TEXT", mandatory: true,
  freeTextSettings: { key: "letra", title: "Tu inicial", maxCharCount: 1 },
});
const noPrice = { minValue: { amount: "0" }, maxValue: { amount: "0" } };

const PRODUCTS = [
  {
    id: ID_RESINA, name: "Letra de resina", visible: true, currency: "EUR", actualPriceRange: noPrice,
    media: { main: { image: { url: media("letra-resina-dia.jpg") } }, itemsInfo: { items: [{ image: { url: media("letra-resina-iluminada.jpg") } }] } },
    options: [colorOption()],
    modifiers: [letterMod(), { id: "mod-2", name: "Segundo color", modifierRenderType: "FREE_TEXT", mandatory: false, freeTextSettings: { key: "segundo", title: "Segundo color", maxCharCount: 20 } }],
  },
  {
    id: ID_DECORADA, name: "Letra decorada", visible: true, currency: "EUR", actualPriceRange: noPrice,
    media: { main: { image: { url: media("letra-a-1-crema.jpg") } }, itemsInfo: { items: [{ image: { url: media("letra-a-2-crema.jpg") } }] } },
    options: [colorOption()],
    modifiers: [letterMod()],
  },
  {
    id: ID_CACHIRULO, name: "Ambientador del Cachirulo", visible: true, currency: "EUR", actualPriceRange: noPrice,
    media: { main: { image: { url: media("ambientador-cachirulo.jpg") } }, itemsInfo: { items: [] } },
    options: [], modifiers: [],
  },
];

function variantsFor(id) {
  const p = PRODUCTS.find((x) => x.id === id);
  if (!p) return [];
  if (!p.options.length) return [{ id: id + "-v", variantId: id + "-v", visible: true, optionChoices: [], price: { actualPrice: { amount: "0" } } }];
  return p.options[0].choicesSettings.choices.map((c) => ({
    id: "v-" + c.choiceId, variantId: "v-" + c.choiceId, visible: true,
    optionChoices: [{ optionChoiceIds: { optionId: "opt-color", choiceId: c.choiceId } }],
    price: { actualPrice: { amount: "0" } }, inventoryStatus: { inStock: true },
  }));
}

// Vistas previas por color: el código de la tienda las pide a Wix por su id; aquí se sirven
// las mismas fotos desde assets/img/colores.
function previewFiles(html) {
  const map = {};
  const re = /"(2435d64f-[^"]+|1ae0ea11-[^"]+)":\s*"([^"]+)"/g;
  let m;
  while ((m = re.exec(html))) {
    const kind = m[1].startsWith("2435") ? "resina" : "decorada";
    m[2].split(",").forEach((kv) => {
      const [key, hex] = kv.split(":");
      const slugs = key.split("").map((d) => COLORS[Number(d)][1]);
      map["43eaa1_" + hex + "~mv2.jpg"] = path.join(IMG, "colores", kind + "-" + slugs.join("-") + ".jpg");
    });
  }
  return map;
}

function fontCss(base) {
  const f = (file) => `url(${base}/assets/fonts/${file}) format('woff2')`;
  return [
    ["Cormorant Garamond", "normal", 400, "cormorant-garamond-latin-400-normal.woff2"],
    ["Cormorant Garamond", "normal", 500, "cormorant-garamond-latin-500-normal.woff2"],
    ["Cormorant Garamond", "normal", 600, "cormorant-garamond-latin-600-normal.woff2"],
    ["Cormorant Garamond", "italic", 400, "cormorant-garamond-latin-400-italic.woff2"],
    ["Cormorant Garamond", "italic", 500, "cormorant-garamond-latin-500-italic.woff2"],
    ["Pinyon Script", "normal", 400, "pinyon-script-latin-400-normal.woff2"],
  ].map(([fam, st, w, file]) => `@font-face{font-family:'${fam}';font-style:${st};font-weight:${w};font-display:block;src:${f(file)};}`).join("\n");
}

// Conecta la página con el catálogo de prueba. Devuelve la URL de la tienda.
async function attach(page, base) {
  const html = fs.readFileSync(path.join(ROOT, "tienda", "index.html"), "utf8");
  const previews = previewFiles(html);
  const STATIC = {
    "43eaa1_72cd58cd4eda4174852a42b5db8ec470~mv2.jpg": path.join(IMG, "hero-porcelana.jpg"),
    "43eaa1_3dab28e9c2ca4bb4af2c54a9abb19aa0~mv2.jpg": path.join(IMG, "hero-porcelana-m.jpg"),
    "43eaa1_5439905b93b943498e6a185ac4867adb~mv2.jpg": path.join(IMG, "tarjeta-regalo.jpg"),
  };
  const json = (route, body) => route.fulfill({ status: 200, contentType: "application/json", headers: { "Access-Control-Allow-Origin": "*" }, body: JSON.stringify(body) });

  await page.route("https://www.wixapis.com/**", async (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "*" } });
    }
    const p = new URL(req.url()).pathname;
    if (p === "/oauth2/token") return json(route, { access_token: "local", refresh_token: "local", expires_in: 14400 });
    if (p === "/stores/v3/products/query") return json(route, { products: PRODUCTS });
    if (p === "/stores/v3/products/query-variants") {
      let id = "";
      try { id = JSON.parse(req.postData() || "{}").query.filter["productData.productId"].$eq; } catch (e) { /* sin filtro */ }
      return json(route, { variants: variantsFor(id) });
    }
    if (p === "/gift-cards/v1/gift-card-products/query") return json(route, {});
    if (p.startsWith("/ecom/v2/carts/current")) return json(route, { cart: { id: "local", lineItems: [], currency: "EUR" } });
    return json(route, {});
  });
  await page.route("https://static.wixstatic.com/**", async (route) => {
    const name = new URL(route.request().url()).pathname.split("/media/")[1].split("/")[0];
    const file = STATIC[name] || previews[name] || (name.startsWith("adk_") ? path.join(IMG, name.slice(4)) : null);
    if (!file || !fs.existsSync(file)) return route.fulfill({ status: 404, body: "" });
    return route.fulfill({ status: 200, contentType: "image/jpeg", body: fs.readFileSync(file) });
  });
  await page.route("https://fonts.googleapis.com/**", (route) => route.fulfill({ status: 200, contentType: "text/css", body: fontCss(base) }));
  await page.route("https://fonts.gstatic.com/**", (route) => route.fulfill({ status: 404, body: "" }));
  return base + "/tienda/index.html";
}

module.exports = { startServer, attach, COLORS, ID_RESINA, ID_DECORADA, ID_CACHIRULO };
