"use strict";
// Driver do ds-verify.py: corre no projeto-alvo (cwd), usa o `playwright` e o `@axe-core/playwright` DELE.
// stdin: JSON {url, rotas, breakpoints, destino, slugs}; stdout (última linha): JSON {violacoes, screenshots} ou {semBrowser, motivo}.
const path = require("path");
const fs = require("fs");

function carregar(nome) {
  return require(require.resolve(nome, { paths: [process.cwd()] }));
}

async function main(cfg) {
  let chromium, AxeBuilder;
  try {
    ({ chromium } = carregar("playwright"));
    AxeBuilder = carregar("@axe-core/playwright").default || carregar("@axe-core/playwright").AxeBuilder;
  } catch (e) {
    return { semBrowser: true, motivo: "playwright ou @axe-core/playwright não instalados no projeto" };
  }
  let browser;
  try {
    browser = await chromium.launch();
  } catch (e) {
    return { semBrowser: true, motivo: "browser do Playwright indisponível (npx playwright install chromium)" };
  }
  const violacoes = [], screenshots = [];
  try {
    for (const rota of cfg.rotas) {
      for (const [nome, largura] of Object.entries(cfg.breakpoints)) {
        const page = await browser.newPage({ viewport: { width: largura, height: 800 } });
        await page.goto(cfg.url.replace(/\/$/, "") + rota, { waitUntil: "networkidle" });
        const ficheiro = path.join(cfg.destino, `${cfg.slugs[rota]}-${nome}.png`);
        await page.screenshot({ path: ficheiro, fullPage: true, animations: "disabled" });
        screenshots.push({ rota, bp: nome, ficheiro });
        if (nome === Object.keys(cfg.breakpoints)[0]) {
          const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
          for (const v of r.violations) violacoes.push({ rota, id: v.id, impact: v.impact, nodes: v.nodes.length });
        }
        await page.close();
      }
    }
  } finally {
    await browser.close();
  }
  return { violacoes, screenshots };
}

let entrada = "";
process.stdin.on("data", (d) => (entrada += d));
process.stdin.on("end", async () => {
  try {
    console.log(JSON.stringify(await main(JSON.parse(entrada))));
  } catch (e) {
    console.log(JSON.stringify({ semBrowser: true, motivo: String(e.message || e).slice(0, 200) }));
  }
});
