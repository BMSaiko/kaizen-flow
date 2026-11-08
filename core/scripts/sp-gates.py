#!/usr/bin/env python3
"""Corre os gates declarados no frontmatter de um SP, por ordem, e pára no primeiro vermelho.

Só lê o campo `gates:` do frontmatter (nunca o corpo do SP). Formato:
  gates:
    - cmd: python -I scripts/test_sp_list.py
      cwd: .          # opcional, defeito = diretório de trabalho atual
      timeout: 300    # opcional, segundos, defeito 300
      inputs: a/*.py, b.md   # opcional, globs (relativos a cwd): sem mudança desde a última corrida verde, o gate é saltado
RC 0 = todos verdes (ou SP sem gates); 1 = gate vermelho/timeout; 2 = gate inválido ou proibido (nada corre).

Uso:
  python -I scripts/sp-gates.py <caminho.md>          # incremental: salta gates verdes com inputs iguais
  python -I scripts/sp-gates.py <caminho.md> --full   # corre todos (o fecho, sp-fechar.py, usa sempre isto)
  python -I scripts/sp-gates.py --sugerir <repo>      # gates por tipo de repo (Node, Python, Tauri, vault), bloco `gates:` pronto
  python -I scripts/sp-gates.py --testes <repo> --sp <SP>  # fase de testes: corre `test.cmd` de <repo>/kaizen.config.json,
                                                       # regista `## Testes` no SP; rc 0 verde, 1 vermelho, 2 proibido,
                                                       # 3 sem test.cmd (perguntar ao user), 4 limite de tentativas
Ordem da fase 5: gates -> harden -> pentest -> review (michi/references/michi-gates.md).
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

DEFAULT_TIMEOUT = 300
RC_SEM_COMANDO = 3  # fase de testes sem `test.cmd` na config
RC_LIMITE = 4  # fase de testes: max_tentativas atingido com `gate-falha` em parar_se
TESTES_HEADING = "## Testes"
HERE_REPO = Path(__file__).resolve().parent.parent
CACHE_PATH = Path(__file__).resolve().parent.parent / ".sp-gates-cache.json"
FORBIDDEN = (
    (re.compile(r"(?<![\w-])--force(?![\w-])|\bgit\s+push\b.*\s-f\b"), "--force"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "git reset --hard"),
    (re.compile(r"\bgit\s+clean\b.*\s-\w*f"), "git clean -f"),
    (re.compile(r"\bgit\s+add\s+(-A\b|--all\b|\.(\s|$))"), "git add -A/."),
    (re.compile(r"\.env(\.|\b)|\.(key|pem|p12|pfx)\b|\bid_rsa|\bsecrets?\.|\.secrets"), "leitura de segredos"),
)


def sp_roots(slug, repo=None):
    """Raízes onde procurar o SP `slug`: a worktree do slug primeiro (o SP pode só existir lá), depois `repo`."""
    repo = Path(repo or HERE_REPO)
    roots = []
    try:
        wt_mod = kaizen_engine.load("sb-worktree")
        wt = wt_mod._find(wt_mod.agent.main_root(repo), wt_mod.name_of(slug))
        if wt:
            roots.append(Path(wt))
    except Exception:  # sem git/worktree: cai para `repo`
        pass
    roots.append(repo)
    return roots


def resolve_sp(arg, roots=None):
    """(caminho do SP, raiz) para um caminho .md existente ou um slug; (None, None) se não existe."""
    p = Path(arg)
    if p.suffix == ".md" or p.exists():
        return (p, None) if p.exists() else (None, None)
    sp_list = kaizen_engine.load("sp-list")
    for root in (roots if roots is not None else sp_roots(arg)):
        for sp in sp_list.collect(sp_list.default_root(root), include_done=True):
            if sp.slug == arg:
                return sp.path, Path(root)
    return None, None


def detect_gates(repo):
    """Comandos de gate sugeridos para o tipo de repo em `repo` (lista de `cmd`, por ordem)."""
    r = Path(repo)
    if (r / "tools" / "vault-mcp").exists() and (r / "scripts" / "context-budget.py").exists():
        return ["python -I scripts/context-budget.py", "python -I scripts/test-fast.py"]
    cmds = []
    if (r / "src-tauri" / "Cargo.toml").exists():
        cmds.append("cargo check --manifest-path src-tauri/Cargo.toml")
    if (r / "package.json").exists():
        try:
            scripts = json.loads((r / "package.json").read_text(encoding="utf-8")).get("scripts", {})
        except (OSError, ValueError):
            scripts = {}
        cmds += [f"npm run {n}" for n in ("lint", "typecheck", "build") if n in scripts]
        if "test" in scripts:
            cmds.append("npm test")
    if (r / "pyproject.toml").exists() or (r / "pytest.ini").exists() or (r / "setup.cfg").exists():
        cmds.append("python -m pytest -q")
    return cmds


def suggestion(repo):
    """Bloco `gates:` de frontmatter para o repo, ou texto vazio se o tipo é desconhecido."""
    cmds = detect_gates(repo)
    if not cmds:
        return ""
    return "gates:\n" + "\n".join(f"  - cmd: {c}\n    timeout: 300" for c in cmds)


def forbidden(cmd):
    """Devolve o nome da proibição em que `cmd` cai, ou None."""
    for rx, name in FORBIDDEN:
        if rx.search(cmd):
            return name
    return None


def parse_gates(text):
    gates, in_gates, current = [], False, None
    for line in kaizen_engine.frontmatter_lines(text):
        if re.match(r"^gates:\s*$", line):
            in_gates = True
            continue
        if not in_gates:
            continue
        if line and not line[0].isspace():
            break
        m = re.match(r"^\s*-\s*cmd:\s*(.*?)\s*$", line)
        if m:
            current = {"cmd": m.group(1), "cwd": ".", "timeout": DEFAULT_TIMEOUT, "inputs": []}
            gates.append(current)
            continue
        m = re.match(r"^\s+(cwd|timeout|inputs):\s*(.*?)\s*$", line)
        if m and current is not None:
            if m.group(1) == "timeout":
                current["timeout"] = int(m.group(2))
            elif m.group(1) == "inputs":
                current["inputs"] = [x.strip().strip("'\"") for x in m.group(2).split(",") if x.strip()]
            else:
                current["cwd"] = m.group(2).strip("'\"")
    return gates


def problems(gates):
    found, seen = [], set()
    for i, g in enumerate(gates, 1):
        cmd = g["cmd"].strip()
        if not cmd:
            found.append(f"gate {i}: comando vazio")
            continue
        if cmd in seen:
            found.append(f"gate {i}: comando duplicado '{cmd}'")
        seen.add(cmd)
        bad = forbidden(cmd)
        if bad:
            found.append(f"gate {i}: comando proibido ({bad}): {cmd}")
    return found


def input_hash(g):
    """Hash do comando + conteúdo dos ficheiros que casam com `inputs`; None se não há inputs."""
    if not g.get("inputs"):
        return None
    base = Path(g["cwd"])
    h = hashlib.sha256(g["cmd"].encode("utf-8"))
    files = sorted({p for pat in g["inputs"] for p in base.glob(pat) if p.is_file()})
    for p in files:
        h.update(str(p.relative_to(base)).encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()


def _load_cache(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run(gates, cache_path=None):
    """Corre por ordem; pára no primeiro rc≠0 ou timeout. Devolve os resultados corridos.

    Com `cache_path`, um gate com `inputs` cujo hash coincide com a última corrida verde é saltado
    (resultado com `cached`). Sem `cache_path` corre sempre tudo.
    """
    cache = _load_cache(cache_path) if cache_path else {}
    results = []
    for g in gates:
        digest = input_hash(g) if cache_path else None
        key = f"{Path(g['cwd']).resolve()}::{g['cmd']}"
        if digest and cache.get(key) == digest:
            results.append({"cmd": g["cmd"], "rc": 0, "timeout": False, "secs": 0, "tail": "", "cached": True})
            continue
        start = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(g["cmd"], shell=True, cwd=g["cwd"], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=g["timeout"])
            rc, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired as exc:
            rc, timed_out = 124, True
            out = (exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else exc.stdout) or ""
        results.append({"cmd": g["cmd"], "rc": rc, "timeout": timed_out,
                        "secs": round(time.monotonic() - start, 1),
                        "tail": "\n".join(out.strip().splitlines()[-10:])})
        if digest:
            if rc == 0:
                cache[key] = digest
            else:
                cache.pop(key, None)
        if rc != 0:
            break
    if cache_path:
        try:
            Path(cache_path).write_text(json.dumps(cache, indent=1), encoding="utf-8")
        except OSError:
            pass
    return results


def summary(results):
    lines = []
    for r in results:
        flag = " TIMEOUT" if r["timeout"] else ""
        when = "cache" if r.get("cached") else f"{r['secs']} s"
        lines.append(f"- `{r['cmd']}` rc={r['rc']}{flag} ({when})")
        if r["tail"]:
            lines += [f"    {t}" for t in r["tail"].splitlines()]
    return "\n".join(lines)


def table(results, total):
    """Tabela final `# | comando | RC | estado`; gates não corridos (após um vermelho) ficam «não correu»."""
    rows = ["| # | comando | RC | estado |", "|---|---|---|---|"]
    for i, r in enumerate(results, 1):
        state = "TIMEOUT" if r["timeout"] else ("cache" if r.get("cached") else ("verde" if r["rc"] == 0 else "VERMELHO"))
        rows.append(f"| {i} | `{r['cmd']}` | {r['rc']} | {state} |")
    rows += [f"| {i} | — | — | não correu |" for i in range(len(results) + 1, total + 1)]
    return "\n".join(rows)


def test_cmd(repo):
    """`test.cmd` de `<repo>/kaizen.config.json`; None se falta, é ilegível ou está vazio."""
    try:
        cfg = json.loads((Path(repo) / "kaizen.config.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    sec = cfg.get("test") if isinstance(cfg, dict) else None
    cmd = sec.get("cmd") if isinstance(sec, dict) else None
    return cmd.strip() if isinstance(cmd, str) and cmd.strip() else None


def fase_testes(repo, timeout=DEFAULT_TIMEOUT):
    """Fase de testes: corre o `test.cmd` da config do projeto-alvo, em `repo`, como gate.

    Devolve (rc, resultados): 0 verde; 1 vermelho/timeout; 2 comando proibido (nada corre);
    RC_SEM_COMANDO sem `test.cmd` (nada corre). Só corre comandos vindos da config, nunca de argumentos.
    """
    cmd = test_cmd(repo)
    if cmd is None:
        return RC_SEM_COMANDO, []
    if forbidden(cmd):
        return 2, []
    results = run([{"cmd": cmd, "cwd": str(repo), "timeout": timeout, "inputs": []}])
    return (0 if results[0]["rc"] == 0 else 1), results


def tentativas(text):
    """Falhas seguidas registadas na secção `## Testes` desde o último verde."""
    n = 0
    for m in re.finditer(r"^- tentativa \d+: .*? rc=(\d+)", text, re.M):
        n = 0 if m.group(1) == "0" else n + 1
    return n


def registar(sp_path, results, aviso=None):
    """Acrescenta uma linha à secção `## Testes` do SP (cria-a se falta; preserva CRLF) e devolve o nº da tentativa.

    Sem resultados, `aviso` fica como linha própria e não conta como tentativa.
    """
    path = Path(sp_path)
    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    lines = raw.replace("\r\n", "\n").rstrip("\n").split("\n")
    total = sum(1 for ln in lines if ln.startswith("- tentativa "))
    stamp = time.strftime("%Y-%m-%d %H:%M")
    if results:
        r = results[0]
        state = "TIMEOUT" if r["timeout"] else ("verde" if r["rc"] == 0 else "VERMELHO")
        total += 1
        new = f"- tentativa {total}: `{r['cmd']}` rc={r['rc']} {state} ({r['secs']} s) — {stamp}"
    else:
        new = f"- aviso: {aviso or 'testes não correram'} — {stamp}"
    if TESTES_HEADING in lines:
        i = lines.index(TESTES_HEADING) + 1
        while i < len(lines) and not lines[i].startswith("## "):
            i += 1
        while lines[i - 1].strip() == "":
            i -= 1
        lines.insert(i, new)
    else:
        lines += ["", TESTES_HEADING, new]
    path.write_text("\n".join(lines).replace("\n", "\r\n" if crlf else "\n") + ("\r\n" if crlf else "\n"),
                    encoding="utf-8", newline="")
    return total


def deve_parar(sp_path):
    """True se as falhas seguidas atingiram `max_tentativas` e o `parar_se` do SP inclui `gate-falha` (como o DA)."""
    text = Path(sp_path).read_text(encoding="utf-8")
    return kaizen_engine.load("da-stop").decide(sp_path, tentativas(text)) == "parar"


def _main_testes(repo, sp_arg, timeout):
    sp_path = None
    if sp_arg:
        sp_path, _ = resolve_sp(sp_arg)
        if sp_path is None:
            print(f"{sp_arg}: SP não encontrado", file=sys.stderr)
            return 2
        if deve_parar(sp_path):
            print("limite de tentativas atingido (max_tentativas + parar_se: gate-falha): parar e escalar ao user, "
                  "sem correr os testes de novo", file=sys.stderr)
            return RC_LIMITE
    rc, results = fase_testes(repo, timeout)
    if rc == RC_SEM_COMANDO:
        print(f"sem test.cmd em {Path(repo) / 'kaizen.config.json'}: nada correu. Perguntar ao user (AskUserQuestion) "
              "qual o comando de testes e gravá-lo na config, ou correr `kaizen init`", file=sys.stderr)
        if sp_path:
            registar(sp_path, [], aviso="sem test.cmd na config, testes não correram")
        return rc
    if rc == 2:
        print(f"test.cmd proibido ({forbidden(test_cmd(repo))}): nada correu", file=sys.stderr)
        return rc
    print(summary(results))
    print(table(results, 1))
    if sp_path:
        registar(sp_path, results)
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(description="Corre os gates do frontmatter de um SP")
    ap.add_argument("path", nargs="?")
    ap.add_argument("--sugerir", metavar="REPO", help="imprime o bloco gates: sugerido para o tipo de repo")
    ap.add_argument("--full", action="store_true", help="ignora a cache: corre todos os gates")
    ap.add_argument("--testes", metavar="REPO", help="fase de testes: corre o test.cmd da config do REPO")
    ap.add_argument("--sp", help="com --testes: SP (caminho ou slug) onde registar a tentativa e ler os limites")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="com --testes: segundos (defeito 300)")
    args = ap.parse_args(argv)
    if args.testes:
        return _main_testes(args.testes, args.sp, args.timeout)
    if args.sugerir:
        block = suggestion(args.sugerir)
        print(block or "tipo de repo desconhecido: declarar os gates à mão", file=None if block else sys.stderr)
        return 0 if block else 1
    if not args.path:
        ap.error("falta o caminho do SP (ou --sugerir REPO)")
    sp_path, _ = resolve_sp(args.path)
    try:
        if sp_path is None:
            raise FileNotFoundError(args.path)
        text = sp_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"{args.path}: erro de leitura ({exc.__class__.__name__})", file=sys.stderr)
        return 2
    gates = parse_gates(text)
    if not gates:
        print("sem gates declarados no SP")
        return 0
    bad = problems(gates)
    if bad:
        print("\n".join(bad), file=sys.stderr)
        return 2
    results = run(gates, cache_path=None if args.full else CACHE_PATH)
    print(summary(results))
    print(table(results, len(gates)))
    return 0 if all(r["rc"] == 0 for r in results) and len(results) == len(gates) else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-gates", main))
