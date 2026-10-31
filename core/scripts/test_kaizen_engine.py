"""Motor único do SP: parse/rewrite do frontmatter e carregamento dos scripts com hífen."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine as ke  # noqa: E402

RAW = "---\nstatus: TODO\nupdated: 2026-01-01T00:00:00Z\nslug: x  # c\ndepends_on: [a, b]\n---\ncorpo\nstatus: fica\n"


def test_parse_frontmatter_strips_comments_and_quotes():
    fm = ke.parse_frontmatter(RAW)
    assert fm["slug"] == "x" and fm["status"] == "TODO"
    assert ke.parse_list(fm["depends_on"]) == ["a", "b"]


def test_parse_frontmatter_without_block():
    assert ke.parse_frontmatter("sem fm") == {}


def test_frontmatter_lines_stops_at_close():
    assert ke.frontmatter_lines(RAW)[-1] == "depends_on: [a, b]"
    assert ke.frontmatter_lines("x") == []


def test_rewrite_fields_only_touches_frontmatter_and_keeps_eol():
    out = ke.rewrite_fields(RAW.replace("\n", "\r\n").encode(), {"status": "Done", "updated": "T"}, ValueError)
    text = out.decode()
    assert "status: Done\r\nupdated: T\r\n" in text
    assert text.endswith("status: fica\r\n")


@pytest.mark.parametrize("raw,msg", [
    ("sem fm\n", "SP sem frontmatter"),
    ("---\nstatus: a\n", "frontmatter sem fecho"),
    ("---\nstatus: a\n---\n", "frontmatter sem status/updated"),
])
def test_rewrite_fields_errors(raw, msg):
    with pytest.raises(ValueError, match=msg):
        ke.rewrite_fields(raw.encode(), {"status": "x", "updated": "y"}, ValueError)


def test_load_sibling_script_is_cached():
    mod = ke.load("sp-list")
    assert mod is ke.load("sp-list") and hasattr(mod, "collect")


def test_precisa_perguntar_acoes_seguem_o_frontmatter():
    assert ke.precisa_perguntar({"commit": "auto"}, "commit") is False
    assert ke.precisa_perguntar({"commit": "pergunta"}, "commit") is True
    assert ke.precisa_perguntar({}, "push") is True
    assert ke.precisa_perguntar({"pr": "nunca"}, "pr") is True


def test_precisa_perguntar_comando_so_se_na_allowlist():
    fm = {"permitir": "npm test; python -I scripts/x.py"}
    assert ke.precisa_perguntar(fm, "npm test") is False
    assert ke.precisa_perguntar(fm, "  python -I scripts/x.py ") is False
    assert ke.precisa_perguntar(fm, "npm publish") is True
    assert ke.precisa_perguntar({}, "npm test") is True


def test_precisa_perguntar_irreversivel_pergunta_sempre():
    fm = {"permitir": "git push --force", "push": "auto"}
    assert ke.precisa_perguntar(fm, "git push --force") is True
    assert ke.precisa_perguntar(fm, "git reset --hard") is True


def test_parse_permitir_separa_por_ponto_e_virgula():
    assert ke.parse_permitir("a b; c ;;d") == ["a b", "c", "d"]
    assert ke.parse_permitir(None) == []


def _git(cwd, *args):
    import subprocess
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)


def test_relocate_untracked_renames_and_creates_parent(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("x\r\ny\r\n", encoding="utf-8", newline="")
    dst = tmp_path / "novo" / "dir" / "a.md"
    ke.relocate(src, dst)
    assert not src.exists() and dst.read_bytes() == b"x\r\ny\r\n"


def test_relocate_tracked_uses_git_mv(tmp_path):
    _git(tmp_path, "init", "-q")
    src = tmp_path / "TODO" / "a.md"
    src.parent.mkdir()
    src.write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "TODO/a.md")
    ke.relocate(src, tmp_path / "Doing" / "a.md")
    status = _git(tmp_path, "status", "--porcelain").stdout
    assert status.strip() == "A  Doing/a.md"  # git mv deixa o destino em stage; rename simples dava «??»
