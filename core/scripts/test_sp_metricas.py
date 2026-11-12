"""Testes de scripts/sp-metricas.py e da ligação ao sp-move done (e2e em diretório temporário)."""
import sys
from pathlib import Path
from sp_carregar import carregar  # noqa: E402

_here = Path(__file__).parent
for name, file in (("sp_metricas", "sp-metricas.py"), ("sp_move", "sp-move.py")):
    mod = carregar(_here / file, name, fresco=True)
sp_metricas, sp_move = sys.modules["sp_metricas"], sys.modules["sp_move"]


from functools import partial
from conftest import criar_sp

make_sp = partial(criar_sp, rel="atlas/sp/Doing", status="Doing", project="atlas",
                  body="# corpo\n- reflect: sem patch\n- reflect: patch x\n")


def test_linha_tem_horas_custo_reflects_e_gates(tmp_path):
    sp = make_sp(tmp_path, slug="abc", extra="gates_tentativas: 1\n")
    sp.write_text(sp.read_text(encoding="utf-8").replace("updated: 2026-10-01T10:00:00Z", "updated: 2026-10-01T12:30:00Z"),
                  encoding="utf-8")
    row = sp_metricas.linha(sp, {"abc": 1.5})
    assert row == "| 2026-10-01 | atlas | abc | 2.5 | 1.50 | 2 | sim |\n"


def test_sp_move_done_acrescenta_linha_uma_so_vez(tmp_path, monkeypatch):
    (tmp_path / "knowledge/infra/reports").mkdir(parents=True)
    make_sp(tmp_path, slug="abc")
    monkeypatch.setattr(sp_metricas, "custo_por_slug", lambda: {"abc": 0.25})
    msg = sp_move.move(tmp_path, "abc", "done")
    assert "(+métricas)" in msg
    out = (tmp_path / sp_metricas.REL).read_text(encoding="utf-8")
    assert out.startswith("# Métricas por SP")
    assert out.count("| abc |") == 1 and "| 0.25 |" in out


def test_sem_pasta_de_relatorios_e_noop(tmp_path):
    sp = make_sp(tmp_path, slug="abc")
    assert sp_metricas.registar(tmp_path, sp, custos={}) is None


def test_uso_imprime_em_consola_cp1252(tmp_path):
    import os
    import subprocess
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    env.pop("PYTHONUTF8", None)
    script = Path(__file__).resolve().parent / "sp-metricas.py"
    r = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, env=env)
    assert r.returncode == 2, r.stderr
    assert b"UnicodeEncodeError" not in r.stderr


TABELA = "| d | p | a | 1 | 1.00 | 1 | n/d |\n| d | p | b | 1 | 3.00 | 1 | n/d |\n| d | p | c | 1 | 0.00 | 1 | n/d |\n"


def test_reflect_mostra_custo_mediana_sem_aviso(tmp_path):
    out = sp_metricas.reflect("novo", {"novo": 2.0}, TABELA)
    assert out[0].startswith("custo novo: 2.00 USD")
    assert "mediana dos anteriores: 2.00 USD (n=2)" in out[1]
    assert len(out) == 2


def test_reflect_avisa_a_2x_e_custo_sem_transcripts_e_traco(tmp_path):
    assert any(l.startswith("AVISO") for l in sp_metricas.reflect("novo", {"novo": 4.0}, TABELA))
    out = sp_metricas.reflect("novo", {}, TABELA)
    assert out[0].startswith("custo novo: -") and len(out) == 2
