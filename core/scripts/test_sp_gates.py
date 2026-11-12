"""Testes de scripts/sp-gates.py (gates executáveis do frontmatter do SP)."""
import sys
from pathlib import Path

import pytest
from sp_carregar import carregar  # noqa: E402

sp_gates = carregar(Path(__file__).with_name("sp-gates.py"), "sp_gates", fresco=True)

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
        {"cmd": "echo a", "cwd": ".", "timeout": 5, "inputs": [], "timeout_declarado": True},
        {"cmd": "echo b", "cwd": ".", "timeout": 300, "inputs": [], "timeout_declarado": False},
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


def _sp_em(root, slug, pasta="Doing"):
    import kaizen_engine
    d = kaizen_engine.load("sp-list").default_root(root) / "x" / "sp" / pasta
    d.mkdir(parents=True)
    f = d / f"{slug}-2026-01-01.md"
    f.write_text(f"---\nstatus: {pasta}\nslug: {slug}\nproject: x\n---\n", encoding="utf-8")
    return f


def test_resolve_sp_slug_so_na_worktree(tmp_path):
    wt, main = tmp_path / "wt", tmp_path / "main"
    f = _sp_em(wt, "so-wt")
    main.mkdir()
    assert sp_gates.resolve_sp("so-wt", roots=[wt, main]) == (f, wt)


def test_resolve_sp_slug_em_master_sem_worktree(tmp_path):
    main = tmp_path / "main"
    f = _sp_em(main, "em-master", "TODO")
    assert sp_gates.resolve_sp("em-master", roots=[main]) == (f, main)


def test_resolve_sp_caminho_e_inexistente(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("x", encoding="utf-8")
    assert sp_gates.resolve_sp(str(f)) == (f, None)
    assert sp_gates.resolve_sp("nao-existe", roots=[tmp_path]) == (None, None)
    assert sp_gates.resolve_sp(str(tmp_path / "b.md")) == (None, None)


# ---- fase de testes: corre `test.cmd` da config do projeto-alvo como gate ----

import json  # noqa: E402


def _repo(tmp_path, cmd=None, raw=None):
    repo = tmp_path / "alvo"
    repo.mkdir()
    if raw is not None:
        (repo / "kaizen.config.json").write_text(raw, encoding="utf-8")
    elif cmd is not None:
        (repo / "kaizen.config.json").write_text(json.dumps({"test": {"cmd": cmd}}), encoding="utf-8")
    return repo


def _sp_testes(tmp_path, extra=""):
    f = tmp_path / "sp.md"
    f.write_text(f"---\nstatus: Doing\nslug: x\n{extra}---\n# corpo\n", encoding="utf-8")
    return f


def test_test_cmd_le_a_config(tmp_path):
    assert sp_gates.test_cmd(_repo(tmp_path, "npm test")) == "npm test"


@pytest.mark.parametrize("raw", [None, "{", "[]", '{"test": "npm test"}', '{"test": {"cmd": "  "}}', '{"test": {}}'])
def test_test_cmd_em_falta_ou_invalido(tmp_path, raw):
    assert sp_gates.test_cmd(_repo(tmp_path, raw=raw)) is None


def test_fase_testes_sucesso(tmp_path):
    rc, results = sp_gates.fase_testes(_repo(tmp_path, f"{PY} -c \"print('ok')\""))
    assert rc == 0 and results[0]["rc"] == 0 and "ok" in results[0]["tail"]


def test_fase_testes_falha_bloqueia(tmp_path):
    rc, results = sp_gates.fase_testes(_repo(tmp_path, f"{PY} -c \"import sys; sys.exit(3)\""))
    assert rc == 1 and results[0]["rc"] == 3


def test_fase_testes_timeout(tmp_path):
    rc, results = sp_gates.fase_testes(_repo(tmp_path, f"{PY} -c \"import time; time.sleep(5)\""), timeout=1)
    assert rc == 1 and results[0]["timeout"] is True


def test_fase_testes_sem_comando_nao_corre_e_avisa(tmp_path):
    rc, results = sp_gates.fase_testes(_repo(tmp_path))
    assert rc == sp_gates.RC_SEM_COMANDO and results == []


def test_fase_testes_recusa_irreversivel(tmp_path):
    rc, results = sp_gates.fase_testes(_repo(tmp_path, "git reset --hard"))
    assert rc == 2 and results == []


def test_fase_testes_corre_no_cwd_do_repo(tmp_path):
    repo = _repo(tmp_path, f"{PY} -c \"import os; print(os.path.basename(os.getcwd()))\"")
    rc, results = sp_gates.fase_testes(repo)
    assert rc == 0 and "alvo" in results[0]["tail"]


def test_registar_acrescenta_tentativas_sem_tocar_no_resto(tmp_path):
    sp = _sp_testes(tmp_path)
    red = [{"cmd": "npm test", "rc": 1, "timeout": False, "secs": 2.0, "tail": "boom"}]
    green = [{"cmd": "npm test", "rc": 0, "timeout": False, "secs": 1.0, "tail": ""}]
    assert sp_gates.registar(sp, red) == 1
    assert sp_gates.registar(sp, green) == 2
    text = sp.read_text(encoding="utf-8")
    assert text.startswith("---\nstatus: Doing") and "# corpo" in text
    assert text.count("## Testes") == 1
    assert "- tentativa 1: `npm test` rc=1 VERMELHO" in text and "- tentativa 2: `npm test` rc=0 verde" in text
    assert sp_gates.tentativas(text) == 0  # o verde zera as falhas seguidas


def test_registar_preserva_crlf(tmp_path):
    sp = tmp_path / "sp.md"
    sp.write_bytes(b"---\r\nslug: x\r\n---\r\n# corpo\r\n")
    sp_gates.registar(sp, [{"cmd": "c", "rc": 0, "timeout": False, "secs": 0.1, "tail": ""}])
    raw = sp.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")


def test_registar_timeout_e_sem_comando(tmp_path):
    sp = _sp_testes(tmp_path)
    sp_gates.registar(sp, [{"cmd": "c", "rc": 124, "timeout": True, "secs": 1.0, "tail": ""}])
    sp_gates.registar(sp, [], aviso="sem test.cmd")
    text = sp.read_text(encoding="utf-8")
    assert "TIMEOUT" in text and "sem test.cmd" in text
    assert sp_gates.tentativas(text) == 1  # o aviso não conta como tentativa


def test_limite_de_tentativas_para(tmp_path):
    sp = _sp_testes(tmp_path, "max_tentativas: 1\nparar_se: [gate-falha]\n")
    sp_gates.registar(sp, [{"cmd": "c", "rc": 1, "timeout": False, "secs": 0.1, "tail": ""}])
    assert sp_gates.deve_parar(sp) is True


def test_limite_nao_atingido_ou_sem_parar_se(tmp_path):
    sp = _sp_testes(tmp_path, "max_tentativas: 3\nparar_se: [gate-falha]\n")
    sp_gates.registar(sp, [{"cmd": "c", "rc": 1, "timeout": False, "secs": 0.1, "tail": ""}])
    assert sp_gates.deve_parar(sp) is False
    sem_parar = tmp_path / "sem-parar.md"
    sem_parar.write_text("---\nslug: y\nmax_tentativas: 1\nparar_se: [custo]\n---\n", encoding="utf-8")
    sp_gates.registar(sem_parar, [{"cmd": "c", "rc": 1, "timeout": False, "secs": 0.1, "tail": ""}])
    assert sp_gates.deve_parar(sem_parar) is False


def test_main_testes_ponta_a_ponta(tmp_path, capsys):
    repo = _repo(tmp_path, f"{PY} -c \"print('verde')\"")
    sp = _sp_testes(tmp_path)
    assert sp_gates.main(["--testes", str(repo), "--sp", str(sp)]) == 0
    assert "verde" in capsys.readouterr().out
    assert "tentativa 1" in sp.read_text(encoding="utf-8")


def test_main_testes_sem_comando_rc3_e_pergunta(tmp_path, capsys):
    repo = _repo(tmp_path)
    sp = _sp_testes(tmp_path)
    assert sp_gates.main(["--testes", str(repo), "--sp", str(sp)]) == sp_gates.RC_SEM_COMANDO
    err = capsys.readouterr().err
    assert "test.cmd" in err and "AskUserQuestion" in err
    assert "sem test.cmd" in sp.read_text(encoding="utf-8")


def test_main_testes_para_ao_atingir_limite(tmp_path, capsys):
    repo = _repo(tmp_path, f"{PY} -c \"import sys; sys.exit(1)\"")
    sp = _sp_testes(tmp_path, "max_tentativas: 1\nparar_se: [gate-falha]\n")
    assert sp_gates.main(["--testes", str(repo), "--sp", str(sp)]) == 1
    assert sp_gates.main(["--testes", str(repo), "--sp", str(sp)]) == sp_gates.RC_LIMITE
    assert sp.read_text(encoding="utf-8").count("- tentativa") == 1


def test_main_com_caminho_do_sp_corre_os_gates(tmp_path):
    sp = tmp_path / "x.md"
    sp.write_text(sp_text((f"{PY} -c pass", {})), encoding="utf-8")
    try:
        rc = sp_gates.main([str(sp)])
    except SystemExit as e:
        rc = e.code
    assert rc in (0, None)


def test_avisos_suite_completa_sem_timeout():
    sem = sp_gates.parse_gates(sp_text(("python -m pytest scripts -q", {})))
    com = sp_gates.parse_gates(sp_text(("python -m pytest scripts -q", {"timeout": 1200})))
    um = sp_gates.parse_gates(sp_text(("python -m pytest scripts/sub -q", {})))
    assert sp_gates.avisos(sem) and "timeout" in sp_gates.avisos(sem)[0]
    assert sp_gates.avisos(com) == [] and sp_gates.avisos(um) == []
