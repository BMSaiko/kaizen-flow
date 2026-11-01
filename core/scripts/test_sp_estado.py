"""Testes de scripts/sp-estado.py (estado de um SP numa só leitura)."""
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("sp_estado", Path(__file__).with_name("sp-estado.py"))
sp_estado = importlib.util.module_from_spec(_spec)
sys.modules["sp_estado"] = sp_estado
_spec.loader.exec_module(sp_estado)

SP = """---
status: {st}
slug: {slug}
project: demo
priority: P2
modo: manual
parent: mae
depends_on: [dep-a, dep-b]
gates:
  - cmd: python -I x.py
---
# Super Prompt

## 4. Success criteria (verifiable)
- [x] um
- [ ] dois
- [ ] tres

## 7. Steps (numbered, ordered)
1. Primeiro.
2. Segundo.

## Progresso
- l1
- l2
- l3
- l4
"""


def make(tmp_path, folder, slug, st=None):
    d = tmp_path / "demo" / "sp" / folder
    d.mkdir(parents=True)
    f = d / f"{slug}-2026-10-26.md"
    f.write_text(SP.format(st=st or folder, slug=slug), encoding="utf-8")
    return f


def test_doing_resume_curto(tmp_path):
    make(tmp_path, "Done", "dep-a")
    make(tmp_path, "Doing", "alvo")
    out = sp_estado.estado("alvo", root=tmp_path, git_lines=["master", "M a.py"])
    lines = out.splitlines()
    assert len(lines) <= 30
    assert "Doing" in out and "1/3" in out and "gates: 1" in out
    assert "dep-b" in out and "master" in out and "a.py" in out
    assert "l4" in out and "l1" not in out  # só as últimas linhas do Progresso


def test_todo_por_caminho(tmp_path):
    f = make(tmp_path, "TODO", "alvo")
    out = sp_estado.estado(str(f), root=tmp_path, git_lines=["master"])
    assert "TODO" in out and "Progresso" not in out.split("progresso:")[0]


def test_inexistente(tmp_path):
    out = sp_estado.estado("nada", root=tmp_path, git_lines=["master"])
    assert "não encontrado" in out


def test_limita_ficheiros_git(tmp_path):
    make(tmp_path, "Doing", "alvo")
    out = sp_estado.estado("alvo", root=tmp_path, git_lines=["master"] + [f"M f{i}" for i in range(50)])
    assert len(out.splitlines()) <= 30


def test_mae_pergunta_concorrencia(tmp_path):
    make(tmp_path, "Doing", "filho")  # parent: mae
    d = tmp_path / "demo" / "sp" / "TODO"
    d.mkdir(parents=True)
    (d / "mae-2026-10-26.md").write_text(
        SP.format(st="TODO", slug="mae").replace("parent: mae\n", "kind: program\n"), encoding="utf-8")
    mae = sp_estado.estado("mae", root=tmp_path, git_lines=["master"])
    filho = sp_estado.estado("filho", root=tmp_path, git_lines=["master"])
    assert "perguntar concorrência" in mae and "1 filhos" in mae
    assert "perguntar concorrência" not in filho
