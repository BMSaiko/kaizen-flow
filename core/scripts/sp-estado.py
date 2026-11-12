#!/usr/bin/env python3
"""Estado de um SP numa só leitura (≤30 linhas) e estado de painel na fila (gravar, listar, migrar).

Só com o slug: junta o que o arranque de `/michi <SP>` ou de um handoff lê em chamadas separadas
(pasta/fase, critérios e passos, gates, dependências, últimas linhas de `## Progresso`, ramo e
ficheiros alterados no git), sem escrever nada.

Com slug e estado: grava o estado do SP na fila que o regista (`scripts/sp_painel_estado.py`,
`~/.claude/sp-fila/<fila-id>/<slug>.json`); é o comando que um painel corre. `--listar` mostra
todas as filas e SPs pelo nome; `--migrar` converte o `~/.claude/sp-fila-estado.json` antigo.

Uso:
  python -I scripts/sp-estado.py <slug|caminho.md> [--project P]
  python -I scripts/sp-estado.py <slug> <pendente|a-correr|pergunta|done|bloqueado|falhou> [--msg "<texto>"] [--fila ID] [--root DIR]
  python -I scripts/sp-estado.py --listar [--json] [--root DIR]
  python -I scripts/sp-estado.py --migrar [--antigo FICHEIRO] [--root DIR]
rc: 0 ok, 1 SP não encontrado, transição inválida, sem vaga, slug desconhecido ou estado ilegível
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kf_git  # noqa: E402
import kaizen_engine  # noqa: E402
import sp_leitura  # noqa: E402
import sp_painel_estado  # noqa: E402

MAX_LINES = 30
MAX_FILES = 8
MAX_PROGRESSO = 3


def section(text, prefix):
    """Corpo da secção `## <prefix>...` até à seguinte `## `."""
    return sp_leitura.seccao(text, prefix)


def git_state():
    def run(*a):
        r = kf_git.run(HERE.parent, *a, run=subprocess.run)
        return r.stdout.splitlines()
    return run("rev-parse", "--abbrev-ref", "HEAD")[:1] + run("status", "--short")


def estado(ref, root=None, project=None, git_lines=None, atras=None):
    sp_list = kaizen_engine.load("sp-list")
    sp_gates = kaizen_engine.load("sp-gates")
    root = Path(root) if root else sp_list.default_root()
    sps = sp_list.collect(root, include_done=True)
    alvo = None
    p = Path(ref)
    ref = sp_list.normalize_ref(root, ref)
    for sp in sps:
        if (p.suffix == ".md" and sp.path.resolve() == p.resolve()) or sp.slug == ref:
            if project is None or sp.project == project:
                alvo = sp
                break
    if alvo is None:
        return f"SP não encontrado: {ref}"
    text = alvo.path.read_text(encoding="utf-8")
    fm = kaizen_engine.parse_frontmatter(text)
    done = {s.slug for s in sps if s.status == "Done"}
    unmet = [d for d in alvo.depends_on if d not in done]

    crit = re.findall(r"^- \[([ xX])\]", section(text, "4."), re.M)
    feitos = sum(1 for c in crit if c.lower() == "x")
    passos = re.findall(r"^\d+\.\s+(.*)", section(text, "7."), re.M)
    prog = [l for l in section(text, "Progresso").splitlines() if l.strip()][-MAX_PROGRESSO:]
    gl = git_lines if git_lines is not None else git_state()
    ramo, ficheiros = (gl[0] if gl else "?"), gl[1:]

    filhos = [s for s in sps if s.parent == alvo.slug and s.project == alvo.project]
    out = [
        f"{alvo.slug} · {alvo.status} · {alvo.priority} · {alvo.project} · modo {fm.get('modo', '-')}",
        f"parent: {alvo.parent or '-'} · dependências: " + (("por cumprir " + ", ".join(unmet)) if unmet else ("ok" if alvo.depends_on else "-")),
        f"critérios: {feitos}/{len(crit)} · gates: {len(sp_gates.parse_gates(text))} · michi: {fm.get('michi_modelo') or 'default'}",
        f"passos ({len(passos)}): " + " | ".join(s.rstrip(".") for s in passos[:6]),
    ]
    if str(fm.get("spike", "")).strip() == "incerto":
        out.append(f"spike: incerto · max_requests {fm.get('max_requests', 15)} · fase 2b antes do DP")
    if filhos:
        out.append(f"filhos: {len(filhos)} filhos")
    if fm.get("kind") == "program":
        out.append(f"execução: {fm['execucao']}" if fm.get("execucao") else "execução: por escolher · perguntar sequencial/paralelo")
    if prog:
        out.append("progresso:")
        out += [f"  {l.strip()}" for l in prog]
    n = atras if atras is not None else kf_git.atras_de(HERE.parent)
    if n:
        out.append(f"⚠ ramo {n} commits atrás de master: git merge master antes de criar SP")
    out.append(f"git: {ramo} · {len(ficheiros)} alterados")
    out += [f"  {l}" for l in ficheiros[:MAX_FILES]]
    if len(ficheiros) > MAX_FILES:
        out.append(f"  … +{len(ficheiros) - MAX_FILES}")
    return "\n".join(out[:MAX_LINES])


def _uma_linha(texto):
    """Texto vindo de um painel numa só linha, sem caracteres de controlo (não inventa linhas nem mexe no terminal)."""
    return " ".join("".join(c if c.isprintable() else " " for c in str(texto)).split())


def listar(root=None, em_json=False, todas=False):
    """Filas e SPs pelo nome, com as vagas livres do teto global. O pane nunca sai: o utilizador vê o slug.

    Árvores já terminadas (todos os SPs em done/falhou) ficam de fora, a não ser com `todas`."""
    filas = sp_painel_estado.filas(root)
    if not todas:
        filas = [f for f in filas if f.get("erro") or not f["sps"]
                 or any(sp["estado"] not in sp_painel_estado.FINAIS for sp in f["sps"])]
    livres, teto = sp_painel_estado.vagas_livres(root), sp_painel_estado.MAX_PARALELO
    if em_json:
        limpas = [{**f, "sps": [{k: v for k, v in sp.items() if k != "pane"} for sp in f["sps"]]} for f in filas]
        return json.dumps({"vagas_livres": livres, "max": teto, "filas": limpas}, ensure_ascii=False, indent=1)
    if not filas:
        return f"sem filas · vagas livres {livres}/{teto}"
    out = [f"vagas livres {livres}/{teto}"]
    for f in filas:
        out.append(f"{f['fila']} · {f.get('modo') or '-'} · {len(f['sps'])} SPs" + (f" · {f['erro']}" if f.get("erro") else ""))
        for sp in f["sps"]:
            partes = [sp["slug"], sp["estado"]] + [_uma_linha(sp[k]) for k in ("modelo", "msg") if sp.get(k)]
            out.append("  " + " · ".join(partes))
    return "\n".join(out)


def main(argv=None):
    for fluxo in (sys.stdout, sys.stderr):  # stderr também: as recusas («transição inválida») têm acentos
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Estado de um SP numa só leitura; com um estado, grava-o na fila de painéis")
    ap.add_argument("sp", nargs="?", help="slug ou caminho .md")
    ap.add_argument("novo", nargs="?", metavar="estado", help="estado a gravar: " + ", ".join(sp_painel_estado.ESTADOS))
    ap.add_argument("--project")
    ap.add_argument("--msg", help="texto que acompanha o estado (pergunta, motivo do bloqueio)")
    ap.add_argument("--fila", help="fila-id, quando o slug está em mais de uma fila")
    ap.add_argument("--root", help=f"pasta do estado das filas (por defeito ${sp_painel_estado.ENV_ROOT} ou ~/.claude/sp-fila)")
    ap.add_argument("--listar", action="store_true", help="todas as filas e SPs pelo nome")
    ap.add_argument("--json", action="store_true", help="com --listar: saída em JSON")
    ap.add_argument("--todas", action="store_true", help="com --listar: inclui as filas já terminadas")
    ap.add_argument("--migrar", action="store_true", help="converter o sp-fila-estado.json antigo numa fila")
    ap.add_argument("--antigo", help="com --migrar: caminho do estado antigo")
    args = ap.parse_args(argv)
    if args.listar or args.migrar or args.novo is not None:
        try:
            if args.listar:
                print(listar(args.root, args.json, args.todas))
            elif args.migrar:
                fid = sp_painel_estado.migrar_antigo(args.antigo, root=args.root)
                print(f"migrado para a fila {fid}" if fid else "sem estado antigo: nada a migrar")
            else:
                sp = sp_painel_estado.transitar(args.sp, args.novo, msg=args.msg, fila=args.fila, root=args.root)
                print(f"{sp['slug']} · {sp['estado']} · fila {sp['fila']}")
        except (sp_painel_estado.ErroEstado, TimeoutError) as e:
            print(f"sp-estado: {e}", file=sys.stderr)
            return 1
        return 0
    if args.sp is None:
        ap.error("falta o slug (ou --listar / --migrar)")
    out = estado(args.sp, project=args.project)
    print(out)
    return 1 if out.startswith("SP não encontrado") else 0


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-estado", main))
