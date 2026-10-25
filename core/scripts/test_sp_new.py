"""Testes de scripts/sp-new.py (FS em diretório temporário, data injetada)."""
import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

_here = Path(__file__).parent
for name, file in (("sp_validate", "sp-validate.py"), ("sp_new", "sp-new.py")):
    _spec = importlib.util.spec_from_file_location(name, _here / file)
    mod = importlib.util.module_from_spec(_spec)
    sys.modules[name] = mod
    _spec.loader.exec_module(mod)
sp_new, sp_validate = sys.modules["sp_new"], sys.modules["sp_validate"]

TODAY = date(2026, 10, 18)


def project(tmp_path, name="atlas"):
    (tmp_path / name / "sp" / "TODO").mkdir(parents=True)
    return tmp_path


def test_cria_em_todo_com_frontmatter_e_oito_seccoes(tmp_path):
    root = project(tmp_path)
    path = sp_new.create(root, "atlas", "abc", "P2", TODAY)
    assert path == root / "atlas/sp/TODO/abc-2026-10-18.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith(
        "---\nstatus: TODO\ncreated: 2026-10-18T00:00:00Z\nupdated: 2026-10-18T00:00:00Z\n"
        "phase: SP\nslug: abc\ndate: 2026-10-18\nproject: atlas\npriority: P2\nmodo: manual\n---\n"
    )
    for n, title in enumerate(("Role", "Context", "Objective", "Success criteria",
                               "Constraints", "Seams", "Steps", "Done-when"), 1):
        assert f"## {n}. {title}" in text


def test_template_por_preencher_falha_so_nas_seccoes_vazias(tmp_path):
    path = sp_new.create(project(tmp_path), "atlas", "abc", "P1", TODAY)
    errors = sp_validate.validate(path.read_text(encoding="utf-8"), folder="TODO")
    assert len(errors) == 8 and all("vazia" in e for e in errors)


def test_parent_e_depends_on_opcionais(tmp_path):
    path = sp_new.create(project(tmp_path), "atlas", "abc", "P3", TODAY, parent="prog", depends_on=["a", "b"])
    head = path.read_text(encoding="utf-8").split("---\n")[1]
    assert "parent: prog\n" in head and "depends_on: [a, b]\n" in head


def test_recusa_slug_ja_existente_no_projeto(tmp_path):
    root = project(tmp_path)
    first = sp_new.create(root, "atlas", "abc", "P2", TODAY)
    before = first.read_bytes()
    with pytest.raises(sp_new.SpNewError, match="já existe"):
        sp_new.create(root, "atlas", "abc", "P2", date(2026, 10, 19))
    assert first.read_bytes() == before
    assert len(list((root / "atlas/sp/TODO").glob("*.md"))) == 1


def test_recusa_slug_existente_noutra_pasta(tmp_path):
    root = project(tmp_path)
    done = root / "atlas/sp/Done/abc-2026-09-01.md"
    done.parent.mkdir(parents=True)
    done.write_text("---\nstatus: Done\nslug: abc\nproject: atlas\n---\n", encoding="utf-8")
    with pytest.raises(sp_new.SpNewError, match="já existe"):
        sp_new.create(root, "atlas", "abc", "P2", TODAY)


def test_mesmo_slug_noutro_projeto_e_permitido(tmp_path):
    root = project(project(tmp_path), "kaizen")
    sp_new.create(root, "atlas", "abc", "P2", TODAY)
    sp_new.create(root, "kaizen", "abc", "P2", TODAY)


@pytest.mark.parametrize("slug,priority", [("ABC", "P2"), ("a b", "P2"), ("-a", "P2"), ("abc", "P4")])
def test_slug_ou_prioridade_invalidos(tmp_path, slug, priority):
    with pytest.raises(sp_new.SpNewError):
        sp_new.create(project(tmp_path), "atlas", slug, priority, TODAY)


def test_projeto_inexistente_nao_cria_pastas(tmp_path):
    with pytest.raises(sp_new.SpNewError, match="projeto"):
        sp_new.create(tmp_path, "atlsa", "abc", "P2", TODAY)
    assert list(tmp_path.iterdir()) == []


def test_cli_imprime_caminho_e_rc(tmp_path, capsys):
    root = project(tmp_path)
    args = ["--project", "atlas", "--slug", "abc", "--priority", "P2", "--root", str(root)]
    assert sp_new.main(args) == 0
    assert "abc-" in capsys.readouterr().out
    assert sp_new.main(args) == 1
    assert "já existe" in capsys.readouterr().err


def test_parse_children_com_dependencias():
    assert sp_new.parse_children("a,b:a,c:a+b") == [("a", []), ("b", ["a"]), ("c", ["a", "b"])]


def test_program_cria_mae_e_filhos_em_todo(tmp_path):
    root = project(tmp_path)
    paths = sp_new.create_program(root, "atlas", "prog", "P2", TODAY, [("a", []), ("b", ["a"])])
    assert [p.name for p in paths] == ["prog-2026-10-18.md", "a-2026-10-18.md", "b-2026-10-18.md"]
    mae = paths[0].read_text(encoding="utf-8")
    assert mae.split("---\n")[1].endswith(
        "priority: P2\nmodo: manual\nkind: program\nchildren:\n"
        "  - slug: a\n    depends_on: []\n    state: TODO\n"
        "  - slug: b\n    depends_on: [a]\n    state: TODO\n"
    )
    head_b = paths[2].read_text(encoding="utf-8").split("---\n")[1]
    assert "parent: prog\n" in head_b and "depends_on: [a]\n" in head_b
    assert "parent:" in paths[1].read_text(encoding="utf-8") and "depends_on" not in paths[1].read_text(encoding="utf-8")


def test_program_recusa_dependencia_fora_dos_filhos_sem_criar_nada(tmp_path):
    root = project(tmp_path)
    with pytest.raises(sp_new.SpNewError, match="depende de 'x'"):
        sp_new.create_program(root, "atlas", "prog", "P2", TODAY, [("a", ["x"])])
    assert list((root / "atlas/sp/TODO").glob("*.md")) == []


def test_program_recusa_slug_existente_sem_criar_nada(tmp_path):
    root = project(tmp_path)
    sp_new.create(root, "atlas", "b", "P2", TODAY)
    with pytest.raises(sp_new.SpNewError, match="já existe"):
        sp_new.create_program(root, "atlas", "prog", "P2", TODAY, [("a", []), ("b", [])])
    assert [p.name for p in (root / "atlas/sp/TODO").glob("*.md")] == ["b-2026-10-18.md"]


def test_program_recusa_filhos_repetidos_ou_vazios(tmp_path):
    root = project(tmp_path)
    with pytest.raises(sp_new.SpNewError, match="repetido"):
        sp_new.create_program(root, "atlas", "prog", "P2", TODAY, [("a", []), ("a", [])])
    with pytest.raises(sp_new.SpNewError, match="filhos"):
        sp_new.create_program(root, "atlas", "prog", "P2", TODAY, [])


def test_modo_auto_grava_no_frontmatter_e_default_e_manual(tmp_path):
    root = project(tmp_path)
    auto = sp_new.create(root, "atlas", "a", "P2", TODAY, modo="auto").read_text(encoding="utf-8")
    assert "\nmodo: auto\n" in auto
    assert "\nmodo: manual\n" in sp_new.create(root, "atlas", "b", "P2", TODAY).read_text(encoding="utf-8")


def test_modo_invalido_e_recusado_sem_criar_nada(tmp_path):
    root = project(tmp_path)
    with pytest.raises(sp_new.SpNewError, match="modo inválido"):
        sp_new.create(root, "atlas", "abc", "P2", TODAY, modo="semi")
    assert list((root / "atlas/sp/TODO").glob("*.md")) == []


def test_program_aplica_modo_a_mae_e_filhos(tmp_path):
    root = project(tmp_path)
    paths = sp_new.create_program(root, "atlas", "prog", "P2", TODAY, [("a", []), ("b", ["a"])], modo="auto")
    assert all("\nmodo: auto\n" in p.read_text(encoding="utf-8") for p in paths)


def test_cli_modo(tmp_path, capsys):
    root = project(tmp_path)
    base = ["--project", "atlas", "--priority", "P2", "--root", str(root)]
    assert sp_new.main([*base, "--slug", "a", "--modo", "auto"]) == 0
    assert "modo: auto" in (root / "atlas/sp/TODO/a-" f"{date.today().isoformat()}.md").read_text(encoding="utf-8")
    assert sp_new.main([*base, "--slug", "b", "--modo", "semi"]) == 1
    assert "modo inválido" in capsys.readouterr().err


def test_cli_program(tmp_path, capsys):
    root = project(tmp_path)
    args = ["--project", "atlas", "--program", "prog", "--children", "a,b:a", "--priority", "P2", "--root", str(root)]
    assert sp_new.main(args) == 0
    assert len(capsys.readouterr().out.splitlines()) == 3
    assert sp_new.main(["--project", "atlas", "--priority", "P2", "--root", str(root)]) == 1
    assert "--slug" in capsys.readouterr().err


def test_autorizacoes_vao_para_o_frontmatter_e_validam(tmp_path):
    auth = {"commit": "auto", "push": "nunca", "pr": "nunca", "restricoes": "não tocar em AGENTS.md"}
    path = sp_new.create(project(tmp_path), "atlas", "abc", "P2", TODAY, auth=auth)
    text = path.read_text(encoding="utf-8")
    assert "modo: manual\ncommit: auto\npush: nunca\npr: nunca\nrestricoes: não tocar em AGENTS.md\n---" in text
    assert not any(e.startswith(("commit", "push", "pr")) for e in sp_validate.validate(text, "TODO"))


@pytest.mark.parametrize("auth", [
    {"push": "talvez"}, {"commit": "nunca", "push": "auto"}, {"push": "pergunta", "pr": "auto"},
    {"restricoes": "a\nb"},
])
def test_autorizacoes_invalidas_recusadas_sem_criar(tmp_path, auth):
    root = project(tmp_path)
    with pytest.raises(sp_new.SpNewError):
        sp_new.create(root, "atlas", "abc", "P2", TODAY, auth=auth)
    assert not list((root / "atlas/sp/TODO").iterdir())


def test_program_herda_autorizacoes_nos_filhos(tmp_path):
    paths = sp_new.create_program(project(tmp_path), "atlas", "prog", "P2", TODAY, [("a", [])],
                                  auth={"push": "nunca"})
    assert all("push: nunca" in p.read_text(encoding="utf-8") for p in paths)


def test_sem_autorizacoes_frontmatter_inalterado(tmp_path):
    text = sp_new.create(project(tmp_path), "atlas", "abc", "P2", TODAY).read_text(encoding="utf-8")
    assert "commit:" not in text and "push:" not in text


def test_gates_e_prova_vao_para_o_frontmatter_e_validam(tmp_path):
    path = sp_new.create(project(tmp_path), "atlas", "abc", "P2", TODAY,
                         gates=["python -I scripts/test_sp_list.py", "npm test"], prova="python -I scripts/x.py")
    text = path.read_text(encoding="utf-8")
    assert "gates:\n  - cmd: python -I scripts/test_sp_list.py\n  - cmd: npm test\nprova: python -I scripts/x.py\n---" in text
    assert not any("gate" in e or "prova" in e for e in sp_validate.validate(text, "TODO"))


@pytest.mark.parametrize("kw", [
    {"gates": ["npm test", "npm test"]}, {"gates": [""]}, {"gates": ["git add -A"]},
    {"gates": ["a\nb"]}, {"prova": "a\nb"}, {"prova": "cat .env"},
])
def test_gates_prova_invalidos_recusados_sem_criar(tmp_path, kw):
    root = project(tmp_path)
    with pytest.raises(sp_new.SpNewError):
        sp_new.create(root, "atlas", "abc", "P2", TODAY, **kw)
    assert not list((root / "atlas/sp/TODO").iterdir())


def test_cli_gate_repetivel_e_prova(tmp_path, capsys):
    root = project(tmp_path)
    rc = sp_new.main(["--root", str(root), "--project", "atlas", "--slug", "abc", "--priority", "P2",
                      "--gate", "npm test", "--gate", "npm run lint", "--prova", "npm run e2e"])
    assert rc == 0
    text = Path(capsys.readouterr().out.strip()).read_text(encoding="utf-8")
    assert "  - cmd: npm test\n  - cmd: npm run lint\nprova: npm run e2e" in text
