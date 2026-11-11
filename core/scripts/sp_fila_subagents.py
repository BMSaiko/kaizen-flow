"""Backend de subagents do `/sp-fila` paralelo: cada SP elegível corre num subagent `Agent` em background.

O script não lança nada: prepara a worktree de cada SP (`sb-worktree.py ensure`) e imprime o plano em JSON;
o agente principal chama `Agent` por item e, na notificação de fim, corre `sp-fila.py --seguinte --slug <slug>`.
Não se usa `isolation: "worktree"` do `Agent`: parte do ramo por defeito (`main`), não de `master`.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import modelos
except ImportError:  # kaizen-flow sem modelos.py
    modelos = None

SCRIPTS = Path(__file__).resolve().parent
ESTADOS = ("done", "pergunta", "bloqueado", "falhou", "continuar")

_PROMPT = """Corre `/michi {slug}` em modo auto, dentro de um subagent da fila `/sp-fila`.

- Worktree já criada: `{worktree}`. Lê e escreve só lá, por caminho absoluto; não faças merge nem `clean`.
- Não tens `AskUserQuestion`: quando o michi pedir uma decisão ao user, pára e devolve a pergunta com as opções (recomendada primeiro).
- Commits na worktree só se o SP tiver `commit: auto` ou `modo: auto`; senão deixa o `COMMIT_*.md` gerado.
- Nunca saltes verificações do fecho (`sp-fechar.py --sem-budget`, `--sem-testes` ou semelhantes): se falharem, `ESTADO: bloqueado` com o erro.
- Fases delegadas (DR, gates, harden, review, report, reflect): usa `Agent` se o tiveres; senão corre-as tu. Nunca abras painéis nem `sp-handoff --launch`.
- `[context-guard]` ou contexto a acabar: grava `## Progresso` no SP e devolve `ESTADO: continuar`.
- Termina com um resumo de ≤5 linhas (feito, provas, em aberto) e, na última linha, exatamente uma de:
  `ESTADO: done` (SP em Done na worktree) · `ESTADO: pergunta` (decisão do user em falta) · `ESTADO: bloqueado` (gate ou erro que não resolves) · `ESTADO: falhou` · `ESTADO: continuar` (progresso gravado; relançar).
"""


def prompt(slug, worktree):
    """Prompt do subagent que corre o michi de `slug` na `worktree`."""
    return _PROMPT.format(slug=slug, worktree=worktree)


def nivel_sp(slug, root=None):
    """`michi_modelo` do frontmatter do SP `slug` (TODO/Doing/Done em `root`); None se faltar o SP ou o campo."""
    root = Path(root) if root else SCRIPTS.parent
    for f in (root / "knowledge" / "projects").glob(f"*/*/sp/*/{slug}.md"):
        m = re.search(r"\A---\n(.*?)\n---", f.read_text(encoding="utf-8"), re.S)
        n = m and re.search(r"^michi_modelo:\s*(\S+)\s*$", m.group(1), re.M)
        return n.group(1) if n else None
    return None


def lancar(slug, run=subprocess.run, root=None):
    """Cria (ou reusa) a worktree de `slug` e devolve o item {slug, worktree, prompt, michi_modelo}; RuntimeError se falhar."""
    r = run([sys.executable, "-I", str(SCRIPTS / "sb-worktree.py"), "ensure", slug], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"sb-worktree ensure {slug}: {(r.stderr or r.stdout or '').strip()}")
    linhas = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
    if not linhas:
        raise RuntimeError(f"sb-worktree ensure {slug}: sem caminho da worktree na saída")
    worktree = linhas[-1]
    return {"slug": slug, "worktree": worktree, "prompt": prompt(slug, worktree), "michi_modelo": nivel_sp(slug, root)}


def modelo_agent(nivel=None):
    """ID do modelo do nível michi (`modelos.michi`; vazio = default) para o `model` do `Agent`; None sem modelos.py ou config válida."""
    if modelos is None:
        return None
    try:
        return modelos.michi(modelos.load(), nivel or "default")[0]["model"]
    except (modelos.ModelosError, OSError, KeyError, TypeError):
        return None


def item_agent(i, description=None):
    """Item do plano para o `Agent`: modelo do nível do SP (se houver modelos.py), `effort: low`, em background."""
    model = modelo_agent(i.get("michi_modelo")) if modelos is not None else None
    extra = {"model": model} if model else {}
    return {**i, "description": (description or f"sp-fila {i['slug']}")[:60], "run_in_background": True, "effort": "low", **extra}


def plano(itens):
    """Plano de lançamento em JSON (uma linha) para o agente principal: um `Agent` em background por item."""
    return json.dumps({
        "acao": "lancar",
        "itens": [item_agent(i) for i in itens],
        "no_fim": "por cada notificação de fim: ler a última linha `ESTADO:`; `pergunta` → AskUserQuestion ao user e SendMessage ao subagent; "
                  "`done` → `sb-worktree.py merge <slug>` com confirmação e depois `sp-fila.py --seguinte --slug <slug>`; "
                  "`continuar` → lançar outro `Agent` com o mesmo item; "
                  "`bloqueado`/`falhou` → avisar o user e `sp-fila.py --seguinte --slug <slug>`",
    }, ensure_ascii=False)


def estado_final(texto):
    """Estado devolvido pelo subagent (última linha `ESTADO: x`); `desconhecido` se faltar ou não for válido."""
    for linha in reversed((texto or "").strip().splitlines()):
        if m := re.match(r"\s*ESTADO:\s*(\w+)\s*$", linha):
            return m.group(1) if m.group(1) in ESTADOS else "desconhecido"
    return "desconhecido"
