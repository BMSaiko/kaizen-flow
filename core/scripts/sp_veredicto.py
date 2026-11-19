"""Ação ligada a cada veredicto de `/rever` (usado por sp-rever.py): ajuste, redirecionamento, merge do PR, arranque.

Cada função devolve um dict de campos para a entrada de `~/.claude/sp-revisao.json` (`acao`: em-todo, em-espera,
a-correr, fechado, falhou) e recebe os efeitos por injeção (`run`, `lancar`, `spawn`, `vagas`, `validar`), por isso
testa-se sem painéis nem rede. A frase do user só viaja em ficheiros (semente e `## Decisões`), nunca numa linha de comando.

Uso: módulo importado por sp-rever.py; sem execução direta
rc: n/a
"""
import json
import re
from pathlib import Path as _P
import sys as _s
_s.path.insert(0, str(_P(__file__).resolve().parent))
from painel_backend import run_hidden  # noqa: E402
import sys
import tempfile
from datetime import datetime, timezone, UTC
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SUFIXO_DATA = re.compile(r"-\d{4}-\d{2}-\d{2}$")
AJUSTE = re.compile(r"-ajuste-(\d+)$")
VERDES = {"SUCCESS", "NEUTRAL", "SKIPPED"}
MAX_SUGESTAO = 2  # com 2 ajustes feitos, o 3.º pede `redirecionar`


class VeredictoErro(Exception):
    pass


def base_slug(slug):
    """`proj-algo-ajuste-2-2026-11-14` e `proj-algo-2026-11-13` -> `proj-algo`."""
    return AJUSTE.sub("", SUFIXO_DATA.sub("", slug))


def numero_ajuste(slug):
    """N de `...-ajuste-N-<data>`, ou 0 se o slug não for de ajuste."""
    m = AJUSTE.search(SUFIXO_DATA.sub("", slug))
    return int(m.group(1)) if m else 0


def cadeia(slug, raiz):
    """Ajustes já criados sobre o mesmo original (qualquer pasta de estado)."""
    padrao = re.compile(re.escape(base_slug(slug)) + r"-ajuste-(\d+)(?:-\d{4}-\d{2}-\d{2})?\.md$")
    return len({f.name for f in Path(raiz).glob("*/sp/*/*.md") if padrao.match(f.name)})


def _frontmatter(path):
    txt = Path(path).read_text(encoding="utf-8", errors="replace")
    m = re.match(r"---\r?\n(.*?)\r?\n---", txt, re.S)
    fm, gates = {}, []
    for ln in (m.group(1).splitlines() if m else []):
        g = re.match(r"\s+-\s+cmd:\s*(.*)$", ln)
        if g:
            gates.append(g.group(1).strip().strip("'\""))
        elif ln and not ln.startswith((" ", "-")) and ":" in ln:
            k, _, v = ln.partition(":")
            fm[k.strip()] = v.strip().strip("'\"")
    fm["_gates"] = gates
    return fm


def _original(slug, raiz):
    for p in Path(raiz).glob("*/sp/*/*.md"):
        if p.stem == slug:
            return p
    raise VeredictoErro(f"SP original não encontrado: {slug}")


def _frase(frase):
    if not isinstance(frase, str) or not frase.strip():
        raise VeredictoErro("frase vazia")
    return frase.strip()


def _semente(semente_dir, nome, linhas):
    fd, tmp = tempfile.mkstemp(dir=str(semente_dir), prefix=f"semente-{nome}-", suffix=".md")
    with open(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    return tmp


def _contexto(slug, original, provas, frase):
    out = [f"# Veredicto sobre {slug}", f"SP original: {original}"]
    for chave, tit in (("objetivo", "Objetivo"), ("feito", "Feito"), ("gates", "Gates"), ("reverter", "Reverter"), ("pr", "PR")):
        v = (provas or {}).get(chave)
        if v:
            out.append(f"## {tit}")
            out.append("\n".join(map(str, v)) if isinstance(v, list) else json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else str(v))
    out += ["## Frase do user (literal)", frase]
    return out


def _acrescentar_decisao(sp, frase):
    """Acrescenta a frase ao fim de `## Decisões` editando o ficheiro (bytes: preserva CRLF)."""
    p = Path(sp)
    raw = p.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    linha = "- Veredicto do user (literal): " + " ".join(frase.split())
    if "## Decisões" in raw:
        antes, _, depois = raw.partition("## Decisões")
        m = re.search(r"\r?\n## ", depois)
        corpo, resto = (depois[:m.start()], depois[m.start():]) if m else (depois, "")
        raw = antes + "## Decisões" + corpo.rstrip("\r\n") + nl + linha + nl + resto
    else:
        raw = raw.rstrip("\r\n") + nl + nl + "## Decisões" + nl + linha + nl
    p.write_bytes(raw.encode("utf-8"))


def criar_ajuste(slug, frase, raiz, provas, run=run_hidden, semente_dir=None, lancar=None):
    """Cria `<base>-ajuste-<n>` com as autorizações e gates do original; fica em TODO (`acao: em-todo`)."""
    frase = _frase(frase)
    original = _original(slug, raiz)
    fm = _frontmatter(original)
    n = cadeia(slug, raiz) + 1
    novo = f"{base_slug(slug)}-ajuste-{n}"
    cmd = [sys.executable, "-I", str(SCRIPTS / "sp-new.py"), "--project", fm.get("project") or original.parts[-4],
           "--slug", novo, "--priority", fm.get("priority") or "P2", "--origem", f"veredicto:{slug}", "--root", str(raiz)]
    for flag, campo in (("--modo", "modo"), ("--michi", "michi_modelo"), ("--commit", "commit"), ("--push", "push"),
                        ("--pr", "pr"), ("--merge", "merge")):
        if fm.get(campo):
            cmd += [flag, fm[campo]]
    for g in fm["_gates"]:
        cmd += ["--gate", g]
    r = run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0 or not (r.stdout or "").strip():
        raise VeredictoErro(f"sp-new falhou: {(r.stderr or r.stdout or '').strip()[:300]}")
    sp = (r.stdout.strip().splitlines() or [""])[0].strip()
    if not Path(sp).is_file():
        raise VeredictoErro(f"sp-new não criou o ficheiro: {sp}")
    _acrescentar_decisao(sp, frase)
    semente = _semente(semente_dir or tempfile.gettempdir(), "ajuste", _contexto(slug, original, provas, frase))
    res = {"acao": "em-todo", "ajuste": Path(sp).stem, "sp": sp, "semente": semente, "n": n}
    if lancar:
        pre = lancar(sp, semente)
        if (pre or {}).get("estado") == "falhou":
            res["motivo"] = (pre or {}).get("msg") or "sp-autor falhou"
    return res


def arrancar_ajuste(info, validar, vagas, spawn):
    """Valida o SP e lança o michi; sem vaga fica `em-espera`. `info`: {ajuste, sp}."""
    ok, msg = validar(info["sp"])
    if not ok:
        return {"acao": "falhou", "motivo": f"SP inválido: {msg}"}
    if vagas() <= 0:
        return {"acao": "em-espera", "espera": datetime.now(UTC).isoformat(timespec="seconds")}
    res = (spawn([info["ajuste"]]) or [{}])[0]
    if res.get("ok"):
        return {"acao": "a-correr"}
    return {"acao": "falhou", "motivo": res.get("erro") or "arranque falhou"}


def retomar_em_espera(dados, arrancar, vagas):
    """Arranca as entradas `em-espera` enquanto houver vagas; devolve {slug: campos novos}."""
    upd = {}
    for slug, e in dados.items():
        if not (isinstance(e, dict) and e.get("acao") == "em-espera"):
            continue
        if vagas() <= 0:
            break
        upd[slug] = arrancar(e)
    return upd


def prompt_grill(sp, semente):
    """Prompt numa só linha do painel de grill de `redirecionar` (a frase fica na semente)."""
    return (f"Corre `python -I scripts/sp-autor.py --consume \"{semente}\"` (contexto do veredicto sobre {Path(sp).stem}: SP original, "
            "pacote de provas e a frase do user; lida e apagada) e depois `/grill-me`. Na 1.ª ronda pergunta «reverter o trabalho "
            "anterior?» com o comando de «Reverter» da semente pronto (revert por commit novo ou fecho de PR; nunca reset --hard nem force). "
            "O SP que sair passa pelo portão normal (resumo e aprovação).")


def abrir_redirecionar(slug, frase, raiz, provas, semente_dir=None, lancar=None):
    """Abre um painel interativo de grill com foco; sem vaga fica `em-espera`."""
    frase = _frase(frase)
    original = _original(slug, raiz)
    semente = _semente(semente_dir or tempfile.gettempdir(), "grill", _contexto(slug, original, provas, frase))
    r = lancar(str(original), semente, rotulo="grill", prompt_fn=prompt_grill, foco=True)
    est = (r or {}).get("estado")
    if est == "a-correr":
        return {"acao": "a-correr", "semente": semente}
    if est == "pendente":
        return {"acao": "em-espera", "semente": semente, "motivo": (r or {}).get("msg") or "sem vaga"}
    return {"acao": "falhou", "semente": semente, "motivo": (r or {}).get("msg") or "grill falhou"}


def merge_pr_se_verde(provas, run=run_hidden):
    """Merge do PR (sem force nem `--admin`) só se estiver aberto e com ≥1 check, todos verdes."""
    pr = (provas or {}).get("pr") if isinstance(provas, dict) else ""
    if not (isinstance(pr, str) and pr.startswith("http")):
        return {"merge": "sem-pr"}
    r = run(["gh", "pr", "view", pr, "--json", "state,statusCheckRollup"], capture_output=True, text=True, encoding="utf-8")
    try:
        d = json.loads(r.stdout or "{}") if r.returncode == 0 else None
    except ValueError:
        d = None
    if not isinstance(d, dict):
        return {"merge": "recusado", "motivo": "não consegui ler o PR (gh)"}
    if d.get("state") != "OPEN":
        return {"merge": "recusado", "motivo": f"PR não está aberto ({d.get('state')})"}
    checks = d.get("statusCheckRollup") or []
    if not checks:
        return {"merge": "recusado", "motivo": "PR sem checks"}
    maus = [c for c in checks if c.get("status", "COMPLETED") != "COMPLETED" or c.get("conclusion") not in VERDES]
    if maus:
        return {"merge": "recusado", "motivo": f"{len(maus)} check(s) por passar ou vermelhos"}
    m = run(["gh", "pr", "merge", pr, "--merge"], capture_output=True, text=True, encoding="utf-8")
    if m.returncode != 0:
        return {"merge": "recusado", "motivo": (m.stderr or m.stdout or "gh pr merge falhou").strip()[:300]}
    return {"merge": "feito"}
