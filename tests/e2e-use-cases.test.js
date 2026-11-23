"use strict";
// E2E dos use cases (docs/use-cases.md, docs/catalogo.json): um teste por UC-NNN, CLI real num sandbox
// temporário, sem rede, sem modelo e sem painéis reais. Nomes estáveis: o catálogo liga-os por nome.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const { ROOT, kaizen, sandbox, caminhoSp, preencherSp, matar, lancarPy, esperarSaida, TIMEOUT } = require("./helpers/sandbox.js");

const T = { timeout: TIMEOUT * 2 };
const comSandbox = (opts, fn) => async () => {
  const sb = sandbox(opts);
  try { await fn(sb); } finally { sb.limpar(); }
};
const ok = (r, msg) => assert.strictEqual(r.status, 0, `${msg || "rc≠0"}: ${r.out}`);

// ---------- fixtures ----------
function novoSp(sb, slug = "login") {
  const r = sb.py("sp-new.py", "--project", "_default", "--slug", slug, "--priority", "P2");
  ok(r, "sp-new");
  const rel = caminhoSp(sb, r.stdout);
  return { rel, slug: path.basename(rel, ".md") };
}

function programa(sb) {
  const r = sb.py("sp-new.py", "--project", "_default", "--program", "billing", "--children", "api,ui:api",
    "--priority", "P2", "--gate", "node --version", "--decisao", "x");
  ok(r, "sp-new --program");
  const dir = path.join(sb.dir, "knowledge", "projects", "kaizen", "_default", "sp", "TODO");
  const slugs = fs.readdirSync(dir).map((f) => f.replace(/\.md$/, ""));
  const mae = slugs.find((s) => s.startsWith("billing-"));
  const api = slugs.find((s) => s.startsWith("api-"));
  const ui = slugs.find((s) => s.startsWith("ui-"));
  assert.ok(mae && api && ui, `programa incompleto: ${slugs}`);
  for (const s of [api, ui]) ok(sb.py("sp-aprovar.py", s, "--rondas", "1"), `aprovar ${s}`);
  return { mae, api, ui, dir };
}

function jl(sb, rel, rows) {
  sb.escrever(rel, rows.map((r) => JSON.stringify(r)).join("\n") + "\n");
}

function claudeRow(ts, id, model = "claude-sonnet-5-5", input = 1_000_000) {
  return { type: "assistant", timestamp: ts, requestId: "r" + id,
    message: { id, model, usage: { input_tokens: input, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 } } };
}

function codexSessao(sb, rel, model) {
  const last = { input_tokens: 100, cached_input_tokens: 0, output_tokens: 10, total_tokens: 110 };
  jl(sb, rel, [
    { timestamp: "2026-10-20T10:00:00Z", type: "session_meta", payload: { id: "abcdef0123456789" } },
    { timestamp: "2026-10-20T10:00:01Z", type: "turn_context", payload: { model } },
    { timestamp: "2026-10-20T10:02:00Z", type: "event_msg", payload: { type: "token_count", info: { last_token_usage: last, total_token_usage: { total_tokens: 110 } } } },
  ]);
}

/** Transcripts de fixture: Claude em 2026-10-20 e 2026-10-25, Codex em 2026-10-20. */
function transcripts(sb) {
  jl(sb, "fx/claude/proj/aaaa1111.jsonl", [claudeRow("2026-10-20T10:00:00Z", "m1"), claudeRow("2026-10-25T10:00:00Z", "m2", "claude-haiku-5-5", 2_000_000)]);
  codexSessao(sb, "fx/codex/2026/10/20/rollout-1.jsonl", "gpt-unpriced");
  return ["--repo", sb.dir, "--claude-root", path.join(sb.dir, "fx", "claude"), "--codex-root", path.join(sb.dir, "fx", "codex")];
}

function commitTudo(sb) {
  sb.git("add", "-A");
  ok(sb.git("commit", "-qm", "base"), "git commit");
}

// ---------- fluxo normal ----------
test("fluxo normal: init, doctor, sp-new, sp-validate, sp-move doing e done, status", T, comSandbox({}, (sb) => {
  ok(sb.kz("doctor", ".", "--harness", "claude"), "doctor");
  const { rel, slug } = novoSp(sb);
  assert.strictEqual(sb.py("sp-validate.py", rel).status, 1, "SP vazio devia falhar a validação");
  preencherSp(sb, rel);
  ok(sb.py("sp-validate.py", rel), "sp-validate");
  ok(sb.py("sp-move.py", slug, "doing"), "sp-move doing");
  assert.match(sb.kz("status", ".").stdout, new RegExp(`${slug}[\\s\\S]*1 Doing|Doing[\\s\\S]*${slug}`));
  ok(sb.py("sp-move.py", slug, "done"), "sp-move done");
  assert.ok(sb.existe(`knowledge/projects/kaizen/_default/sp/Done/${slug}.md`));
  const st = sb.kz("status", ".");
  ok(st, "status");
  assert.match(st.stdout, /0 TODO, 0 Doing/);
  const fora = fs.readdirSync(sb.base).filter((f) => ![".home", "projeto ção"].includes(f));
  assert.deepStrictEqual(fora, [], "nada escrito fora do projeto e do HOME do sandbox");
}));

// ---------- instalação ----------
test("UC-001 kaizen init instala o workflow e preserva ficheiros", T, comSandbox({ init: false }, (sb) => {
  sb.escrever("AGENTS.md", "# Meu projeto\nregra minha\n");
  ok(sb.kz("init", sb.dir, "--harness", "codex"), "init");
  const agents = sb.ler("AGENTS.md");
  assert.match(agents, /regra minha/);
  assert.ok(agents.length > "# Meu projeto\nregra minha\n".length, "bloco do kaizen acrescentado");
  for (const f of ["scripts/sp-new.py", "scripts/sp-move.py", "scripts/sp-validate.py"]) assert.ok(sb.existe(f), f);
}));

test("UC-002 kaizen doctor dá rc 0 completo e rc 1 com o que falta", T, comSandbox({ harness: "codex" }, (sb) => {
  ok(sb.kz("doctor", ".", "--harness", "codex"), "doctor ok");
  fs.rmSync(path.join(sb.dir, "scripts", "sp-move.py"));
  const r = sb.kz("doctor", ".", "--harness", "codex");
  assert.strictEqual(r.status, 1);
  assert.match(r.out, /sp-move/);
}));

test("UC-003 kaizen doctor --fix repõe sem sobrescrever", T, comSandbox({ harness: "codex" }, (sb) => {
  fs.rmSync(path.join(sb.dir, "scripts", "sp-move.py"));
  const meu = path.join(sb.dir, "scripts", "sp-new.py");
  fs.appendFileSync(meu, "\n# alteração local\n");
  ok(sb.kz("doctor", ".", "--harness", "codex", "--fix"), "doctor --fix");
  assert.ok(sb.existe("scripts/sp-move.py"));
  assert.match(fs.readFileSync(meu, "utf8"), /# alteração local/);
  ok(sb.kz("doctor", ".", "--harness", "codex"), "doctor depois do fix");
}));

// ---------- custos ----------
test("UC-004 kaizen usage mostra totais por dia e modelo", T, comSandbox({ init: false }, (sb) => {
  const r = sb.kz("usage", ...transcripts(sb), "--days", "3650");
  ok(r, "usage");
  for (const s of ["2026-10-20", "claude-sonnet-5-5", "gpt-unpriced"]) assert.match(r.stdout, new RegExp(s));
}));

test("UC-005 kaizen usage junta Claude e Codex numa tabela", T, comSandbox({ init: false }, (sb) => {
  const r = sb.kz("usage", ...transcripts(sb), "--source", "claude,codex");
  ok(r, "usage");
  assert.match(r.stdout, /claude-sonnet-5-5/);
  assert.match(r.stdout, /gpt-unpriced/);
}));

test("UC-006 kaizen report escreve a nota semanal só com métricas", T, comSandbox({ init: false }, (sb) => {
  const r = sb.kz("report", ...transcripts(sb), "--week", "2026-W43");
  ok(r, "report");
  const nota = r.stdout.split(/\r?\n/).map((l) => l.trim()).find((l) => l.endsWith("2026-W43.md"));
  assert.ok(nota, `caminho da nota: ${r.out}`);
  const p = path.isAbsolute(nota) ? nota : path.join(sb.dir, nota.replace(/^.*?:\s*/, ""));
  const texto = fs.readFileSync(fs.existsSync(p) ? p : nota.replace(/^.*?:\s*/, ""), "utf8");
  assert.match(texto, /claude-sonnet-5-5/);
  assert.ok(!texto.includes("requestId"), "só métricas, sem conteúdo dos transcripts");
}));

test("UC-007 preços em kaizen.config.json dão custo em vez de n/a", T, comSandbox({ init: false }, (sb) => {
  const argv = transcripts(sb);
  assert.match(sb.kz("usage", ...argv, "--source", "codex").stdout, /\| gpt-unpriced \|[^\n]*n\/a/);
  sb.escrever("p.json", JSON.stringify({ models: { "gpt-unpriced": { in: 10.0, out: 20.0 } } }));
  sb.escrever("kaizen.config.json", JSON.stringify({ prices: "p.json" }));
  const r = sb.kz("usage", ...argv, "--source", "codex");
  ok(r, "usage");
  assert.doesNotMatch(r.stdout, /\| gpt-unpriced \|[^\n]*n\/a/);
  assert.doesNotMatch(r.out, /Warning: no price for gpt-unpriced/);
}));

test("UC-008 kaizen status lista as histórias por estado e prioridade", T, comSandbox({}, (sb) => {
  const a = novoSp(sb, "alfa");
  const b = novoSp(sb, "beta");
  ok(sb.py("sp-move.py", b.slug, "doing"), "sp-move");
  const r = sb.kz("status", ".");
  ok(r, "status");
  assert.match(r.stdout, new RegExp(`${a.slug}`));
  assert.match(r.stdout, new RegExp(`${b.slug}`));
  assert.match(r.stdout, /1 TODO, 1 Doing/);
  assert.match(r.stdout, /P2/);
}));

test("UC-009 kaizen usage --since corta o período", T, comSandbox({ init: false }, (sb) => {
  const r = sb.kz("usage", ...transcripts(sb), "--since", "2026-10-21");
  ok(r, "usage");
  assert.match(r.stdout, /2026-10-25/);
  assert.doesNotMatch(r.stdout, /2026-10-20/);
}));

test("UC-010 kaizen usage --source codex --top mostra só um harness", T, comSandbox({ init: false }, (sb) => {
  const r = sb.kz("usage", ...transcripts(sb), "--source", "codex", "--top", "10");
  ok(r, "usage");
  assert.match(r.stdout, /gpt-unpriced/);
  assert.doesNotMatch(r.stdout, /claude-/);
}));

test("UC-011 kaizen usage --codex-root lê transcripts copiados", T, comSandbox({ init: false }, (sb) => {
  codexSessao(sb, "backup/sessions/2026/10/20/rollout-9.jsonl", "gpt-copiado");
  const r = sb.kz("usage", "--repo", sb.dir, "--source", "codex", "--codex-root", path.join(sb.dir, "backup", "sessions"));
  ok(r, "usage");
  assert.match(r.stdout, /gpt-copiado/);
}));

test("UC-012 kaizen report --print mostra a nota sem escrever", T, comSandbox({ init: false }, (sb) => {
  const antes = new Set(fs.readdirSync(sb.dir));
  const r = sb.kz("report", ...transcripts(sb), "--week", "2026-W43", "--print");
  ok(r, "report --print");
  assert.match(r.stdout, /2026-W43/);
  assert.match(r.stdout, /claude-sonnet-5-5/);
  const novos = fs.readdirSync(sb.dir).filter((f) => !antes.has(f) && f !== "fx");
  assert.deepStrictEqual(novos, [], "nada escrito");
}));

test("UC-013 kaizen report --out escreve noutra pasta", T, comSandbox({ init: false }, (sb) => {
  const r = sb.kz("report", ...transcripts(sb), "--week", "2026-W43", "--out", path.join(sb.dir, "docs", "usage"));
  ok(r, "report --out");
  assert.ok(sb.existe("docs/usage/2026-W43.md"), r.out);
}));

// ---------- histórias ----------
test("UC-014 sp-new cria uma história de 8 secções em TODO", T, comSandbox({}, (sb) => {
  const { rel } = novoSp(sb);
  assert.match(rel.replace(/\\/g, "/"), /sp\/TODO\/login-\d{4}-\d{2}-\d{2}\.md$/);
  const t = sb.ler(rel);
  for (let n = 1; n <= 8; n++) assert.match(t, new RegExp(`## ${n}\\.`));
}));

test("UC-015 sp-new --program cria mãe e filhos com dependências", T, comSandbox({}, (sb) => {
  const { mae, api, ui, dir } = programa(sb);
  const tui = fs.readFileSync(path.join(dir, `${ui}.md`), "utf8");
  assert.match(tui, new RegExp(`depends_on:.*${api}`));
  assert.match(tui, new RegExp(`parent: ${mae}`));
}));

test("UC-016 sp-move leva a história a Doing e Done e --next abre o filho seguinte", T, comSandbox({}, (sb) => {
  const { api, ui } = programa(sb);
  ok(sb.py("sp-move.py", api, "doing"), "doing");
  const r = sb.py("sp-move.py", api, "done", "--next");
  ok(r, "done --next");
  assert.ok(sb.existe(`knowledge/projects/kaizen/_default/sp/Done/${api}.md`));
  assert.ok(sb.existe(`knowledge/projects/kaizen/_default/sp/Doing/${ui}.md`), r.out);
}));

test("UC-017 sp-validate falha com secção vazia e passa completa", T, comSandbox({}, (sb) => {
  const { rel } = novoSp(sb);
  const r = sb.py("sp-validate.py", rel);
  assert.strictEqual(r.status, 1);
  assert.match(r.out, /secção vazia: 1\. Role/);
  preencherSp(sb, rel);
  ok(sb.py("sp-validate.py", rel), "validate");
}));

test("UC-018 kaizen audit falha com dados pessoais", T, comSandbox({}, (sb) => {
  ok(sb.kz("audit", "."), "audit limpo");
  sb.escrever("notas.md", "contacto: " + ["fulano", "exemplo.pt"].join("@") + "\n");
  assert.strictEqual(sb.kz("audit", ".").status, 1);
}));

// ---------- sessões e fila ----------
test("UC-019 sp-handoff --launch --dry-run mostra os comandos sem executar", T, comSandbox({}, (sb) => {
  const { rel } = novoSp(sb);
  const antes = sb.ler(rel);
  const r = sb.py("sp-handoff.py", "--launch", rel, "--dry-run", "--backend", "tmux", "--pane", "%9");
  ok(r, "dry-run");
  assert.match(r.stdout, /\/clear/);
  assert.match(r.stdout, /michi/);
  assert.strictEqual(sb.ler(rel), antes, "SP intacto");
}));

test("UC-020 sp-fila --dry-run mostra a ordem e as exclusões", T, comSandbox({}, (sb) => {
  const a = novoSp(sb, "pronta");
  preencherSp(sb, a.rel);
  ok(sb.py("sp-aprovar.py", a.slug, "--rondas", "1"), "aprovar");
  const b = novoSp(sb, "vazia");
  const r = sb.py("sp-fila.py", "--dry-run");
  ok(r, "fila --dry-run");
  assert.match(r.stdout, new RegExp(a.slug));
  assert.match(r.out, new RegExp(b.slug));
  assert.ok(r.stdout.indexOf(a.slug) >= 0);
}));

test("UC-021 sp-fila --concorrencia planeia vários sem abrir painéis", T, comSandbox({}, (sb) => {
  const slugs = ["um", "dois"].map((s) => { const x = novoSp(sb, s); preencherSp(sb, x.rel); ok(sb.py("sp-aprovar.py", x.slug, "--rondas", "1")); return x.slug; });
  const r = sb.py("sp-fila.py", "--dry-run", "--concorrencia", "3");
  ok(r, "fila --concorrencia --dry-run");
  for (const s of slugs) assert.match(r.stdout, new RegExp(s));
  assert.ok(!sb.existe(".kaizen/fila-paineis.json"), "nenhum painel registado");
}));

test("UC-022 pentest deteta uma falha plantada no diff", T, comSandbox({}, (sb) => {
  commitTudo(sb);
  sb.escrever("app.py", "import subprocess\nsubprocess.run(cmd, shell=True)\n");
  const r = sb.py("pentest.py", "--repo", ".");
  assert.strictEqual(r.status, 1, r.out);
  assert.match(r.out, /injecao/);
  assert.match(r.out, /app\.py/);
}));

test("UC-023 review_ciclo corrige e repete até aprovar", T, comSandbox({}, (sb) => {
  const ach = sb.escrever("achados.txt", "[bloqueante] x.py:3 divide por zero\n");
  const est = path.join(sb.dir, "review.json");
  assert.strictEqual(sb.py("review_ciclo.py", est, "--achados", ach).status, 1);
  assert.strictEqual(JSON.parse(fs.readFileSync(est, "utf8")).veredicto, "CORRIGIR");
  fs.writeFileSync(ach, "[menor] x.py:3 comentário\n");
  ok(sb.py("review_ciclo.py", est, "--achados", ach), "segunda ronda");
  const e = JSON.parse(fs.readFileSync(est, "utf8"));
  assert.strictEqual(e.veredicto, "APROVADO");
  assert.strictEqual(e.iteracao, 2);
}));

test("UC-024 pr_corpo monta o corpo do PR sem o abrir", T, comSandbox({}, (sb) => {
  const sp = sb.escrever("sp.md", "---\nslug: demo\npr: auto\n---\n# Super Prompt\n## 3. Objective (single sentence)\nFazer a coisa.\n## Decisões\n- Usar X.\n## Progresso\n- feito Y.\n## Prova de done\n- teste 4/4.\n");
  const rev = sb.escrever("review.json", JSON.stringify({ veredicto: "APROVADO", iteracao: 2 }));
  const r = sb.py("pr_corpo.py", sp, "--review", rev, "--base", "main", "--dry-run");
  ok(r, "pr_corpo");
  assert.match(r.stdout, /## Prova/);
  assert.match(r.stdout, /Fazer a coisa/);
}));

test("UC-025 handoff sem história escreve, retoma e apaga", T, comSandbox({}, (sb) => {
  const campos = ["Estado", "Último passo", "Próximo passo", "Ficheiros tocados", "Gates por correr"];
  const corpo = sb.escrever("corpo.md", campos.map((c) => `**${c}**\n- x\n`).join("\n"));
  const dir = path.join(sb.dir, "handoffs");
  const w = sb.py("handoff.py", "--write", "--file", corpo, "--slug", "conversa", "--dir", dir);
  ok(w, "write");
  const f = w.stdout.trim().split(/\r?\n/).pop();
  assert.ok(fs.existsSync(f), w.out);
  const c = sb.py("handoff.py", "--consume", f);
  ok(c, "consume");
  for (const k of campos) assert.ok(c.stdout.includes(`**${k}**`), k);
  assert.ok(!fs.existsSync(f), "handoff apagado depois de lido");
}));

test("UC-026 kaizen-hooks.json corre um comando num evento", T, comSandbox({}, (sb) => {
  const out = path.join(sb.dir, "evento.txt");
  const code = `import os,sys;open(r'${out}','w',encoding='utf-8').write(os.environ['KAIZEN_SLUG']+sys.stdin.read())`;
  sb.escrever("kaizen-hooks.json", JSON.stringify({ hooks: [{ event: "sp.created", cmd: `"${process.platform === "win32" ? "python" : "python3"}" -c "${code}"` }] }));
  ok(sb.py("kaizen_hooks.py", "fire", "sp.created", "--slug", "abc"), "fire");
  const t = fs.readFileSync(out, "utf8");
  assert.ok(t.startsWith("abc"), t);
  assert.match(t, /"event": "sp.created"/);
}));

test("UC-027 sp-handoff regista o progresso e prepara a retoma", T, comSandbox({}, (sb) => {
  const { rel, slug } = novoSp(sb);
  preencherSp(sb, rel);
  ok(sb.py("sp-move.py", slug, "doing"), "doing");
  const relDoing = rel.replace(/TODO/, "Doing");
  const r = sb.py("sp-handoff.py", "--launch", relDoing, "--dry-run", "--backend", "clipboard");
  ok(r, "sp-handoff --dry-run");
  assert.match(r.stdout, new RegExp(`michi[^\\n]*${slug}`));
}));

test("UC-028 sp-execucao grava sequencial ou paralelo na mãe", T, comSandbox({}, (sb) => {
  const { mae, dir } = programa(sb);
  assert.match(sb.py("sp-execucao.py", mae).out, /por escolher/);
  ok(sb.py("sp-execucao.py", mae, "paralelo"), "gravar");
  assert.match(fs.readFileSync(path.join(dir, `${mae}.md`), "utf8"), /execucao: paralelo/);
  assert.match(sb.py("sp-execucao.py", mae).out, /paralelo/);
}));

test("UC-029 kaizen catalog mede EC e UC", T, comSandbox({ init: false }, (sb) => {
  const r = sb.kz("catalog", "report", "--json", "--no-run", "--root", ROOT);
  assert.ok([0, 1].includes(r.status), r.out);
  const j = JSON.parse(r.stdout);
  for (const k of ["ec", "uc"]) assert.ok(j[k] && j[k].total > 0 && typeof j[k].fracao === "number", r.stdout.slice(0, 200));
}));

// ---------- retoma (programa edge-cases-retoma) ----------
function journal(sb, slug, passos) {
  for (const [ev, fase, passo] of passos) ok(sb.py("sp_journal.py", ev, "--slug", slug, "--fase", fase, "--passo", passo, "--raiz", sb.dir), `journal ${ev} ${fase}`);
}

function codigoLock(sb, slug) {
  const scripts = path.join(sb.dir, "scripts").replace(/\\/g, "/");
  const raiz = sb.dir.replace(/\\/g, "/");
  return `import sys,time;sys.path.insert(0,${JSON.stringify(scripts)});import sp_disco,sp_journal;` +
    `sp_journal.inicio(${JSON.stringify(raiz)},${JSON.stringify(slug)},"da","p2");` +
    `sp_disco.tomar_lock(${JSON.stringify(raiz)},${JSON.stringify(slug)},"painel-e2e");print("pronto",flush=True);time.sleep(60)`;
}

test("UC-030 kaizen resume retoma após o processo morrer a meio", T, comSandbox({}, async (sb) => {
  const slug = "retoma-e2e";
  journal(sb, slug, [["inicio", "dp", "p1"], ["fim", "dp", "p1"]]);
  const filho = await lancarPy(sb, codigoLock(sb, slug));
  try {
    const vivo = sb.kz("resume", slug);
    assert.strictEqual(vivo.status, 1, `2.º processo devia ser recusado: ${vivo.out}`);
    assert.match(vivo.out, /EC-043/);
    assert.match(vivo.out, /painel-e2e/);
  } finally {
    matar(filho);
    await esperarSaida(filho);
  }
  const r = sb.kz("resume", slug);
  ok(r, "resume");
  assert.match(r.out, /em da/);
  assert.doesNotMatch(r.out, /em dp/);
}));

test("UC-031 kaizen resume --from começa na fase pedida", T, comSandbox({}, (sb) => {
  const slug = "from-e2e";
  journal(sb, slug, [["inicio", "dp", "p1"], ["fim", "dp", "p1"], ["inicio", "da", "p2"], ["fim", "da", "p2"], ["inicio", "gates", "p3"]]);
  const r = sb.kz("resume", slug, "--from", "da");
  ok(r, "resume --from");
  assert.match(r.out, /retomar from-e2e em da\b/);
  assert.doesNotMatch(r.out, /em gates/);
}));

test("UC-032 kaizen resume --restart pede confirmação e arquiva o checkpoint", T, comSandbox({}, (sb) => {
  const slug = "restart-e2e";
  journal(sb, slug, [["inicio", "dp", "p1"], ["fim", "dp", "p1"], ["inicio", "da", "p2"]]);
  const estado = path.join(sb.dir, ".kaizen", "estado");
  const antes = fs.readdirSync(estado, { recursive: true }).length;
  const sem = sb.kz("resume", slug, "--restart");
  assert.strictEqual(sem.status, 1, sem.out);
  assert.match(sem.out, /EC-006/);
  const com = sb.kz("resume", slug, "--restart", "--sim");
  ok(com, "restart --sim");
  const depois = fs.readdirSync(estado, { recursive: true }).map(String);
  assert.ok(depois.length >= antes, "nada apagado");
  assert.ok(depois.some((f) => /arquiv|restart|\.bak|-\d{8}/i.test(f)), `checkpoint arquivado: ${depois}`);
}));

test("UC-033 sp-fila --programa corre os filhos pela ordem da mãe", T, comSandbox({}, (sb) => {
  const { mae, api, ui } = programa(sb);
  ok(sb.py("sp-execucao.py", mae, "sequencial"), "execucao");
  const r = sb.py("sp-fila.py", "--programa", mae, "--dry-run");
  ok(r, "fila --programa --dry-run");
  const ia = r.stdout.indexOf(api);
  const iu = r.stdout.indexOf(ui);
  assert.ok(ia >= 0 && iu >= 0 && ia < iu, `api antes de ui: ${r.stdout}`);
  assert.strictEqual(sb.py("sp-fila.py", "--programa", "billing", "--dry-run").status, 1, "slug sem data recusado");
}));

test("UC-034 sp-fila --programa retoma o filho já em Doing", T, comSandbox({}, (sb) => {
  const { mae, api, ui } = programa(sb);
  ok(sb.py("sp-execucao.py", mae, "sequencial"), "execucao");
  ok(sb.py("sp-move.py", api, "doing"), "api em Doing");
  const r = sb.py("sp-fila.py", "--programa", mae, "--dry-run");
  ok(r, "fila --programa --dry-run");
  assert.match(r.out, new RegExp(`${api}[^\\n]*já em Doing|já em Doing[^\\n]*${api}`));
  assert.match(r.stdout, new RegExp(ui));
}));

test("UC-035 kaizen ds gera e valida o design system do projeto", T, comSandbox({}, (sb) => {
  const ds = (...a) => kaizen(["ds", ...a], { cwd: sb.dir, env: sb.env, encoding: "utf8" });
  assert.strictEqual(ds("init", "demo").status, 0, "ds init");
  assert.ok(fs.existsSync(path.join(sb.dir, "DESIGN.md")), "DESIGN.md");
  assert.ok(fs.existsSync(path.join(sb.dir, "design", "tokens.json")), "tokens.json");
  assert.strictEqual(ds("validate").status, 0, "ds validate");
  assert.strictEqual(ds("export").status, 0, "ds export");
  const css = fs.readFileSync(path.join(sb.dir, "design", "tokens.css"), "utf8");
  assert.match(css, /:root\s*\{[^}]*--/);
}));

test("UC-038 kaizen vision gera e valida o VISION.md do projeto", T, comSandbox({}, (sb) => {
  const vision = (...a) => kaizen(["vision", ...a], { cwd: sb.dir, env: sb.env, encoding: "utf8" });
  assert.strictEqual(vision("init", "demo").status, 0, "vision init");
  const f = path.join("demo", "VISION.md");
  assert.ok(fs.existsSync(path.join(sb.dir, f)), "VISION.md");
  const falha = vision("validate", f);
  assert.strictEqual(falha.status, 1, "esqueleto com TBD não valida");
  assert.match(falha.stderr, /Goal/);
  const texto = fs.readFileSync(path.join(sb.dir, f), "utf8")
    .replace("ui: nao", "ui: nao").replace("stack: TBD", "stack: node").replace("orcamento: TBD", "orcamento: 5 USD por SP, 20 USD por dia")
    .replace("## Goal\nTBD", "## Goal\nPlanear refeições sem desperdício.")
    .replace("## Users\n- TBD", "## Users\n- Famílias.")
    .replace(/- \[ \] TBD[^\n]*/, "- [ ] `npm test` passa.")
    .replace("## Constraints\n- TBD", "## Constraints\n- Sem telemetria.")
    .replace("## Non-goals\n- TBD", "## Non-goals\n- Sem contas.")
    .replace("1. TBD", "1. Lista de compras.");
  fs.writeFileSync(path.join(sb.dir, f), texto, "utf8");
  assert.strictEqual(vision("validate", f).status, 0, "vision validate");
  const r = vision("resumo", f);
  assert.strictEqual(r.status, 0, "vision resumo");
  assert.match(r.stdout, /demo/);
}));

test("UC-039 kaizen vision decompor cria o programa de SPs", T, comSandbox({}, (sb) => {
  const vision = (...a) => kaizen(["vision", ...a], { cwd: sb.dir, env: sb.env, encoding: "utf8" });
  const f = path.join(sb.dir, "VISION.md");
  fs.writeFileSync(f, [
    "---", "projeto: demo", "ui: nao", "stack: node", "design_system: nenhum", "orcamento: 5 USD por SP, 20 USD por dia", "---",
    "# demo", "", "## Goal", "Planear refeições.", "", "## Users", "- Famílias.", "", "## Success criteria", "- [ ] `npm test` passa", "",
    "## Constraints", "- Só stdlib.", "", "## Non-goals", "- Sem contas.", "", "## Milestones",
    "1. Modelo [ficheiros 2, horas 1] `node --version`", "2. API (depende: 1) `node --version`", "",
  ].join("\n"), "utf8");
  const root = path.join(sb.dir, "sp-root");
  fs.mkdirSync(path.join(root, "demo"), { recursive: true });
  const args = ["decompor", f, "--root", root, "--data", "2026-11-23"];
  assert.strictEqual(vision(...args).status, 0, "decompor");
  const todo = path.join(root, "demo", "sp", "TODO");
  assert.strictEqual(fs.readdirSync(todo).length, 3, "mãe + 2 filhos");
  const outra = vision(...args);
  assert.strictEqual(outra.status, 0, "segunda execução");
  assert.match(outra.stdout, /nada a criar/);
  assert.strictEqual(fs.readdirSync(todo).length, 3, "idempotente");
}));
