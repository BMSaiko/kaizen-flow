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
