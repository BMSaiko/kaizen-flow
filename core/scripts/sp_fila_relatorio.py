"""Sp-fila: custo por sessão e relatório final / progresso da mãe."""
from pathlib import Path
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
from sp_fila_estado import REPO


def gastos(estado, custos):
    """[(slug, USD)] das sessões da corrida (em curso, feitas e falhadas) e o total. Só mede, nunca limita."""
    slugs = [*estado.get("sessoes", {}), *estado.get("feitos", []), *estado.get("falhados", [])]
    linhas = [(s, custos.get(s, 0.0)) for s in dict.fromkeys(slugs)]
    return linhas, sum(c for _, c in linhas)


def render_gastos(estado, custos):
    linhas, total = gastos(estado, custos)
    corpo = [f"  {s}: {c:.2f}" for s, c in linhas] or ["  (nenhuma sessão)"]
    return "\n".join(["Gasto por sessão (USD equivalente API, só medição):", *corpo, f"  total: {total:.2f}"])


def commits_desde(inicio, run):
    out = run(["git", "-C", str(REPO), "log", f"--since={inicio}", "--format=%h %s"], capture_output=True,
              text=True, encoding="utf-8").stdout or ""
    return [ln for ln in out.splitlines() if ln.strip()]


def reflect_lacunas(slug, texto):
    """Linhas `Reflect ...` do SP com gap (as «sem patch» não contam), prefixadas pelo slug."""
    return [f"{slug}: {l.strip()}" for l in texto.splitlines()
            if l.startswith("Reflect ") and not l.rstrip(". ").endswith("sem patch")]


MAX_LINHAS = 30


def relatorio(estado, fila, excluidos, motivo, rel_dir, run, agora, custos=None, sps=None):
    """Relatório final em ≤ MAX_LINHAS linhas: feito, parado, porquê, próximo passo (listas longas cortam em «+N mais»)."""
    rel_dir.mkdir(parents=True, exist_ok=True)
    path = rel_dir / f"fila-{agora:%Y-%m-%d-%H%M}.md"
    commits = commits_desde(estado["inicio"], run)
    passos = [f"inspecionar o SP falhado `{s}` (continua em Doing) e correr `/michi` à mão" for s in estado["falhados"]]
    passos += [f"por correr: `{sp.slug}`" for sp in fila if sp.slug not in estado["falhados"]]
    passos += ["rever os saltados e, se fizer sentido, dar-lhes `modo: auto` e `gates:`"] if excluidos else []
    secoes = [("Feitos", list(estado["feitos"])), ("Falhados", list(estado["falhados"])),
              ("Saltados", [f"{s}: {w}" for s, w in excluidos]),
              ("Gasto", [f"{s}: {c:.2f} USD" for s, c in gastos(estado, custos or {})[0]]), ("Commits", commits),
              ("Reflect (lacunas)", [l for s, (_, t) in (sps or {}).items() for l in reflect_lacunas(s, t)]),
              ("Falhas", [f"{s}: não chegou a Done (fase {sps[s][0]})" if s in (sps or {}) else f"{s}: não chegou a Done"
                          for s in estado["falhados"]]),
              ("Próximos passos", passos)]
    cabeca = ["---", "type: report", "tags: [sp-fila]", f"date: {agora:%Y-%m-%d}", "---",
              f"# Fila de SPs ({agora:%Y-%m-%d %H:%M})", f"Fim: {motivo}."]
    for cap in range(len(passos) + len(excluidos) + len(commits) + 99, 0, -1):
        corpo = []
        for nome, xs in secoes:
            corpo.append(f"## {nome}")
            corpo += [f"- {x}" for x in xs[:cap]] + ([f"- … +{len(xs) - cap} mais"] if len(xs) > cap else []) or ["- nenhum"]
        if len(cabeca) + len(corpo) <= MAX_LINHAS:
            break
    path.write_text(chr(10).join(cabeca + corpo) + chr(10), encoding="utf-8")
    return path


def progresso(mae_path, estado, fila, motivo, agora):
    """Acrescenta `## Progresso (sessão <data>)` à mãe: feitos, falhados, por correr."""
    listar = lambda xs: [f"- {x}" for x in xs] or ["- nenhum"]
    porcorrer = [sp.slug for sp in fila if sp.slug not in estado["falhados"]]
    linhas = ["", f"## Progresso (sessão {agora:%Y-%m-%d %H:%M})", "", f"Paragem: {motivo}.", "", "Feitos:",
              *listar(estado["feitos"]), "", "Falhados:", *listar(estado["falhados"]), "", "Por correr:",
              *listar(porcorrer), ""]
    with Path(mae_path).open("a", encoding="utf-8") as f:
        f.write("\n".join(linhas))
