#!/usr/bin/env python3
"""Regista uma linha por SP fechado em knowledge/infra/reports/sp-metricas.md.

Colunas: data | projeto | slug | horas (created→fecho) | custo USD | reflects | gates à 1ª.
Custo: soma das sessões `/michi <SP>` do claude-usage (0.00 se não houver transcripts).
Reflects: linhas «reflect» do SP. Gates à 1ª: `gates_tentativas: 1` no frontmatter (senão n/d).
Chamado por sp-move.py ao fechar; sem a pasta de relatórios é no-op.

Uso: python -I scripts/sp-metricas.py <ficheiro-sp-em-Done>
     python -I scripts/sp-metricas.py --reflect <ficheiro-sp|slug>  (custo do SP, mediana dos anteriores, aviso a 2x)
rc: 0 ok, 2 erro de uso
"""
import importlib.util
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
import sp_indice  # noqa: E402

REL = Path("knowledge/infra/reports/sp-metricas.md")
HEADER = (
    "# Métricas por SP\n\n"
    "| data | projeto | slug | horas | custo USD | reflects | gates à 1ª |\n"
    "|---|---|---|---|---|---|---|\n"
)


def custo_por_slug(usage_root=None):
    """{slug: custo USD} a partir do claude-usage (vazio se indisponível)."""
    path = Path(__file__).with_name("claude-usage.py")
    if not path.is_file():
        return {}
    spec = importlib.util.spec_from_file_location("claude_usage", path)
    cu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cu)
    root = usage_root or str(Path.home() / ".claude" / "projects")
    out = defaultdict(float)
    for _ts, sid, model, t in cu.load(root):
        slug = cu.MICHI.get(sid)
        if slug:
            out[slug] += cu.cost(model, t)
    return out


def _parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def linha(sp_path, custos, project=None, now=None):
    text = Path(sp_path).read_text(encoding="utf-8")
    fm = sp_indice.frontmatter(sp_path)
    slug = fm.get("slug") or re.sub(r"-\d{4}-\d{2}-\d{2}$", "", Path(sp_path).stem)
    fim = _parse(fm.get("updated")) or now or datetime.now(timezone.utc)
    ini = _parse(str(fm.get("created", "")))
    if ini and ini.tzinfo is None:
        ini = ini.replace(tzinfo=timezone.utc)
    horas = f"{(fim - ini).total_seconds() / 3600:.1f}" if ini else "n/d"
    reflects = len(re.findall(r"(?im)^\s*[-*|].*\breflect\b", text))
    gates = "sim" if str(fm.get("gates_tentativas", "")) == "1" else "n/d"
    proj = project or fm.get("project", "?")
    return f"| {fim:%Y-%m-%d} | {proj} | {slug} | {horas} | {custos.get(slug, 0.0):.2f} | {reflects} | {gates} |\n"


def registar(root, sp_path, project=None, custos=None):
    """Acrescenta a linha do SP no 1º ancestral com knowledge/infra/reports (root fica por compatibilidade); devolve o caminho do ficheiro ou None se a pasta de relatórios não existe."""
    base = next((b for b in (Path(sp_path).resolve(), *Path(sp_path).resolve().parents) if (b / REL).parent.is_dir()), None)
    if base is None:
        return None
    dest = base / REL
    row = linha(sp_path, custo_por_slug() if custos is None else custos, project)
    existing = dest.read_text(encoding="utf-8") if dest.exists() else HEADER
    if f"| {row.split('|')[3].strip()} |" in existing:
        return dest
    dest.write_text(existing + row, encoding="utf-8")
    return dest


def custos_anteriores(table_text, slug):
    """Custos USD (>0) das linhas registadas, exceto a do próprio slug."""
    out = []
    for row in table_text.splitlines():
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) < 7 or cells[2] == slug:
            continue
        try:
            v = float(cells[4])
        except ValueError:
            continue
        if v > 0:
            out.append(v)
    return out


def reflect(sp_arg, custos, table_text):
    """Linhas para o /reflect: custo do SP, mediana dos anteriores e aviso se >= 2x a mediana."""
    p = Path(sp_arg)
    if p.is_file():
        fm = sp_indice.frontmatter(p)
        slug = fm.get("slug") or re.sub(r"-\d{4}-\d{2}-\d{2}$", "", p.stem)
    else:
        slug = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", p.stem)
    cost = custos.get(slug)
    prev = sorted(custos_anteriores(table_text, slug))
    mediana = statistics.median(prev) if prev else None
    out = [f"custo {slug}: " + (f"{cost:.2f} USD" if cost else "-") + " (- = sem transcripts, não é zero)",
           "mediana dos anteriores: " + (f"{mediana:.2f} USD (n={len(prev)})" if mediana is not None else "-")]
    if cost and mediana and cost >= 2 * mediana:
        out.append(f"AVISO: custo {cost:.2f} >= 2x a mediana {mediana:.2f}; registar como fricção")
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(argv) == 2 and argv[0] == "--reflect":
        root = Path(__file__).resolve().parent.parent
        table = root / REL
        text = table.read_text(encoding="utf-8") if table.exists() else ""
        print("\n".join(reflect(argv[1], custo_por_slug(), text)))
        return 0
    if len(argv) != 1:
        print(__doc__)
        return 2
    root = Path(__file__).resolve().parent.parent
    dest = registar(root, argv[0])
    print(f"métricas: {dest}" if dest else "métricas: sem pasta de relatórios, ignorado")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-metricas", main))
