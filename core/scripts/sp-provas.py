#!/usr/bin/env python3
"""Pacote de provas de um SP: `sp/proofs/<slug>/provas.json` + imagens (SVG gerado por código, anexos PNG/SVG).

Uso:
  python -I scripts/sp-provas.py <slug> [--project P] [--root R] [--base B] [--cwd DIR]
  python -I scripts/sp-provas.py <slug> --imagem F --tipo antes|depois|terminal|diagrama --legenda L
  python -I scripts/sp-provas.py --validar <provas.json> [--ui]
Regerar preserva as imagens manuais (antes/depois). SP com `ui: sim` exige uma imagem `depois`;
sem UI exige diagrama ou terminal. Stdlib apenas; pacote <= 2 MB; recusa segredos e caminhos proibidos.
rc: 0 ok, 1 pacote inválido ou erro, 2 erro de uso
"""
import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
import sp_leitura  # noqa: E402

sp_list = kaizen_engine.load("sp-list")

CAMPOS = ("objetivo", "feito", "ficheiros", "gates", "criterios", "decisoes_auto", "experimentar", "reverter", "pr", "imagens")
TIPOS = ("antes", "depois", "diagrama", "terminal")
MAX_BYTES = 2 * 1024 * 1024
DATA_MIN = "2026-11-13"
PROIBIDOS = (".env", ".key", ".pem", ".p12", ".pfx", "id_rsa", ".kdbx", "secrets.", ".secrets")
SEGREDO = re.compile(r"(ghp_\w{10,}|github_pat_\w+|sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{12,}|xox[abprs]-[\w-]+|"
                     r"eyJ[\w-]{15,}\.[\w-]{10,}\.[\w-]+|Bearer\s+[\w.-]{16,}|(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S{6,})", re.I)
PERIGOSO = re.compile(r"git\s+(reset|push\s+.*(--force|-f\b))|--force|--hard", re.I)


class ProvasError(Exception):
    pass


def limpar(texto):
    """Corta linhas com padrões de token."""
    return "\n".join("[linha cortada: possível segredo]" if SEGREDO.search(l) else l for l in str(texto).splitlines())


def caminho_proibido(p):
    nome = Path(str(p)).name.lower()
    return any(s in nome for s in PROIBIDOS)


def pasta_do_pacote(sp):
    return sp.path.parent.parent / "proofs" / sp.slug


def secao(texto, *titulos):
    for t in titulos:
        c = sp_leitura.seccao(texto, t, maiusculas=False).strip()
        if c:
            return c
    return ""


def linhas_uteis(texto, n):
    out = [re.sub(r"^\s*[-*\d.]+\s+", "", l).strip() for l in texto.splitlines() if l.strip() and not l.startswith("#")]
    return out[:n]


def criterios(texto):
    """(cumpridos, por_cumprir): critérios numerados da secção 4; `[x]` ou `✓` = cumprido."""
    cumpridos, pendentes = [], []
    for l in secao(texto, "4. Success", "Success").splitlines():
        m = re.match(r"^\s*(?:\d+\.|-)\s+(.*)$", l)
        if not m:
            continue
        t = m.group(1).strip()
        if re.match(r"^\[[xX]\]|^✓", t):
            cumpridos.append(re.sub(r"^(\[[xX]\]|✓)\s*", "", t))
        else:
            pendentes.append(re.sub(r"^\[ \]\s*", "", t))
    return cumpridos, pendentes


def git(cwd, *args):
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip() if r.returncode == 0 else ""


def base_git(cwd, base=None):
    if base:
        return base
    for b in ("master", "main"):
        mb = git(cwd, "merge-base", "HEAD", b)
        if mb:
            return mb
    return ""


def ficheiros_alterados(cwd, base=None):
    """Lista `{path, estado}` (N novo, M alterado, D apagado) contra a base; inclui os por commitar."""
    b = base_git(cwd, base)
    out = {}
    for l in (git(cwd, "diff", "--name-status", b) if b else git(cwd, "diff", "--name-status", "HEAD")).splitlines():
        partes = l.split("\t")
        if len(partes) >= 2:
            est = {"A": "N", "D": "D"}.get(partes[0][0], "M")
            out[partes[-1]] = est
    for p in git(cwd, "ls-files", "--others", "--exclude-standard").splitlines():
        out[p] = "N"
    return [{"path": p, "estado": e} for p, e in sorted(out.items())
            if not Path(p).name.startswith("COMMIT_") and not caminho_proibido(p) and "/proofs/" not in "/" + p]


def stat_texto(cwd, base=None):
    b = base_git(cwd, base)
    return limpar(git(cwd, "diff", "--stat", b) if b else "")


def esc(s):
    return html.escape(str(s), quote=True)


def diagrama_svg(ficheiros):
    """SVG escrito à mão: ficheiros agrupados por pasta (novos/alterados/apagados) com barras proporcionais."""
    grupos = {}
    for f in ficheiros:
        p = f["path"].replace("\\", "/")
        pasta = p.rsplit("/", 1)[0] if "/" in p else "."
        g = grupos.setdefault(pasta, {"N": 0, "M": 0, "D": 0})
        g[f.get("estado", "M")] = g.get(f.get("estado", "M"), 0) + 1
    cores = {"N": "#2da44e", "M": "#bf8700", "D": "#cf222e"}
    nomes = {"N": "novos", "M": "alterados", "D": "apagados"}
    linhas = sorted(grupos.items())
    maxn = max([sum(g.values()) for _, g in linhas] or [1])
    alt = 70 + 28 * max(len(linhas), 1)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="760" height="{alt}" viewBox="0 0 760 {alt}" font-family="Segoe UI,Arial,sans-serif" font-size="13">',
         f'<rect width="760" height="{alt}" fill="#ffffff"/>',
         f'<text x="16" y="24" font-size="15" font-weight="bold" fill="#1f2328">O que mudou ({len(ficheiros)} ficheiros)</text>']
    x = 16
    for k in "NMD":
        o.append(f'<rect x="{x}" y="36" width="12" height="12" fill="{cores[k]}"/><text x="{x + 18}" y="47" fill="#1f2328">{nomes[k]}</text>')
        x += 110
    if not linhas:
        o.append('<text x="16" y="82" fill="#656d76">sem alterações</text>')
    for i, (pasta, g) in enumerate(linhas):
        y = 62 + 28 * i
        o.append(f'<text x="16" y="{y + 14}" fill="#1f2328">{esc(pasta[-42:])}</text>')
        bx = 300
        for k in "NMD":
            w = round(g.get(k, 0) / maxn * 380)
            if w:
                o.append(f'<rect x="{bx}" y="{y}" width="{w}" height="18" fill="{cores[k]}"/>')
                o.append(f'<text x="{bx + 4}" y="{y + 13}" fill="#ffffff" font-size="11">{g[k]}</text>')
                bx += w
    o.append("</svg>")
    return "\n".join(o)


def gates_svg(gates):
    """SVG com o output dos gates (comando, rc, últimas linhas), como imagem de terminal."""
    linhas = []
    for g in gates:
        linhas.append((f"$ {g['cmd']}", "cmd"))
        linhas += [(l[:96], "out") for l in str(g.get("tail", "")).splitlines()[-6:]]
        linhas.append((f"rc={g['rc']}", "ok" if g["rc"] == 0 else "mau"))
    if not linhas:
        linhas = [("sem gates declarados", "out")]
    alt = 20 + 18 * len(linhas)
    cor = {"cmd": "#79c0ff", "out": "#c9d1d9", "ok": "#3fb950", "mau": "#f85149"}
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="820" height="{alt}" viewBox="0 0 820 {alt}" font-family="Consolas,monospace" font-size="13">',
         f'<rect width="820" height="{alt}" fill="#0d1117"/>']
    for i, (t, k) in enumerate(linhas):
        o.append(f'<text x="12" y="{26 + 18 * i}" fill="{cor[k]}" xml:space="preserve">{esc(t)}</text>')
    o.append("</svg>")
    return "\n".join(o)


def validar(d, ui=False, pasta=None):
    """Lista de problemas (vazia = válido)."""
    p = [f"campo em falta: {c}" for c in CAMPOS if c not in d]
    if p:
        return p
    if len(d["feito"]) > 5:
        p.append("feito: máximo 5 linhas")
    if len(d["experimentar"]) > 3:
        p.append("experimentar: máximo 3 linhas")
    if not isinstance(d["criterios"], dict) or not {"cumpridos", "por_cumprir"} <= set(d["criterios"]):
        p.append("criterios: precisa de cumpridos e por_cumprir")
    for r in d["reverter"] if isinstance(d["reverter"], list) else [d["reverter"]]:
        if PERIGOSO.search(str(r)):
            p.append(f"reverter: comando perigoso (reset/force): {r}")
    tipos = []
    for im in d["imagens"]:
        if not isinstance(im, dict) or not {"ficheiro", "legenda", "tipo"} <= set(im):
            p.append("imagens: cada item precisa de ficheiro, legenda e tipo")
            continue
        if im["tipo"] not in TIPOS:
            p.append(f"imagens: tipo inválido {im['tipo']!r}")
        if caminho_proibido(im["ficheiro"]):
            p.append(f"imagens: caminho proibido {im['ficheiro']}")
        tipos.append(im["tipo"])
        if pasta is not None and not (Path(pasta) / im["ficheiro"]).is_file():
            p.append(f"imagens: ficheiro em falta {im['ficheiro']}")
    if ui and "depois" not in tipos:
        p.append("SP com ui: sim exige uma imagem `depois` (app a correr)")
    if not ui and not ({"diagrama", "terminal"} & set(tipos)):
        p.append("SP sem UI exige pelo menos uma imagem diagrama ou terminal")
    if SEGREDO.search(json.dumps(d, ensure_ascii=False)):
        p.append("possível segredo no pacote")
    if pasta is not None:
        total = sum(f.stat().st_size for f in Path(pasta).rglob("*") if f.is_file())
        if total > MAX_BYTES:
            p.append(f"pacote com {total} bytes (máximo {MAX_BYTES})")
    return p


def montar(sp, cwd=None, base=None, gates_resultados=None, pr="", manuais=None):
    """Dicionário do pacote para o SP `sp` (objeto de sp_list). `gates_resultados` evita correr os gates outra vez."""
    texto = sp.path.read_text(encoding="utf-8").replace("\r\n", "\n")
    cwd = cwd or sp.path.parent
    fich = ficheiros_alterados(cwd, base)
    cump, pend = criterios(texto)
    prova = secao(texto, "Prova de done")
    feito = linhas_uteis(prova, 5) or linhas_uteis(secao(texto, "3. Objective", "Objective"), 5)
    exp = linhas_uteis(secao(texto, "Como experimentar", "Experimentar"), 3)
    if not exp:
        gs = re.findall(r"cmd:\s*(.+)", sp_leitura.bloco(texto))
        exp = [limpar(gs[0].strip())] if gs else ["ver `## Prova de done` no SP"]
    commits = git(cwd, "log", "--format=%h", f"{base_git(cwd, base)}..HEAD").split() if base_git(cwd, base) else []
    rev = [f"git revert --no-edit {' '.join(commits)}"] if commits else ["sem commits ainda: descartar com `git restore` os ficheiros listados"]
    gates = [{"cmd": r["cmd"], "rc": r["rc"], "tail": limpar(r.get("tail", ""))} for r in (gates_resultados or [])]
    obj = linhas_uteis(secao(texto, "3. Objective", "Objective"), 1)
    return {"slug": sp.slug, "objetivo": limpar(obj[0]) if obj else sp.slug,
            "feito": [limpar(l) for l in feito], "ficheiros": fich, "diff_stat": stat_texto(cwd, base),
            "gates": gates, "criterios": {"cumpridos": cump, "por_cumprir": pend},
            "decisoes_auto": [limpar(l) for l in linhas_uteis(secao(texto, "Decisões modo auto"), 20)],
            "experimentar": exp, "reverter": rev, "pr": pr, "imagens": list(manuais or [])}


def gravar(sp, cwd=None, base=None, gates_resultados=None, pr=""):
    """Escreve o pacote (regerando diagrama e gates; preserva imagens manuais). Devolve (pasta, dict)."""
    pasta = pasta_do_pacote(sp)
    pasta.mkdir(parents=True, exist_ok=True)
    ant = pasta / "provas.json"
    manuais = []
    if ant.is_file():
        try:
            manuais = [i for i in json.loads(ant.read_text(encoding="utf-8")).get("imagens", []) if i.get("tipo") in ("antes", "depois")]
        except ValueError:
            manuais = []
    d = montar(sp, cwd, base, gates_resultados, pr, manuais)
    (pasta / "diagrama.svg").write_text(diagrama_svg(d["ficheiros"]), encoding="utf-8")
    (pasta / "gates.svg").write_text(gates_svg(d["gates"]), encoding="utf-8")
    d["imagens"] += [{"ficheiro": "diagrama.svg", "legenda": "O que mudou, por pasta", "tipo": "diagrama"},
                     {"ficheiro": "gates.svg", "legenda": "Output dos gates", "tipo": "terminal"}]
    (pasta / "provas.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pasta, d


def anexar(sp, imagem, tipo, legenda):
    """Copia uma imagem manual (PNG/SVG) para o pacote e regista-a em provas.json."""
    src = Path(imagem)
    if caminho_proibido(src):
        raise ProvasError(f"caminho proibido: {src.name}")
    if src.suffix.lower() not in (".png", ".svg") or not src.is_file():
        raise ProvasError("imagem tem de existir e ser PNG ou SVG")
    if tipo not in TIPOS:
        raise ProvasError(f"tipo inválido: {tipo}")
    pasta = pasta_do_pacote(sp)
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f"{tipo}-{src.name}"
    (pasta / nome).write_bytes(src.read_bytes())
    f = pasta / "provas.json"
    d = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {"imagens": []}
    d["imagens"] = [i for i in d.get("imagens", []) if i.get("ficheiro") != nome] + [{"ficheiro": nome, "legenda": legenda, "tipo": tipo}]
    f.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pasta / nome


def exige_pacote(sp):
    """True se o SP é de 2026-11-13 em diante (portão do fecho)."""
    return (sp_leitura.frontmatter(sp.path.read_text(encoding="utf-8")).get("date", "0")).split()[0] >= DATA_MIN


def com_ui(sp):
    return sp_leitura.frontmatter(sp.path.read_text(encoding="utf-8")).get("ui", "").split()[:1] == ["sim"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--project")
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT))
    ap.add_argument("--base")
    ap.add_argument("--cwd")
    ap.add_argument("--imagem")
    ap.add_argument("--tipo")
    ap.add_argument("--legenda", default="")
    ap.add_argument("--validar", metavar="PROVAS_JSON")
    ap.add_argument("--ui", action="store_true")
    a = ap.parse_args(argv)
    if a.validar:
        f = Path(a.validar)
        probs = validar(json.loads(f.read_text(encoding="utf-8")), a.ui, f.parent)
        print("\n".join(probs) if probs else "válido")
        return 1 if probs else 0
    if not a.slug:
        ap.error("falta o slug")
    achados = [s for s in sp_list.collect(a.root, include_done=True) if s.slug == a.slug and (not a.project or s.project == a.project)]
    if len(achados) != 1:
        print(f"erro: SP '{a.slug}' não encontrado ou ambíguo (--project)", file=sys.stderr)
        return 2
    sp = achados[0]
    try:
        if a.imagem:
            print(anexar(sp, a.imagem, a.tipo or "depois", a.legenda))
            return 0
        pasta, d = gravar(sp, a.cwd, a.base)
    except ProvasError as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    probs = validar(d, com_ui(sp), pasta)
    print(pasta / "provas.json")
    if probs:
        print("\n".join(probs), file=sys.stderr)
    return 1 if probs else 0


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-provas", main))
