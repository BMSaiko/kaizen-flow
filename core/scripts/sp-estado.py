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
from pathlib import Path as _P
import sys as _s
_s.path.insert(0, str(_P(__file__).resolve().parent))
from painel_backend import run_hidden  # noqa: E402
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
        r = kf_git.run(HERE.parent, *a, run=run_hidden)
        return r.stdout.splitlines()
    return run("rev-parse", "--abbrev-ref", "HEAD")[:1] + run("status", "--short")


def estado(ref, root=None, project=None, git_lines=None, atras=None):
    sp_list = kaizen_engine.load("sp-list")
    sp_gates = kaizen_engine.load("sp-gates")
    root = Path(root) if root else sp_list.default_root()
    sps = sp_list.collect(root, include_done=True)
    p = Path(ref)
    por_caminho = [sp for sp in sps if p.suffix == ".md" and sp.path.resolve() == p.resolve()]
    achados = por_caminho or sp_list.encontrar(sps, ref, project)
    if len(achados) > 1:
        return f"SP ambíguo: {ref} ({', '.join(f'{s.slug} [{s.project}]' for s in achados)}); usar o slug completo ou --project"
    alvo = achados[0] if achados else None
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


def interrompidos(raiz=None):
    """SPs órfãos (estado em disco sem lock vivo, fora de Done) da worktree `raiz` (cwd), com o comando de retoma (EC-027)."""
    sr = kaizen_engine.load("sp-resume")
    raiz = raiz or "."
    return [{"slug": s, "estado": "interrompido", "proximo": f"kaizen resume {s}"} for s in sr.candidatos(raiz)]


def listar(root=None, em_json=False, todas=False, raiz_sp=None):
    """Filas e SPs pelo nome, com as vagas livres do teto global. O pane nunca sai: o utilizador vê o slug.

    Árvores já terminadas (todos os SPs em done/falhou) ficam de fora, a não ser com `todas`."""
    filas = sp_painel_estado.filas(root)
    if not todas:
        filas = [f for f in filas if f.get("erro") or not f["sps"]
                 or any(sp["estado"] not in sp_painel_estado.FINAIS for sp in f["sps"])]
    orfaos = interrompidos(raiz_sp)
    livres, teto = sp_painel_estado.vagas_livres(root), sp_painel_estado.MAX_PARALELO
    if em_json:
        limpas = [{**f, "sps": [{k: v for k, v in sp.items() if k != "pane"} for sp in f["sps"]]} for f in filas]
        return json.dumps({"vagas_livres": livres, "max": teto, "filas": limpas, "interrompidos": orfaos}, ensure_ascii=False, indent=1)
    if not filas and not orfaos:
        return f"sem filas · vagas livres {livres}/{teto}"
    out = [f"vagas livres {livres}/{teto}"]
    out += [f"{o['slug']} · {o['estado']} · {o['proximo']}" for o in orfaos]
    for f in filas:
        out.append(f"{f['fila']} · {f.get('modo') or '-'} · {len(f['sps'])} SPs" + (f" · {f['erro']}" if f.get("erro") else ""))
        for sp in f["sps"]:
            partes = [sp["slug"], sp["estado"]] + [_uma_linha(sp[k]) for k in ("modelo", "msg") if sp.get(k)]
            if sp.get("motivo") and not (sp.get("msg") and sp["motivo"] in sp["msg"]):
                partes.append(_uma_linha(sp["motivo"]))
            if sp.get("retoma_em"):
                partes.append(f"retoma {sp['retoma_em']}")
            out.append("  " + " · ".join(partes))
    return "\n".join(out)


def _msg_erro(e):
    """Recusa do estado no formato único (kf_erros), com o EC do catálogo."""
    import kf_erros
    if isinstance(e, TimeoutError):
        return kf_erros.erro("EC-042", f"sp-estado: {e}", "outro processo tem o lock do estado das filas",
                             "nada escrito", "repetir daqui a uns segundos")
    if isinstance(e, sp_painel_estado.SemVaga):
        return kf_erros.erro("EC-033", f"sp-estado: {e}", "o teto global de painéis ativos está atingido",
                             "o SP fica no estado em que estava", "esperar que um painel acabe; a fila reaproveita a vaga")
    if sp_painel_estado.ILEGIVEL in str(e):
        return kf_erros.erro("EC-047", f"sp-estado: {e}", "o JSON do estado do painel está corrompido",
                             "ficheiro intacto (nada adivinhado)", "`sp-estado.py --listar` e, se preciso, `sp-fila.py --parar`")
    return kf_erros.erro("EC-067", f"sp-estado: {e}", "pedido inválido ao estado da fila", "nada escrito",
                         "`sp-estado.py --listar` mostra slugs e estados válidos")


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
            print(_msg_erro(e), file=sys.stderr)
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
