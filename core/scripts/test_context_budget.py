"""Testes de scripts/context-budget.py (ficheiros temporários)."""
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("context_budget", Path(__file__).with_name("context-budget.py"))
context_budget = importlib.util.module_from_spec(_spec)
sys.modules["context_budget"] = context_budget
_spec.loader.exec_module(context_budget)


def test_skill_descriptions_conta_nome_e_descricao(tmp_path):
    skill = tmp_path / "abc" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text('---\nname: abc\ndescription: "dez bytes"\n---\ncorpo longo ignorado\n', encoding="utf-8")
    assert context_budget.skill_descriptions(tmp_path) == len("abc") + len('"dez bytes"')


def test_check_passa_dentro_do_limite():
    rows = [("CLAUDE.md", 100, "sempre"), ("AGENTS.md", 200, "sempre")]
    assert context_budget.check(rows, total_limit=300) == (300, [])


def test_check_falha_total_e_ficheiro():
    rows = [("CLAUDE.md", 5000, "sempre"), ("AGENTS.md", 200, "sempre")]
    total, failures = context_budget.check(rows, total_limit=1000, file_limits={"CLAUDE.md": 3000})
    assert total == 5200
    assert len(failures) == 2


def test_collect_mede_ficheiros(tmp_path):
    (tmp_path / "CLAUDE.md").write_bytes(b"x" * 10)
    (tmp_path / "AGENTS.md").write_bytes(b"y" * 20)
    memory = tmp_path / "MEMORY.md"
    memory.write_bytes(b"z" * 30)
    rows = {name: n for name, n, _ in context_budget.collect(tmp_path, memory)}
    assert rows["CLAUDE.md"] == 10 and rows["AGENTS.md"] == 20 and rows["MEMORY.md"] == 30
    assert rows["descrições das skills"] == 0
