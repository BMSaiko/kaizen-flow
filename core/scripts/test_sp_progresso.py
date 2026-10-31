"""Testes de sp_progresso.py (registo de `## Progresso` no SP e verificação do delta)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_progresso  # noqa: E402
from handoff_pane import HandoffError  # noqa: E402

SP = "---\nstatus: Doing\nupdated: 2020-01-01T00:00:00Z\nslug: x\n---\n# SP\n\n## Outra\n\ntexto\n"


def test_check_delta_aceita_curto():
    sp_progresso.check_delta("próximo passo: X\n\n\n")


def test_check_delta_recusa_longo():
    with pytest.raises(HandoffError, match="linhas"):
        sp_progresso.check_delta("\n".join(["l"] * (sp_progresso.MAX_BODY_LINES + 1)))


def test_check_delta_recusa_secao_do_sp_copiada():
    with pytest.raises(HandoffError, match="repete"):
        sp_progresso.check_delta("nota\n## 3. Objective\nx")


def test_write_acrescenta_seccao_e_atualiza_updated(tmp_path):
    p = tmp_path / "x.md"
    p.write_bytes(SP.encode())
    sp_progresso.write(p, "fez A", today="2026-10-31")
    t = p.read_bytes().decode()
    assert "## Progresso (sessão 2026-10-31)\n\nfez A\n" in t
    assert "updated: 2020-01-01" not in t


def test_write_substitui_a_secao_do_mesmo_dia_sem_duplicar(tmp_path):
    p = tmp_path / "x.md"
    p.write_bytes(SP.encode())
    sp_progresso.write(p, "primeiro", today="2026-10-31")
    sp_progresso.write(p, "segundo", today="2026-10-31")
    t = p.read_bytes().decode()
    assert t.count("## Progresso (sessão 2026-10-31)") == 1
    assert "segundo" in t and "primeiro" not in t


def test_write_preserva_crlf(tmp_path):
    p = tmp_path / "x.md"
    p.write_bytes(SP.replace("\n", "\r\n").encode())
    sp_progresso.write(p, "a\nb", today="2026-10-31")
    t = p.read_bytes().decode()
    assert "\r\n" in t and "\n" not in t.replace("\r\n", "")


def test_write_recusa_sem_frontmatter_ou_sem_updated(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("# sem fm\n", encoding="utf-8")
    with pytest.raises(HandoffError, match="frontmatter"):
        sp_progresso.write(p, "x")
    p.write_text("---\nstatus: Doing\n---\n", encoding="utf-8")
    with pytest.raises(HandoffError, match="updated"):
        sp_progresso.write(p, "x")


def test_require_doing(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("---\nstatus: TODO\n---\n", encoding="utf-8")
    with pytest.raises(HandoffError, match="Doing"):
        sp_progresso.require_doing(p)
    p.write_text("---\nstatus: Doing\n---\n", encoding="utf-8")
    sp_progresso.require_doing(p)
