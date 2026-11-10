import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff_resume as hr  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "handoff_resume.py"


def _mk(folder, name, age_h=0):
    p = folder / name
    p.write_text("x", encoding="utf-8")
    t = time.time() - age_h * 3600
    os.utime(p, (t, t))
    return p


def test_sem_handoff_sem_saida(tmp_path):
    assert hr.hook('{"source":"clear"}', tmp_path) == ""


def test_ignora_pendentes_e_antigos(tmp_path):
    _mk(tmp_path, "2026-11-10-pendentes.md")
    _mk(tmp_path, "velho.md", age_h=13)
    assert hr.hook('{"source":"clear"}', tmp_path) == ""


def test_mais_recente_e_outros(tmp_path):
    _mk(tmp_path, "a.md", age_h=2)
    b = _mk(tmp_path, "b.md", age_h=1)
    out = json.loads(hr.hook('{"source":"clear"}', tmp_path))
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert f'--consume "{b.as_posix()}"' in ctx
    assert "Outros pendentes: a.md." in ctx


def test_ignora_resume_e_compact(tmp_path):
    _mk(tmp_path, "a.md")
    assert hr.hook('{"source":"resume"}', tmp_path) == ""
    assert hr.hook('{"source":"compact"}', tmp_path) == ""


def test_nao_apaga(tmp_path):
    a = _mk(tmp_path, "a.md")
    hr.hook('{"source":"startup"}', tmp_path)
    assert a.exists()


def test_cli_rc0_mesmo_com_lixo(tmp_path):
    _mk(tmp_path, "a.md")
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(tmp_path)], input="não-json",
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and "--consume" in r.stdout
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(tmp_path / "nao-existe")], input="{}",
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and r.stdout == ""
