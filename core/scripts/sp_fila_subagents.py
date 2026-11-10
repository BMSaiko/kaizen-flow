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

SCRIPTS = Path(__file__).resolve().parent
ESTADOS = ("done", "pergunta", "bloqueado", "falhou")

_PROMPT = """Corre `/michi {slug}` em modo auto, dentro de um subagent da fila `/sp-fila`.

- Worktree já criada: `{worktree}`. Lê e escreve só lá, por caminho absoluto; não faças merge nem `clean`.
- Não tens `AskUserQuestion`: quando o michi pedir uma decisão ao user, pára e devolve a pergunta com as opções (recomendada primeiro).
- Commits na worktree só se o SP tiver `commit: auto` ou `modo: auto`; senão deixa o `COMMIT_*.md` gerado.
- Nunca saltes verificações do fecho (`sp-fechar.py --sem-budget`, `--sem-testes` ou semelhantes): se falharem, `ESTADO: bloqueado` com o erro.
- Termina com um resumo de ≤5 linhas (feito, provas, em aberto) e, na última linha, exatamente uma de:
  `ESTADO: done` (SP em Done na worktree) · `ESTADO: pergunta` (decisão do user em falta) · `ESTADO: bloqueado` (gate ou erro que não resolves) · `ESTADO: falhou`.
"""


def prompt(slug, worktree):
    """Prompt do subagent que corre o michi de `slug` na `worktree`."""
    return _PROMPT.format(slug=slug, worktree=worktree)


def lancar(slug, run=subprocess.run):
    """Cria (ou reusa) a worktree de `slug` e devolve o item do plano {slug, worktree, prompt}; RuntimeError se falhar."""
    r = run([sys.executable, "-I", str(SCRIPTS / "sb-worktree.py"), "ensure", slug], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"sb-worktree ensure {slug}: {(r.stderr or r.stdout or '').strip()}")
    linhas = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
    if not linhas:
        raise RuntimeError(f"sb-worktree ensure {slug}: sem caminho da worktree na saída")
    worktree = linhas[-1]
    return {"slug": slug, "worktree": worktree, "prompt": prompt(slug, worktree)}


def plano(itens):
    """Plano de lançamento em JSON (uma linha) para o agente principal: um `Agent` em background por item."""
    return json.dumps({
        "acao": "lancar",
        "itens": [{**i, "description": f"sp-fila {i['slug']}"[:60], "run_in_background": True} for i in itens],
        "no_fim": "por cada notificação de fim: ler a última linha `ESTADO:`; `pergunta` → AskUserQuestion ao user e SendMessage ao subagent; "
                  "`done` → `sb-worktree.py merge <slug>` com confirmação e depois `sp-fila.py --seguinte --slug <slug>`; "
                  "`bloqueado`/`falhou` → avisar o user e `sp-fila.py --seguinte --slug <slug>`",
    }, ensure_ascii=False)


def estado_final(texto):
    """Estado devolvido pelo subagent (última linha `ESTADO: x`); `desconhecido` se faltar ou não for válido."""
    for linha in reversed((texto or "").strip().splitlines()):
        if m := re.match(r"\s*ESTADO:\s*(\w+)\s*$", linha):
            return m.group(1) if m.group(1) in ESTADOS else "desconhecido"
    return "desconhecido"
