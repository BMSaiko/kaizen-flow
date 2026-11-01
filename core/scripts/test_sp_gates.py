"""Testes de scripts/sp-gates.py (gates executáveis do frontmatter do SP)."""
import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("sp_gates", Path(__file__).with_name("sp-gates.py"))
sp_gates = importlib.util.module_from_spec(_spec)
sys.modules["sp_gates"] = sp_gates
_spec.loader.exec_module(sp_gates)

PY = f'"{sys.executable}"'


@pytest.fixture(autouse=True)
def _cache_isolada(tmp_path, monkeypatch):
    """`main()` sem --full grava CACHE_PATH: desviar para tmp para não sujar o repo."""
    monkeypatch.setattr(sp_gates, "CACHE_PATH", tmp_path / "gates-cache.json")


def sp_text(*gates):
    lines = ["---", "status: Doing", "slug: x", "gates:"]
    for cmd, extra in gates:
        lines += [f"  - cmd: {cmd}"] + [f"    {k}: {v}" for k, v in extra.items()]
    return "\n".join(lines + ["prova: ver output", "---", "# corpo", "- cmd: rm -rf /"])


def test_parse_gates_le_so_o_frontmatter():
    gates = sp_gates.parse_gates(sp_text(("echo a", {"cwd": ".", "timeout": 5}), ("echo b", {})))
    assert gates == [
        {"cmd": "echo a", "cwd": ".", "timeout": 5, "inputs": []},
        {"cmd": "echo b", "cwd": ".", "timeout": 300, "inputs": []},
    ]


def test_sem_gates_devolve_lista_vazia():
    assert sp_gates.parse_gates("---\nslug: x\n---\ncorpo") == []


@pytest.mark.parametrize("cmd", [
    "git push --force", "git reset --hard HEAD", "git clean -fd", "git add -A", "git add .",
    "cat .env", "type .env.local", "cat server.pem", "git push origin -f",
])
def test_comandos_proibidos_recusados(cmd):
    assert sp_gates.forbidden(cmd)


@pytest.mark.parametrize("cmd", ["python -I scripts/test_sp_list.py", "npm test", "git add scripts/x.py", "git status"])
def test_comandos_normais_aceites(cmd):
    assert sp_gates.forbidden(cmd) is None


def test_problemas_apanha_vazio_duplicado_e_proibido():
    base = {"cwd": ".", "timeout": 1}
    gates = [{"cmd": "", **base}, {"cmd": "a", **base}, {"cmd": "a", **base}, {"cmd": "git add -A", **base}]
    text = " ".join(sp_gates.problems(gates))
    assert "vazio" in text and "duplicado" in text and "proibido" in text


def test_run_para_no_primeiro_vermelho(tmp_path):
    cwd = str(tmp_path)
    gates = [
        {"cmd": f'{PY} -c "print(1)"', "cwd": cwd, "timeout": 30},
        {"cmd": f'{PY} -c "import sys; print(99); sys.exit(3)"', "cwd": cwd, "timeout": 30},
        {"cmd": f'{PY} -c "print(2)"', "cwd": cwd, "timeout": 30},
    ]
    results = sp_gates.run(gates)
    assert [r["rc"] for r in results] == [0, 3]
    assert "99" in results[1]["tail"]


def test_run_timeout(tmp_path):
    gate = {"cmd": f'{PY} -c "import time; time.sleep(8)"', "cwd": str(tmp_path), "timeout": 1}
    (result,) = sp_gates.run([gate])
    assert result["rc"] != 0 and result["timeout"] is True


def test_main_rc_e_resumo(tmp_path, capsys):
    f = tmp_path / "sp.md"
    f.write_text(sp_text((f'{PY} -c "print(7)"', {"cwd": str(tmp_path)})), encoding="utf-8")
    assert sp_gates.main([str(f)]) == 0
    out = capsys.readouterr().out
    assert "rc=0" in out and "7" in out
    f.write_text(sp_text((f'{PY} -c "raise SystemExit(1)"', {"cwd": str(tmp_path)})), encoding="utf-8")
    assert sp_gates.main([str(f)]) == 1


def test_main_recusa_gate_proibido_sem_executar(tmp_path, capsys):
    f = tmp_path / "sp.md"
    f.write_text(sp_text(("git push --force", {})), encoding="utf-8")
    assert sp_gates.main([str(f)]) == 2
    assert "proibido" in capsys.readouterr().err


def test_main_sem_gates_rc_0_com_aviso(tmp_path, capsys):
    f = tmp_path / "sp.md"
    f.write_text("---\nslug: x\n---\ncorpo", encoding="utf-8")
    assert sp_gates.main([str(f)]) == 0
    assert "sem gates" in capsys.readouterr().out


# --- incremental (kf-gates-incrementais) ---
def _gate(tmp_path, cmd, inputs):
    return {"cmd": cmd, "cwd": str(tmp_path), "timeout": 30, "inputs": inputs}


def test_parse_gates_le_inputs():
    text = "---\ngates:\n  - cmd: echo x\n    inputs: a/*.py, b.md\n---\n"
    g = sp_gates.parse_gates(text)[0]
    assert g["inputs"] == ["a/*.py", "b.md"]
    assert sp_gates.parse_gates("---\ngates:\n  - cmd: echo x\n---\n")[0]["inputs"] == []


def test_cache_hit_miss_e_invalidacao(tmp_path):
    (tmp_path / "f.txt").write_text("1", encoding="utf-8")
    cache = tmp_path / "c.json"
    g = [_gate(tmp_path, f'python -c "print(1)"', ["f.txt"])]
    r1 = sp_gates.run(g, cache_path=cache)          # miss: corre
    assert r1[0]["rc"] == 0 and not r1[0].get("cached")
    r2 = sp_gates.run(g, cache_path=cache)          # hit: não corre
    assert r2[0]["rc"] == 0 and r2[0]["cached"]
    (tmp_path / "f.txt").write_text("2", encoding="utf-8")
    r3 = sp_gates.run(g, cache_path=cache)          # input mudou: corre
    assert not r3[0].get("cached")


def test_sem_inputs_corre_sempre(tmp_path):
    cache = tmp_path / "c.json"
    g = [_gate(tmp_path, 'python -c "print(1)"', [])]
    sp_gates.run(g, cache_path=cache)
    assert not sp_gates.run(g, cache_path=cache)[0].get("cached")


def test_vermelho_nao_entra_na_cache(tmp_path):
    (tmp_path / "f.txt").write_text("1", encoding="utf-8")
    cache = tmp_path / "c.json"
    g = [_gate(tmp_path, 'python -c "import sys; sys.exit(1)"', ["f.txt"])]
    sp_gates.run(g, cache_path=cache)
    assert sp_gates.run(g, cache_path=cache)[0]["rc"] == 1


def test_sem_cache_path_corre_tudo(tmp_path):
    """Fecho (sp-fechar chama run(gates) sem cache): nunca salta."""
    (tmp_path / "f.txt").write_text("1", encoding="utf-8")
    g = [_gate(tmp_path, 'python -c "print(1)"', ["f.txt"])]
    assert not sp_gates.run(g)[0].get("cached") and not sp_gates.run(g)[0].get("cached")


def test_tabela_marca_gates_nao_corridos_apos_vermelho(tmp_path):
    cwd = str(tmp_path)
    gates = [
        {"cmd": f'{PY} -c "print(1)"', "cwd": cwd, "timeout": 30},
        {"cmd": f'{PY} -c "raise SystemExit(3)"', "cwd": cwd, "timeout": 30},
        {"cmd": f'{PY} -c "print(2)"', "cwd": cwd, "timeout": 30},
    ]
    rows = sp_gates.table(sp_gates.run(gates), len(gates)).splitlines()
    assert "verde" in rows[2] and "VERMELHO" in rows[3] and "não correu" in rows[4]


def test_main_imprime_tabela_e_nao_corre_gate_apos_vermelho(tmp_path, capsys):
    f = tmp_path / "sp.md"
    marker = tmp_path / "ran.txt"
    f.write_text(sp_text((f'{PY} -c "raise SystemExit(1)"', {"cwd": str(tmp_path)}),
                         (f'{PY} -c "import pathlib; pathlib.Path(\'ran.txt\').touch()"', {"cwd": str(tmp_path)})),
                 encoding="utf-8")
    assert sp_gates.main([str(f), "--full"]) == 1
    assert not marker.exists()
    assert "| 2 | — | — | não correu |" in capsys.readouterr().out


def test_detect_gates_por_tipo_de_repo(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"test": "x", "lint": "y"}}', encoding="utf-8")
    (tmp_path / "src-tauri").mkdir()
    (tmp_path / "src-tauri" / "Cargo.toml").write_text("", encoding="utf-8")
    assert sp_gates.detect_gates(tmp_path) == ["cargo check --manifest-path src-tauri/Cargo.toml", "npm run lint", "npm test"]


def test_detect_gates_python_e_desconhecido(tmp_path, capsys):
    assert sp_gates.detect_gates(tmp_path) == [] and sp_gates.suggestion(tmp_path) == ""
    assert sp_gates.main(["--sugerir", str(tmp_path)]) == 1
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    assert sp_gates.main(["--sugerir", str(tmp_path)]) == 0
    assert "cmd: python -m pytest -q" in capsys.readouterr().out


def test_sugestao_nunca_usa_or_true(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"build": "b", "test": "t"}}', encoding="utf-8")
    assert "|| true" not in sp_gates.suggestion(tmp_path)
    text = "---\n" + sp_gates.suggestion(tmp_path) + "\n---\n"
    assert sp_gates.problems(sp_gates.parse_gates(text)) == []
