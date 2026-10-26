"""Testes de scripts/sp-metricas.py e da ligação ao sp-move done (e2e em diretório temporário)."""
import importlib.util
import sys
from pathlib import Path

_here = Path(__file__).parent
for name, file in (("sp_metricas", "sp-metricas.py"), ("sp_move", "sp-move.py")):
    _spec = importlib.util.spec_from_file_location(name, _here / file)
    mod = importlib.util.module_from_spec(_spec)
    sys.modules[name] = mod
    _spec.loader.exec_module(mod)
sp_metricas, sp_move = sys.modules["sp_metricas"], sys.modules["sp_move"]


def make_sp(root, slug, extra=""):
    path = root / "atlas/sp/Doing" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    head = (f"---\nstatus: Doing\ncreated: 2026-10-01T10:00:00Z\nupdated: 2026-10-01T10:00:00Z\n"
            f"slug: {slug}\nproject: atlas\n{extra}---\n")
    path.write_text(head + "# corpo\n- reflect: sem patch\n- reflect: patch x\n", encoding="utf-8")
    return path


def test_linha_tem_horas_custo_reflects_e_gates(tmp_path):
    sp = make_sp(tmp_path, "abc", "gates_tentativas: 1\n")
    sp.write_text(sp.read_text(encoding="utf-8").replace("updated: 2026-10-01T10:00:00Z", "updated: 2026-10-01T12:30:00Z"),
                  encoding="utf-8")
    row = sp_metricas.linha(sp, {"abc": 1.5})
    assert row == "| 2026-10-01 | atlas | abc | 2.5 | 1.50 | 2 | sim |\n"


def test_sp_move_done_acrescenta_linha_uma_so_vez(tmp_path, monkeypatch):
    (tmp_path / "knowledge/infra/reports").mkdir(parents=True)
    make_sp(tmp_path, "abc")
    monkeypatch.setattr(sp_metricas, "custo_por_slug", lambda: {"abc": 0.25})
    msg = sp_move.move(tmp_path, "abc", "done")
    assert "(+métricas)" in msg
    out = (tmp_path / sp_metricas.REL).read_text(encoding="utf-8")
    assert out.startswith("# Métricas por SP")
    assert out.count("| abc |") == 1 and "| 0.25 |" in out


def test_sem_pasta_de_relatorios_e_noop(tmp_path):
    sp = make_sp(tmp_path, "abc")
    assert sp_metricas.registar(tmp_path, sp, custos={}) is None
