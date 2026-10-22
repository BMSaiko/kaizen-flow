"""Testes de scripts/sp-validate.py (fixtures em ficheiros temporários)."""
import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("sp_validate", Path(__file__).with_name("sp-validate.py"))
sp_validate = importlib.util.module_from_spec(_spec)
sys.modules["sp_validate"] = sp_validate
_spec.loader.exec_module(sp_validate)

SECTIONS = [
    ("1. Role", "És o the agent."),
    ("2. Context", "- Repo: Second Brain."),
    ("3. Objective (single sentence)", "Fazer uma coisa."),
    ("4. Success criteria (verifiable)", "- [ ] RC 0."),
    ("5. Constraints / invariants", "- Must keep: X."),
    ("6. Seams (public interfaces to test / change)", "- `scripts/x.py`."),
    ("7. Steps (numbered, ordered)", "1. Fazer."),
    ("8. Done-when", "Testes verdes."),
]


def build(status="TODO", drop=None, no_priority=False, empty=None):
    fm = ["---", f"status: {status}", "created: 2026-10-18T00:00:00Z", "updated: 2026-10-18T00:00:00Z",
          "phase: SP", "slug: abc", "date: 2026-10-18", "project: atlas"]
    if not no_priority:
        fm.append("priority: P2")
    fm.append("---")
    body = ["# Super Prompt - abc", ""]
    for title, text in SECTIONS:
        if title.startswith(f"{drop}."):
            continue
        body += [f"## {title}", "" if title.startswith(f"{empty}.") else text, ""]
    return "\n".join(fm + body)


def test_sp_valido_nao_tem_erros():
    assert sp_validate.validate(build(), folder="TODO") == []


def test_sem_seccao_5_nomeia_a_seccao():
    errors = sp_validate.validate(build(drop=5), folder="TODO")
    assert len(errors) == 1 and "5." in errors[0]


def test_sem_priority_nomeia_o_campo():
    errors = sp_validate.validate(build(no_priority=True), folder="TODO")
    assert len(errors) == 1 and "priority" in errors[0]


def test_status_diferente_da_pasta():
    errors = sp_validate.validate(build(status="Doing"), folder="TODO")
    assert len(errors) == 1 and "status" in errors[0] and "TODO" in errors[0]


def test_seccao_vazia():
    errors = sp_validate.validate(build(empty=8), folder="TODO")
    assert len(errors) == 1 and "8." in errors[0] and "vazia" in errors[0]


def test_sem_frontmatter():
    errors = sp_validate.validate("# só corpo\n", folder=None)
    assert any("frontmatter" in e for e in errors)


def test_folder_none_nao_compara_status():
    assert sp_validate.validate(build(status="Doing"), folder=None) == []


def test_cli_rc0_e_rc1_com_lista(tmp_path, capsys):
    ok = tmp_path / "atlas" / "sp" / "TODO" / "ok.md"
    ok.parent.mkdir(parents=True)
    ok.write_text(build(), encoding="utf-8")
    bad = tmp_path / "atlas" / "sp" / "TODO" / "bad.md"
    bad.write_text(build(drop=5, no_priority=True), encoding="utf-8")
    assert sp_validate.main([str(ok)]) == 0
    assert sp_validate.main([str(bad)]) == 1
    err = capsys.readouterr().err
    assert "5." in err and "priority" in err
