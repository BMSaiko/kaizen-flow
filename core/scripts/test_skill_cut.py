"""Testes de skill-cut.py (mover uma secção de SKILL.md para references/ com contagem verificada)."""
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("skill_cut", Path(__file__).with_name("skill-cut.py"))
skill_cut = importlib.util.module_from_spec(_spec)
sys.modules["skill_cut"] = skill_cut
_spec.loader.exec_module(skill_cut)

SKILL = "# Skill\n\n## Pitfalls\n\n- **Um.** primeiro\n  continua\n- **Dois.** segundo\n\n## Outro\n\nfica\n"


def _run(tmp_path, monkeypatch, capsys, *extra):
    skill = tmp_path / "s" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text(SKILL, encoding="utf-8", newline="\n")
    ref = skill.parent / "references" / "p.md"
    monkeypatch.setattr(sys, "argv", ["skill-cut", str(skill), "## Pitfalls", str(ref), "--title", "T", *extra])
    rc = skill_cut.main()
    return rc, skill, ref, capsys.readouterr().out


def test_split_blocks_bullets():
    pre, blocks = skill_cut.split_blocks(["", "- a", "  x", "- b"], numbered=False)
    assert pre == [""]
    assert blocks == ["- a\n  x", "- b"]


def test_split_blocks_numbered_ignora_bullets():
    _, blocks = skill_cut.split_blocks(["1. a", "- nota", "2. b"], numbered=True)
    assert blocks == ["1. a\n- nota", "2. b"]


def test_label_usa_negrito_ou_primeira_linha():
    assert skill_cut.label("- **Titulo.** resto") == "Titulo"
    assert skill_cut.label("### Cabecalho\ncorpo") == "Cabecalho"
    assert skill_cut.label("- texto simples.") == "texto simples"


def test_main_move_blocos_e_deixa_indice(tmp_path, monkeypatch, capsys):
    rc, skill, ref, out = _run(tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "blocos=2 indice=2" in out
    novo = skill.read_text(encoding="utf-8")
    assert "1. Um" in novo and "2. Dois" in novo
    assert "references/p.md" in novo
    assert "## Outro\n\nfica" in novo
    refs = ref.read_text(encoding="utf-8")
    assert "- **Um.** primeiro\n  continua" in refs and "- **Dois.** segundo" in refs
