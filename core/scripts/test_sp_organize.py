"""Testes de scripts/sp-organize.py (FS em diretório temporário)."""
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("sp_organize", Path(__file__).with_name("sp-organize.py"))
sp_organize = importlib.util.module_from_spec(_spec)
sys.modules["sp_organize"] = sp_organize
_spec.loader.exec_module(sp_organize)


def sp(root, rel, slug="abc", status="TODO", project="atlas", date="2026-10-18"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nstatus: {status}\nphase: SP\nslug: {slug}\ndate: {date}\nproject: {project}\n---\n# corpo\n",
        encoding="utf-8")
    return path


def test_conforme_nao_tem_desvios(tmp_path):
    sp(tmp_path, "atlas/sp/TODO/abc-2026-10-18.md")
    assert sp_organize.plan(tmp_path) == []


def test_status_diferente_da_pasta_corrige_frontmatter(tmp_path):
    path = sp(tmp_path, "atlas/sp/Doing/abc-2026-10-18.md", status="TODO")
    (action,) = sp_organize.plan(tmp_path)
    assert action.target == path and "status" in action.reason
    sp_organize.apply(action)
    assert "status: Doing" in path.read_text(encoding="utf-8")


def test_nome_com_data_duplicada_e_renomeado(tmp_path):
    old = sp(tmp_path, "atlas/sp/TODO/abc-2026-10-18-2026-10-18.md")
    (action,) = sp_organize.plan(tmp_path)
    sp_organize.apply(action)
    assert not old.exists()
    assert (tmp_path / "atlas/sp/TODO/abc-2026-10-18.md").is_file()


def test_sp_na_raiz_sem_projeto_vai_para_o_projeto_do_frontmatter(tmp_path):
    (tmp_path / "atlas/sp/TODO").mkdir(parents=True)
    sp(tmp_path, "sp/Done/abc-2026-10-18.md", status="Done")
    (action,) = sp_organize.plan(tmp_path)
    sp_organize.apply(action)
    assert (tmp_path / "atlas/sp/Done/abc-2026-10-18.md").is_file()


def test_project_diferente_da_pasta_corrige_frontmatter(tmp_path):
    path = sp(tmp_path, "atlas/sp/TODO/abc-2026-10-18.md", project="outro")
    (action,) = sp_organize.plan(tmp_path)
    sp_organize.apply(action)
    assert "project: atlas" in path.read_text(encoding="utf-8")


def test_sp_diretamente_em_sp_move_para_pasta_do_estado(tmp_path):
    sp(tmp_path, "atlas/sp/abc-2026-10-18.md", status="TODO")
    (action,) = sp_organize.plan(tmp_path)
    sp_organize.apply(action)
    assert (tmp_path / "atlas/sp/TODO/abc-2026-10-18.md").is_file()


def test_colisao_nao_sobrescreve(tmp_path):
    dup = sp(tmp_path, "atlas/sp/TODO/abc-2026-10-18-2026-10-18.md")
    sp(tmp_path, "atlas/sp/TODO/abc-2026-10-18.md")
    (action,) = sp_organize.plan(tmp_path)
    assert action.blocked
    sp_organize.apply(action)
    assert dup.is_file()


def test_exclusoes_nao_sao_tocadas(tmp_path):
    sp(tmp_path, "atlas/sp/arquivo/x-2026-09-06.md", slug="y")
    sp(tmp_path, "pi/sp/TODO/_sessions/s.md", slug="z")
    sp(tmp_path, "atlas/sp/TODO/abc-2026-10-18-DP.md")
    sp(tmp_path, "atlas/sp/TODO/abc-2026-10-18-REPORT.md")
    (tmp_path / "plans/sp").mkdir(parents=True)
    (tmp_path / "plans/sp/MOC.md").write_text("# moc", encoding="utf-8")
    assert sp_organize.plan(tmp_path) == []


def test_filtro_por_projeto(tmp_path):
    sp(tmp_path, "atlas/sp/Doing/abc-2026-10-18.md", status="TODO")
    sp(tmp_path, "hermes/sp/Doing/abc-2026-10-18.md", status="TODO", project="hermes")
    assert len(sp_organize.plan(tmp_path, project="hermes")) == 1


def test_idempotente_e_dry_run_por_defeito(tmp_path, capsys):
    path = sp(tmp_path, "atlas/sp/Doing/abc-2026-10-18.md", status="TODO")
    assert sp_organize.main(["--root", str(tmp_path)]) == 1
    assert "status: TODO" in path.read_text(encoding="utf-8")
    assert sp_organize.main(["--root", str(tmp_path), "--apply"]) == 0
    assert sp_organize.main(["--root", str(tmp_path)]) == 0
    assert "nada a fazer" in capsys.readouterr().out
