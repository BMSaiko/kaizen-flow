"""Testes de sp-validate-hook.py (hook PostToolUse): corre o script como o harness, com JSON no stdin."""
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).with_name("sp-validate-hook.py")


def _run(payload):
    return subprocess.run([sys.executable, "-I", str(HOOK)], input=payload, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _ev(path):
    return json.dumps({"tool_input": {"file_path": str(path)}})


def test_json_invalido_sai_com_zero():
    assert _run("não é json").returncode == 0


def test_ficheiro_fora_de_sp_e_ignorado(tmp_path):
    f = tmp_path / "notas.md"
    f.write_text("qualquer", encoding="utf-8")
    assert _run(_ev(f)).returncode == 0


def test_sp_inexistente_e_ignorado(tmp_path):
    assert _run(_ev(tmp_path / "sp" / "TODO" / "x.md")).returncode == 0


def test_ficheiro_com_prefixo_underscore_e_ignorado(tmp_path):
    f = tmp_path / "sp" / "TODO" / "_modelo.md"
    f.parent.mkdir(parents=True)
    f.write_text("vazio", encoding="utf-8")
    assert _run(_ev(f)).returncode == 0


def test_sp_invalido_devolve_2_com_problemas_no_stderr(tmp_path):
    f = tmp_path / "sp" / "TODO" / "x.md"
    f.parent.mkdir(parents=True)
    f.write_text("sem frontmatter", encoding="utf-8")
    r = _run(_ev(f))
    assert r.returncode == 2
    assert r.stderr.startswith("x.md: ")
