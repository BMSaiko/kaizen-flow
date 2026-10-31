#!/usr/bin/env python3
"""Regista uma linha por SP fechado em knowledge/infra/reports/sp-metricas.md.

Colunas: data | projeto | slug | horas (created→fecho) | custo USD | reflects | gates à 1ª.
Custo: soma das sessões `/michi <SP>` do claude-usage (0.00 se não houver transcripts).
Reflects: linhas «reflect» do SP. Gates à 1ª: `gates_tentativas: 1` no frontmatter (senão n/d).
Chamado por sp-move.py ao fechar; sem a pasta de relatórios é no-op.

Uso: python -I scripts/sp-metricas.py <ficheiro-sp-em-Done>
"""
import importlib.util
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

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
    fm = kaizen_engine.parse_frontmatter(text)
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


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    root = Path(__file__).resolve().parent.parent
    dest = registar(root, argv[0])
    print(f"métricas: {dest}" if dest else "métricas: sem pasta de relatórios, ignorado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
