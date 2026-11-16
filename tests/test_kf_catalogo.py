"""Testes do catálogo de edge cases (EC) e use cases (UC): estrutura, geração dos .md e relatório de cobertura."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "catalog"))
import kf_catalogo as kc  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def base():
    return {
        "versao": 1,
        "limiar": {"ec": 0.9, "uc": 1.0},
        "categorias": [
            {"id": "interruption", "titulo": "Interruption"},
            {"id": "crash", "titulo": "Crash"},
        ],
        "filhos": ["catalogo-ec-uc", "checkpoint-journal"],
        "edge_cases": [
            {"id": "EC-001", "categoria": "interruption", "gatilho": "Ctrl+C | mid step", "esperado": "state kept",
             "filho": "checkpoint-journal", "teste": "tests/test_a.py::test_um"},
            {"id": "EC-002", "categoria": "crash", "gatilho": "gate rc 1", "esperado": "stop",
             "filho": "catalogo-ec-uc", "teste": "por cobrir"},
        ],
        "use_cases": [
            {"id": "UC-001", "objetivo": "Start", "comando": "`kaizen init`", "resultado": "files",
             "filho": "catalogo-ec-uc", "teste": "tests/b.test.js::init funciona"},
        ],
    }


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_um():\n    pass\n\nclass K:\n    def test_m(self):\n        pass\n", encoding="utf-8")
    (tmp_path / "tests" / "b.test.js").write_text('test("init funciona", () => {});\n', encoding="utf-8")
    (tmp_path / "docs").mkdir()
    return tmp_path


def escrever(repo, cat):
    p = repo / "docs" / "catalogo.json"
    p.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def test_catalogo_valido_sem_problemas(repo):
    assert kc.problemas(base(), repo) == []


def test_id_duplicado(repo):
    cat = base()
    cat["edge_cases"][1]["id"] = "EC-001"
    assert any("EC-001" in p and "duplicado" in p for p in kc.problemas(cat, repo))


def test_buraco_na_numeracao(repo):
    cat = base()
    cat["edge_cases"][1]["id"] = "EC-003"
    assert any("EC-003" in p and "EC-002" in p for p in kc.problemas(cat, repo))


def test_id_mal_formado(repo):
    cat = base()
    cat["use_cases"][0]["id"] = "UC-1"
    assert any("UC-1" in p for p in kc.problemas(cat, repo))


def test_teste_com_ficheiro_inexistente(repo):
    cat = base()
    cat["edge_cases"][0]["teste"] = "tests/test_nao_existe.py::test_um"
    assert any("test_nao_existe.py" in p for p in kc.problemas(cat, repo))


def test_teste_com_nome_inexistente_no_ficheiro(repo):
    cat = base()
    cat["edge_cases"][0]["teste"] = "tests/test_a.py::test_dois"
    assert any("test_dois" in p for p in kc.problemas(cat, repo))
    cat["use_cases"][0]["teste"] = "tests/b.test.js::outro nome"
    assert any("outro nome" in p for p in kc.problemas(cat, repo))


def test_teste_metodo_de_classe_e_aceite(repo):
    cat = base()
    cat["edge_cases"][0]["teste"] = "tests/test_a.py::K::test_m"
    assert kc.problemas(cat, repo) == []


@pytest.mark.parametrize("ref", ["/abs/test_a.py::test_um", "../fora.py::test_um", "tests/test_a.py", "tests/test_a.txt::x"])
def test_referencia_de_teste_invalida(repo, ref):
    cat = base()
    cat["edge_cases"][0]["teste"] = ref
    assert kc.problemas(cat, repo)


@pytest.mark.parametrize("ref", ["--rootdir=x.py::test_um", "-p.js::x", "tests/-x.py::test_um"])
def test_referencia_com_opcao_e_recusada(ref):
    # um caminho começado por "-" chegaria ao pytest/node como opção
    assert kc._ref(ref) is None


def test_categoria_vazia(repo):
    cat = base()
    cat["categorias"].append({"id": "windows", "titulo": "Windows"})
    assert any("windows" in p and "vazia" in p for p in kc.problemas(cat, repo))


def test_categoria_e_filho_desconhecidos(repo):
    cat = base()
    cat["edge_cases"][0]["categoria"] = "nada"
    cat["use_cases"][0]["filho"] = "ninguem"
    probs = kc.problemas(cat, repo)
    assert any("nada" in p for p in probs) and any("ninguem" in p for p in probs)


def test_campo_em_falta_ou_vazio(repo):
    cat = base()
    del cat["edge_cases"][0]["gatilho"]
    cat["use_cases"][0]["resultado"] = "  "
    probs = kc.problemas(cat, repo)
    assert any("gatilho" in p for p in probs) and any("resultado" in p for p in probs)


def test_topo_invalido(repo):
    assert kc.problemas([], repo)
    cat = base()
    cat["limiar"] = {"ec": 2}
    assert any("limiar" in p for p in kc.problemas(cat, repo))


def test_fracao():
    assert kc.fracao(9, 10) == 0.9
    assert kc.fracao(0, 0) == 0.0


def test_medir_so_conta_testes_que_passam(repo):
    cat = base()
    m = kc.medir(cat, {"tests/test_a.py::test_um": True, "tests/b.test.js::init funciona": False})
    assert (m["ec"]["cobertos"], m["ec"]["total"]) == (1, 2)
    assert (m["uc"]["cobertos"], m["uc"]["total"]) == (0, 1)
    assert m["ok"] is False
    assert {"id": "UC-001", "motivo": "falhou"} in m["uc"]["em_falta"]
    assert {"id": "EC-002", "motivo": "por cobrir"} in m["ec"]["em_falta"]


def test_rc_do_limiar(repo):
    cat = base()
    cat["edge_cases"][1]["teste"] = "tests/test_a.py::test_um"
    todos = {"tests/test_a.py::test_um": True, "tests/b.test.js::init funciona": True}
    assert kc.medir(cat, todos)["ok"] is True
    cat["limiar"]["ec"] = 0.9
    cat["edge_cases"][1]["teste"] = "por cobrir"
    assert kc.medir(cat, todos)["ok"] is False  # 0,5 < 0,9


def test_render_gera_tabelas_por_categoria_e_escapa_barras(repo):
    md = kc.render_edge_cases(base())
    assert "## Interruption" in md and "## Crash" in md
    assert "| EC-001 |" in md and "Ctrl+C \\| mid step" in md
    assert "`por cobrir`" in md
    uc = kc.render_use_cases(base())
    assert uc.splitlines()[0] == "# Use cases"
    assert "| UC-001 | Start | `kaizen init` | files | `tests/b.test.js::init funciona` |" in uc


def test_check_deteta_md_desatualizado_e_render_corrige(repo, capsys):
    p = escrever(repo, base())
    assert kc.main(["--check", "--file", str(p), "--root", str(repo)]) == 1
    assert "render" in capsys.readouterr().out
    assert kc.main(["render", "--file", str(p), "--root", str(repo)]) == 0
    assert kc.main(["--check", "--file", str(p), "--root", str(repo)]) == 0
    (repo / "docs" / "use-cases.md").write_text("# Use cases\n", encoding="utf-8")
    assert kc.main(["--check", "--file", str(p), "--root", str(repo)]) == 1


def test_check_catalogo_invalido_rc1(repo, capsys):
    cat = base()
    cat["edge_cases"][1]["id"] = "EC-001"
    p = escrever(repo, cat)
    assert kc.main(["--check", "--file", str(p), "--root", str(repo)]) == 1
    assert "duplicado" in capsys.readouterr().out


def test_json_ilegivel_ou_em_falta_rc1(repo, capsys):
    p = repo / "docs" / "catalogo.json"
    p.write_text("{ nao e json", encoding="utf-8")
    assert kc.main(["--check", "--file", str(p), "--root", str(repo)]) == 1
    assert kc.main(["report", "--file", str(repo / "nada.json"), "--root", str(repo)]) == 1
    assert "erro" in capsys.readouterr().err


def test_report_usa_o_executor_e_devolve_rc(repo, capsys, monkeypatch):
    p = escrever(repo, base())
    monkeypatch.setattr(kc, "correr_testes", lambda refs, root: {r: True for r in refs})
    assert kc.main(["report", "--file", str(p), "--root", str(repo)]) == 1  # EC 1/2 < 0,9
    out = capsys.readouterr().out
    assert "EC: 1/2" in out and "UC: 1/1" in out and "EC-002" in out
    assert kc.main(["report", "--json", "--file", str(p), "--root", str(repo)]) == 1
    dados = json.loads(capsys.readouterr().out)
    assert dados["ec"]["fracao"] == 0.5 and dados["uc"]["fracao"] == 1.0


def test_report_no_run_nao_corre_testes(repo, capsys, monkeypatch):
    p = escrever(repo, base())
    monkeypatch.setattr(kc, "correr_testes", lambda refs, root: pytest.fail("não devia correr"))
    kc.main(["report", "--no-run", "--file", str(p), "--root", str(repo)])
    assert "sem correr" in capsys.readouterr().out


def test_correr_testes_python_real(repo):
    (repo / "tests" / "test_c.py").write_text("def test_ok():\n    pass\n\ndef test_ko():\n    assert False\n", encoding="utf-8")
    r = kc.correr_testes(["tests/test_c.py::test_ok", "tests/test_c.py::test_ko"], repo)
    assert r == {"tests/test_c.py::test_ok": True, "tests/test_c.py::test_ko": False}


def test_correr_testes_js_real(repo):
    (repo / "tests" / "c.test.js").write_text(
        'const test = require("node:test");\nconst assert = require("node:assert");\n'
        'test("passa (sim)", () => {});\ntest("falha", () => { assert.ok(false); });\n', encoding="utf-8")
    r = kc.correr_testes(["tests/c.test.js::passa (sim)", "tests/c.test.js::falha", "tests/c.test.js::nao ha"], repo)
    assert r == {"tests/c.test.js::passa (sim)": True, "tests/c.test.js::falha": False, "tests/c.test.js::nao ha": False}


def test_catalogo_do_repo_e_valido_e_os_md_estao_em_dia():
    p = REPO / "docs" / "catalogo.json"
    cat = json.loads(p.read_text(encoding="utf-8"))
    assert kc.problemas(cat, REPO) == []
    assert len(cat["edge_cases"]) >= 30
    assert {c["id"] for c in cat["categorias"]} == {e["categoria"] for e in cat["edge_cases"]}
    assert len(cat["categorias"]) == 7
    assert kc.main(["--check", "--file", str(p), "--root", str(REPO)]) == 0


def test_base_nao_e_mutada_pelos_testes():
    a = base()
    b = copy.deepcopy(a)
    kc.medir(a, {})
    assert a == b
