#!/usr/bin/env python3
"""Auditoria só de leitura: deteta o contexto e aponta o que está mal, incorreto ou errado.

Uso: auditar.py [--repo R] [--modo rapido|normal|total] [--base REF] [--sp SP.md]
                [--no-baseline | --baseline F] [--criar-sps --project P [--prefixo S]] [--relatorio F]
     auditar.py ciclo <estado.json> --achados F [--max 3] [--criar-sps --project P] [--ficheiros F... [--raiz D]]
Modos: rapido = linhas adicionadas; normal = ficheiros alterados por inteiro; total = todo o repo.
Tipos: bug, regra, docs, seguranca, robustez. Contextos: codigo, vault, ui, sp.
rc: 0 sem achados confirmados (suspeitas não contam), 1 com achados.
Nunca abre segredos (.env, chaves) nem toca na rede. Só escreve com --criar-sps, --relatorio e o estado do `ciclo`.
Supressão: `# auditar: ok <motivo>` (ou `//`) na linha; sem motivo não suprime.
"""
import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from painel_backend import run_hidden  # noqa: E402

SECRET_FILES = re.compile(r"(^|/)(\.env(\..*)?|.*\.(key|pem|p12|pfx)|id_rsa.*|secrets\..*|\.secrets.*)$")
WEB = re.compile(r"\.(js|jsx|ts|tsx|mjs|cjs|html|vue|svelte)$")
JSTS = re.compile(r"\.(js|jsx|ts|tsx|mjs|cjs|vue|svelte)$")
PY = re.compile(r"\.py$")
RUST = re.compile(r"\.rs$")
TAURI = re.compile(r"(capabilities/[^/]+\.(json|toml)|tauri\.conf\.json)$")
CODIGO = re.compile(r"\.(py|js|jsx|ts|tsx|mjs|cjs|rs|go|java|c|cpp|h|sh|vue|svelte)$")
UI = re.compile(r"\.(tsx|jsx|vue|svelte|html|css)$|(^|/)(src-tauri|components)/")
TEXTO_PROSA = re.compile(r"\.(md|txt|rst)$")
IMPORT = re.compile(r"(^|[^\w])(from|import|require)\s*\(?\s*[\"']\.\./")
TESTE = re.compile(r"(^|/)(test_[^/]*|[^/]*(\.(test|spec)\.[a-z]+|_test\.(py|rs|go)))$")
SUPRESSAO = re.compile(r"(?:#|//|<!--|/\*)\s*auditar:\s*ok\s+(\S.*?)\s*(?:-->|\*/)?\s*$")
SUSPEITA = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
WIKILINK = re.compile(r"\[\[([^\]\n]+?)\]\]")
SQL_KW = r"(?=.*\b(select|insert|update|delete|drop)\b)"
SQL_CALL = r"\.(execute\w*|query|raw)\s*\(\s*"
SEV = {"alta": "alto", "media": "medio", "baixa": "baixo", "critica": "critico"}
ORDEM = {"critico": 0, "alto": 1, "medio": 2, "baixo": 3}

# (tipo, categoria, severidade, descrição, regex, filtro de caminho ou None)
CHECKS = [
    ("seguranca", "injecao", "alta", "shell=True ou os.system", re.compile(r"shell\s*=\s*True|os\.system\s*\("), None),  # auditar: ok definição do padrão
    ("seguranca", "injecao", "alta", "eval/exec dinâmico", re.compile(r"(?<![\w.])(eval|exec)\s*\("), None),
    ("seguranca", "injecao", "alta", "new Function com código dinâmico", re.compile(r"\bnew\s+Function\s*\("), JSTS),
    ("seguranca", "injecao", "alta", "child_process.exec com string", re.compile(r"child_process\.exec\s*\(|(?<![\w.])execSync\s*\(\s*[`\"']"), None),
    ("seguranca", "desserializacao", "alta", "desserialização insegura (pickle/marshal)", re.compile(r"\b(pickle|marshal|cPickle)\.loads?\s*\("), PY),
    ("seguranca", "desserializacao", "alta", "yaml.load sem Loader seguro", re.compile(r"\byaml\.(unsafe_load\s*\(|load\s*\((?![^)]*Loader\s*=\s*(yaml\.)?(Safe|CSafe)Loader))"), PY),
    ("seguranca", "sql", "alta", "SQL montado por concatenação/interpolação",
     re.compile(r"(?i)" + SQL_KW + SQL_CALL + r"(f[\"'][^\"']*\{|`[^`]*\$\{|[\"'][^\"']*[\"']\s*(\+|%|\.format))"), None),
    ("seguranca", "xss", "media", "escrita de HTML não escapado (innerHTML/document.write)",
     re.compile(r"\.(inner|outer)HTML\s*=|dangerouslySetInnerHTML|document\.write(ln)?\s*\(|insertAdjacentHTML\s*\(|\bv-html\b"), WEB),
    ("seguranca", "paths", "media", "extração de arquivo sem validar caminhos", re.compile(r"\.extractall\s*\("), None),
    ("seguranca", "paths", "media", "caminho com ../ literal", re.compile(r"[\"']\.\./"), None),
    ("seguranca", "rust", "media", "bloco ou função unsafe", re.compile(r"\bunsafe\s*(\{|fn\b|impl\b|trait\b)"), RUST),
    ("seguranca", "tauri", "media", "âmbito Tauri com glob total (**)", re.compile(r"\"(path|url)\"\s*:\s*\"([^\"]*/)?\*\*\""), TAURI),
    ("seguranca", "tauri", "alta", "permissão Tauri shell:allow-execute", re.compile(r"\"shell:allow-execute\""), TAURI),
    ("seguranca", "tauri", "alta", "CSP Tauri desligada", re.compile(r"\"csp\"\s*:\s*null|\"dangerousDisableAssetCspModification\"\s*:\s*true"), TAURI),
    ("seguranca", "segredos", "critica", "chave privada no código", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), None),
    ("seguranca", "segredos", "alta", "token/credencial literal", re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"), None),
    ("seguranca", "segredos", "alta", "id de acesso AWS", re.compile(r"AKIA[0-9A-Z]{16}"), None),
    ("seguranca", "segredos", "alta", "leitura de ficheiro de segredos", re.compile(r"(open|readFile\w*|read_text)\s*\([^)]*\.env\b"), None),
    ("robustez", "robustez", "baixa", "except nu a engolir erros", re.compile(r"^\s*except\s*:\s*(pass)?\s*$"), None),
]


def git(repo, *args):
    r = run_hidden(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        sys.exit(f"auditar: git {' '.join(args)} falhou: {r.stderr.strip()}")
    return r.stdout


def norm(p):
    return p.replace("\\", "/")


def e_comentario(text):
    s = text.lstrip()
    return (s.startswith("#") and not s.startswith(("#[", "#!"))) or s.startswith("//")


def e_teste(p):
    return bool(TESTE.search(p) or "/tests/" in "/" + p or "/__tests__/" in "/" + p)


def ambito(repo, modo, base):
    """{ficheiro: None (todas as linhas) | set de linhas adicionadas}."""
    out = {}
    if modo == "total":
        for f in git(repo, "ls-files").splitlines():
            out[f] = None
    else:
        cur, ln = None, 0
        for raw in git(repo, "diff", "-U0", "--no-color", "--src-prefix=a/", "--dst-prefix=b/", base).splitlines():
            if raw.startswith("+++ "):
                cur = raw[6:] if raw.startswith("+++ b/") else None
                if cur:
                    out.setdefault(cur, set() if modo == "rapido" else None)
            elif raw.startswith("@@"):
                m = re.search(r"\+(\d+)", raw)
                ln = int(m.group(1)) if m else 0
            elif raw.startswith("+") and cur:
                if modo == "rapido":
                    out[cur].add(ln)
                ln += 1
    for f in git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
        out[f] = None
    return {f: v for f, v in out.items() if (Path(repo) / f).is_file()}


def added_lines(repo, base):
    """(ficheiro, nº linha, texto) das linhas adicionadas, incluindo ficheiros novos não rastreados (conteúdo de segredos não lido)."""
    out = []
    cur, ln = None, 0
    for raw in git(repo, "diff", "-U0", "--no-color", "--src-prefix=a/", "--dst-prefix=b/", base).splitlines():
        if raw.startswith("+++ "):
            cur = raw[6:] if raw.startswith("+++ b/") else None
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            ln = int(m.group(1)) if m else 0
        elif raw.startswith("+") and cur:
            out.append((cur, ln, raw[1:]))
            ln += 1
    for f in git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
        if SECRET_FILES.search(norm(f)):
            out.append((f, 1, ""))
            continue
        texto = ler(repo, f)
        out += [(f, i, t) for i, t in enumerate((texto or "").splitlines(), 1)]
    return out


CHECKLISTS = {
    "codigo": ["testes cobrem o comportamento novo e os casos limite", "erros e entradas inválidas tratados", "sem segredos, injeção ou caminhos não validados", "sem regressão nas interfaces públicas"],
    "ui": ["estados vazio, erro e carregamento", "teclado e contraste (acessibilidade)", "responsivo em largura estreita", "prova visual anexada"],
    "docs": ["links e wikilinks resolvem", "frontmatter e MOC/README atualizados", "sem duplicar regra existente", "orçamento de contexto respeitado"],
}


def checklist(tipo):
    return "\n".join(f"- [ ] {i}" for i in CHECKLISTS[tipo])


def contextos(repo, ficheiros, sp):
    ctx = []
    fs = [norm(f) for f in ficheiros]
    r = Path(repo)
    if any(CODIGO.search(f) for f in fs):
        ctx.append("codigo")
    if (r / "knowledge").is_dir() or (r / ".claude").is_dir():
        ctx.append("vault")
    if any(UI.search(f) for f in fs):
        ctx.append("ui")
    if sp:
        ctx.append("sp")
    return ctx or ["codigo"]


def achado(sev, tipo, onde, problema, correcao, evidencia):  # noqa: PLR0913 (um campo por coluna do relatório)
    return {"sev": sev, "tipo": tipo, "onde": onde, "problema": problema, "correcao": correcao, "evidencia": evidencia}


def ler(repo, f):
    try:
        return (Path(repo) / f).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def checks_ficheiro(f, p, texto):
    """Erros do ficheiro por inteiro (sintaxe, JSON, conflitos de merge)."""
    out = []
    if PY.search(p):
        try:
            ast.parse(texto)
        except SyntaxError as e:
            out.append(achado("alto", "bug", f"{f}:{e.lineno or 1}", f"erro de sintaxe Python: {e.msg}", "corrigir a sintaxe", (e.text or "").strip()))
    elif p.endswith(".json"):
        try:
            json.loads(texto)
        except json.JSONDecodeError as e:
            out.append(achado("alto", "bug", f"{f}:{e.lineno}", f"JSON inválido: {e.msg}", "corrigir o JSON", texto.splitlines()[e.lineno - 1].strip() if texto.splitlines() else ""))
    for i, t in enumerate(texto.splitlines(), 1):
        if re.match(r"^<{7}( |$)", t):
            out.append(achado("alto", "bug", f"{f}:{i}", "marcador de conflito de merge por resolver", "resolver o conflito", t.strip()))
            break
    return out


def stems(repo):
    s = set()
    for f in git(repo, "ls-files").splitlines() + git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
        if f.endswith(".md"):
            s.add(Path(f).stem.lower())
            s.add(norm(f)[:-3].lower())
    return s


def checks_links(f, texto, linhas, existentes):
    out = []
    fence = False
    for i, t in enumerate(texto.splitlines(), 1):
        if t.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence or (linhas is not None and i not in linhas):
            continue
        for m in WIKILINK.finditer(t):
            alvo = re.split(r"[|#]", m.group(1))[0].strip().lower()
            if alvo and alvo not in existentes and Path(alvo).name not in existentes and alvo.endswith(".md") is False:
                out.append(achado("medio", "docs", f"{f}:{i}", f"wikilink partido: {m.group(0)}", "corrigir o alvo ou criar a nota", t.strip()))
    return out


def checks_linhas(f, p, texto, linhas):
    """(confirmados, suspeitas) das regras linha a linha."""
    conf, sus = [], []
    prosa = bool(TEXTO_PROSA.search(p))
    for i, t in enumerate(texto.splitlines(), 1):
        if linhas is not None and i not in linhas:
            continue
        motivo = SUPRESSAO.search(t)
        comentario = e_comentario(t)
        if SUSPEITA.search(t):
            sus.append(achado("baixo", "bug", f"{f}:{i}", "marca de trabalho pendente", "resolver ou registar", t.strip()))
        if motivo:
            continue
        for tipo, cat, sev, desc, rx, filtro in CHECKS:
            if (filtro and not filtro.search(p)) or (comentario and cat != "segredos") or (prosa and cat != "segredos"):
                continue
            if desc.startswith("caminho com ../") and IMPORT.search(t):
                continue
            if rx.search(t):
                ev = "[redigido]" if cat == "segredos" else t.strip()
                conf.append(achado(SEV[sev], tipo, f"{f}:{i}", desc, "remover ou validar a entrada", ev))
    return conf, sus


def checks_vault(repo, ficheiros):
    out = []
    for f in ficheiros:
        if norm(f) == ".claude/settings.json":
            texto = ler(repo, f) or ""
            try:
                d = json.loads(texto)
            except json.JSONDecodeError:
                continue
            deny = (d.get("permissions") or {}).get("deny") if isinstance(d, dict) else None
            if not deny:
                out.append(achado("alto", "regra", f"{f}:1", "settings sem permissions.deny para segredos (.env, chaves)", "negar a leitura de .env, *.key, *.pem", "{}" if len(texto) < 40 else texto[:40]))
    return out


def checks_sp(sp):
    texto = Path(sp).read_text(encoding="utf-8")
    out = []
    fm = re.match(r"^---\n(.*?)\n---", texto, re.S)
    if not fm or "gates:" not in fm.group(1):
        out.append(achado("alto", "regra", f"{sp}:1", "SP sem gates no frontmatter", "definir os gates executáveis", ""))
    partes = re.split(r"^## ", texto, flags=re.M)[1:]
    for p in partes:
        titulo, _, corpo = p.partition("\n")
        if not corpo.strip():
            out.append(achado("medio", "regra", f"{sp}:1", f"SP com secção vazia: {titulo.strip()}", "preencher a secção", titulo.strip()))
    return out


def auditar(repo, modo="normal", base="HEAD", sp=None, baseline=None):
    """(contextos, confirmados, suspeitas). `baseline` = conjunto de chaves `tipo|onde|problema` a ignorar."""
    esc = ambito(repo, modo, base)
    conf, sus = [], []
    existentes = None
    for f, linhas in sorted(esc.items()):
        p = norm(f)
        if SECRET_FILES.search(p):
            conf.append(achado("alto", "seguranca", f"{f}:1", "ficheiro de segredos no âmbito (conteúdo não lido)", "remover do repo e rodar o segredo", "[não lido]"))
            continue
        texto = ler(repo, f)
        if texto is None:
            continue
        conf += checks_ficheiro(f, p, texto)
        if p.endswith(".md"):
            existentes = existentes if existentes is not None else stems(repo)
            conf += checks_links(f, texto, linhas, existentes)
        if e_teste(p):
            continue
        c, s = checks_linhas(f, p, texto, linhas)
        conf += c
        sus += s
    ctx = contextos(repo, esc, sp)
    if "vault" in ctx:
        conf += checks_vault(repo, esc)
    if sp:
        conf += checks_sp(sp)
    ign = set(baseline or ())
    chave = lambda a: f"{a['tipo']}|{a['onde']}|{a['problema']}"
    conf = sorted((a for a in conf if chave(a) not in ign), key=lambda a: (ORDEM[a["sev"]], a["onde"]))
    sus = [a for a in sus if chave(a) not in ign]
    return ctx, conf, sus


def relatorio(ctx, conf, sus):
    L = [f"contexto: {', '.join(ctx)}"]
    if conf:
        L += ["", "| sev | tipo | onde | problema | correção | evidência |", "|---|---|---|---|---|---|"]
        L += [f"| {a['sev']} | {a['tipo']} | {a['onde']} | {a['problema']} | {a['correcao']} | `{a['evidencia']}` |" for a in conf]
    else:
        L.append("sem achados")
    if sus:
        L += ["", "suspeitas (não contam para o rc):"]
        L += [f"- {a['onde']} {a['problema']}: `{a['evidencia']}`" for a in sus]
    return "\n".join(L)


def criar_sps(achados, project, prefixo):
    sp_new = Path(__file__).with_name("sp-new.py")
    res = []
    for i, a in enumerate(achados, 1):
        slug = f"{prefixo}-{i}-{a['tipo']}"
        r = run_hidden([sys.executable, "-I", str(sp_new), "--project", project, "--slug", slug, "--priority", "P1", "--escopo", a["onde"].split(":")[0]],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
        res.append((slug, r.returncode == 0))
    return res


# --- ciclo corrigir -> reauditar (porta de auditar.py ciclo) ---
LINHA = re.compile(r"^\[(bloqueante|menor)\]\s+(\S+)\s+(.*)$")
VERIFICAR = re.compile(r"\s*\|\s*verificar:\s*(.*)$")


def ler_achados(path):
    out = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        m = LINHA.match(raw.strip())
        if m:
            desc = m.group(3)
            v = VERIFICAR.search(desc)
            out.append({"sev": m.group(1), "onde": m.group(2), "desc": VERIFICAR.sub("", desc), "verificar": v.group(1) if v else ""})
    return out


def hashes(raiz, ficheiros):
    return {f: (hashlib.sha1((Path(raiz) / f).read_bytes()).hexdigest() if (Path(raiz) / f).is_file() else "") for f in ficheiros}


def decidir(estado, achados, maximo):
    bloq = [a for a in achados if a["sev"] == "bloqueante"]
    estado["iteracao"] = estado.get("iteracao", 0) + 1
    estado.setdefault("historico", []).append({"iteracao": estado["iteracao"], "bloqueantes": len(bloq), "menores": len(achados) - len(bloq), "achados": achados})
    estado["veredicto"] = "APROVADO" if not bloq else ("ESCALAR" if estado["iteracao"] >= maximo else "CORRIGIR")
    return estado["veredicto"], bloq


def main_ciclo(argv):
    ap = argparse.ArgumentParser(prog="auditar.py ciclo")
    ap.add_argument("estado")
    ap.add_argument("--achados", required=True)
    ap.add_argument("--max", type=int, default=3)
    ap.add_argument("--criar-sps", action="store_true")
    ap.add_argument("--project")
    ap.add_argument("--prefixo", default="auditar")
    ap.add_argument("--ficheiros", nargs="+")
    ap.add_argument("--raiz", default=".")
    a = ap.parse_args(argv)
    if a.criar_sps and not a.project:
        ap.error("--criar-sps exige --project")
    ep = Path(a.estado)
    estado = json.loads(ep.read_text(encoding="utf-8")) if ep.exists() else {}
    if estado.get("veredicto") in ("APROVADO", "ESCALAR"):
        print(f"{estado['veredicto']} (ciclo já terminado; apagar {ep.name} para recomeçar)")
        return 0 if estado["veredicto"] == "APROVADO" else 2
    rever = None
    if a.ficheiros:
        novos = hashes(a.raiz, a.ficheiros)
        antes = estado.get("hashes")
        rever = sorted(novos) if antes is None else sorted(f for f, h in novos.items() if antes.get(f) != h)
        estado["hashes"] = novos
    ver, bloq = decidir(estado, ler_achados(a.achados), a.max)
    if rever is not None:
        estado["historico"][-1]["rever"] = rever
    ep.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{ver} (iteração {estado['iteracao']}/{a.max}, {len(bloq)} bloqueantes)")
    for b in bloq:
        print(f"[bloqueante] {b['onde']} {b['desc']}" + (f" | verificar: {b['verificar']}" if b["verificar"] else ""))
    if rever is not None:
        print("Rever só: " + (", ".join(rever) or "(nada alterado)"))
    if ver == "CORRIGIR" and a.criar_sps:
        for slug, ok in criar_sps([{"tipo": "ciclo", "onde": b["onde"]} for b in bloq], a.project, f"{a.prefixo}-{estado['iteracao']}"):
            print(f"SP {slug}: {'criado' if ok else 'falhou'}")
    return {"APROVADO": 0, "CORRIGIR": 1, "ESCALAR": 2}[ver]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "ciclo":
        return main_ciclo(argv[1:])
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--modo", choices=["rapido", "normal", "total"], default="normal")
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--sp")
    ap.add_argument("--baseline")
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--criar-sps", action="store_true")
    ap.add_argument("--project")
    ap.add_argument("--prefixo", default="auditar")
    ap.add_argument("--relatorio")
    a = ap.parse_args(argv)
    if a.criar_sps and not a.project:
        ap.error("--criar-sps exige --project")
    bl = None
    bp = Path(a.baseline) if a.baseline else Path(a.repo) / ".auditar-baseline.json"
    if not a.no_baseline and bp.is_file():
        bl = json.loads(bp.read_text(encoding="utf-8"))
    ctx, conf, sus = auditar(a.repo, a.modo, a.base, Path(a.sp) if a.sp else None, bl)
    rep = relatorio(ctx, conf, sus)
    print(rep)
    if a.relatorio:
        Path(a.relatorio).write_text(rep + "\n", encoding="utf-8")
    if conf and a.criar_sps:
        for slug, ok in criar_sps(conf, a.project, a.prefixo):
            print(f"SP {slug}: {'criado' if ok else 'falhou'}")
    return 1 if conf else 0


if __name__ == "__main__":
    sys.exit(main())
