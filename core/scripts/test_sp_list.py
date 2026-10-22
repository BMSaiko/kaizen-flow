"""Testes de scripts/sp-list.py (fixtures em ficheiros temporários)."""
import dataclasses
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("sp_list", Path(__file__).with_name("sp-list.py"))
sp_list = importlib.util.module_from_spec(_spec)
sys.modules["sp_list"] = sp_list
_spec.loader.exec_module(sp_list)


def make_sp(root, rel, slug, status="TODO", created="2026-10-01T10:00:00Z", priority=None, project=None,
            parent=None, depends_on=None, kind=None):
    path = root / rel / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"status: {status}", f"created: {created}", f"updated: {created}", "phase: SP", f"slug: {slug}"]
    if project:
        lines.append(f"project: {project}")
    if priority:
        lines.append(f"priority: {priority}")
    if parent:
        lines.append(f"parent: {parent}")
    if depends_on:
        lines.append(f"depends_on: [{', '.join(depends_on)}]")
    if kind:
        lines.append(f"kind: {kind}")
    lines += ["---", "# corpo"]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_parse_frontmatter_aspas_e_sem_aspas():
    text = "---\nstatus: TODO\ncreated: '2026-10-16T17:40:00Z'\nslug: \"abc\"\npriority: P1 # nota\n---\ncorpo: x"
    fm = sp_list.parse_frontmatter(text)
    assert fm == {"status": "TODO", "created": "2026-10-16T17:40:00Z", "slug": "abc", "priority": "P1"}


def test_parse_frontmatter_sem_frontmatter():
    assert sp_list.parse_frontmatter("# so corpo") == {}


def test_collect_ignora_done_e_arquivo(tmp_path):
    make_sp(tmp_path, "atlas/sp/TODO", "a", project="atlas")
    make_sp(tmp_path, "atlas/sp/Doing", "b", status="Doing", project="atlas")
    make_sp(tmp_path, "atlas/sp/Done", "c", status="Done", project="atlas")
    make_sp(tmp_path, "atlas/sp/arquivo/TODO", "d", project="atlas")
    slugs = sorted(s.slug for s in sp_list.collect(tmp_path))
    assert slugs == ["a", "b"]


def test_collect_all_inclui_done(tmp_path):
    make_sp(tmp_path, "atlas/sp/Done", "c", status="Done", project="atlas")
    assert [s.slug for s in sp_list.collect(tmp_path, include_done=True)] == ["c"]


def test_pasta_manda_e_avisa(tmp_path):
    make_sp(tmp_path, "atlas/sp/Doing", "x", status="Done", project="atlas")
    (sp,) = sp_list.collect(tmp_path)
    assert sp.status == "Doing"
    assert sp.warning
    assert "⚠ status≠pasta" in sp_list.render([sp])


def test_priority_default_p3_e_projeto_global(tmp_path):
    make_sp(tmp_path, "sp/TODO", "g")
    (sp,) = sp_list.collect(tmp_path)
    assert sp.priority == "P3"
    assert sp.project == "-"


def test_projeto_do_frontmatter_ganha(tmp_path):
    make_sp(tmp_path, "sp/TODO", "g", project="foodlister")
    (sp,) = sp_list.collect(tmp_path)
    assert sp.project == "foodlister"


def test_created_irregular_nao_rebenta(tmp_path):
    make_sp(tmp_path, "p/sp/TODO", "zz", created="2026-09-24T20:36:41.698ZZ")
    make_sp(tmp_path, "p/sp/TODO", "lixo", created="ontem")
    by_slug = {s.slug: s for s in sp_list.collect(tmp_path)}
    assert str(by_slug["zz"].created) == "2026-09-24"
    assert by_slug["lixo"].created is None
    assert "?" in sp_list.render([by_slug["lixo"]])


def test_ordenacao_default(tmp_path):
    make_sp(tmp_path, "p/sp/TODO", "todo-p1", priority="P1", created="2026-10-05")
    make_sp(tmp_path, "p/sp/Doing", "doing-p3-novo", status="Doing", created="2026-10-10")
    make_sp(tmp_path, "p/sp/Doing", "doing-p3-velho", status="Doing", created="2026-10-01")
    make_sp(tmp_path, "p/sp/TODO", "todo-p3-sem-data", created="???")
    make_sp(tmp_path, "p/sp/TODO", "todo-p3", created="2026-10-02")
    order = [s.slug for s in sp_list.sort_sps(sp_list.collect(tmp_path), "status")]
    assert order == ["doing-p3-velho", "doing-p3-novo", "todo-p1", "todo-p3", "todo-p3-sem-data"]


def test_ordenacao_priority_e_reverse(tmp_path):
    make_sp(tmp_path, "p/sp/TODO", "a", priority="P2")
    make_sp(tmp_path, "p/sp/TODO", "b", priority="P1")
    sps = sp_list.collect(tmp_path)
    assert [s.slug for s in sp_list.sort_sps(sps, "priority")] == ["b", "a"]
    assert [s.slug for s in sp_list.sort_sps(sps, "priority", reverse=True)] == ["a", "b"]


def test_ordenacao_created(tmp_path):
    make_sp(tmp_path, "p/sp/TODO", "novo", created="2026-10-10")
    make_sp(tmp_path, "p/sp/TODO", "velho", created="2026-10-01")
    sps = sp_list.collect(tmp_path)
    assert [s.slug for s in sp_list.sort_sps(sps, "created")] == ["velho", "novo"]


def test_main_filtros_e_resumo(tmp_path, capsys):
    make_sp(tmp_path, "atlas/sp/TODO", "a", project="atlas")
    make_sp(tmp_path, "kaizen-core/sp/Doing", "b", status="Doing", project="kaizen-core")
    make_sp(tmp_path, "atlas/sp/Doing", "c", status="Done", project="atlas")
    assert sp_list.main(["--root", str(tmp_path), "--flat", "--project", "atlas", "--status", "todo"]) == 0
    out = capsys.readouterr().out
    rows = [line.split()[-1] for line in out.splitlines()[1:-1]]
    assert rows == ["a"]
    assert out.strip().splitlines()[-1] == "1 TODO, 0 Doing, 0 avisos"


def test_main_resumo_com_aviso(tmp_path, capsys):
    make_sp(tmp_path, "atlas/sp/TODO", "a", project="atlas")
    make_sp(tmp_path, "atlas/sp/Doing", "c", status="Done", project="atlas")
    sp_list.main(["--root", str(tmp_path), "--flat"])
    assert capsys.readouterr().out.strip().splitlines()[-1] == "1 TODO, 1 Doing, 1 aviso"


def test_sp_malformado_ignorado_com_aviso(tmp_path, capsys):
    bad = tmp_path / "p" / "sp" / "TODO" / "bad.md"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"\xff\xfe\x00 nao utf8")
    make_sp(tmp_path, "p/sp/TODO", "ok")
    assert sp_list.main(["--root", str(tmp_path), "--flat"]) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines()[1].endswith(" ok")
    assert "bad.md" in captured.err


def program(tmp_path):
    make_sp(tmp_path, "atlas/sp/TODO", "mae", project="atlas", kind="program", priority="P2")
    make_sp(tmp_path, "atlas/sp/Done", "a", status="Done", project="atlas", parent="mae")
    make_sp(tmp_path, "atlas/sp/Doing", "b", status="Doing", project="atlas", parent="mae", depends_on=["a"], priority="P1")
    make_sp(tmp_path, "atlas/sp/TODO", "c", project="atlas", parent="mae", depends_on=["a", "b"])
    make_sp(tmp_path, "atlas/sp/TODO", "solto", project="atlas")
    return sp_list.collect(tmp_path, include_done=True)


def test_collect_le_parent_depends_on_e_kind(tmp_path):
    by_slug = {s.slug: s for s in program(tmp_path)}
    assert by_slug["c"].parent == "mae"
    assert by_slug["c"].depends_on == ["a", "b"]
    assert by_slug["mae"].kind == "program"
    assert by_slug["solto"].parent == "" and by_slug["solto"].depends_on == []


def test_build_tree_agrupa_filhos_e_deps_por_cumprir(tmp_path):
    groups, loose = sp_list.build_tree(program(tmp_path))
    assert [m.slug for m, _ in groups] == ["mae"]
    children = groups[0][1]
    assert [(sp.slug, unmet) for sp, unmet in children] == [("a", []), ("b", []), ("c", ["b"])]
    assert [sp.slug for sp in loose] == ["solto"]


def test_build_tree_mae_so_com_kind_program_sem_filhos(tmp_path):
    make_sp(tmp_path, "atlas/sp/TODO", "vazio", project="atlas", kind="program")
    groups, loose = sp_list.build_tree(sp_list.collect(tmp_path, include_done=True))
    assert [(m.slug, c) for m, c in groups] == [("vazio", [])]
    assert loose == []


def test_main_agrupa_filhos_sob_a_mae_por_omissao(tmp_path, capsys):
    program(tmp_path)
    assert sp_list.main(["--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out.splitlines()
    mae = next(i for i, line in enumerate(out) if " mae " in line)
    assert "0/3 feitos" not in out[mae] and "1/3 feitos" in out[mae]
    assert "├─ b" in out[mae + 1] and "Doing" in out[mae + 1] and "P1" in out[mae + 1]
    assert "└─ c" in out[mae + 2] and "aguarda: b" in out[mae + 2]
    assert not any("─ a" in line for line in out)  # Done só com --all
    assert any(line.rstrip().endswith("atlas") and " solto " in line + " " for line in out)
    assert out[-1] == "3 TODO, 1 Doing, 0 avisos"


def test_main_tree_e_sinonimo_do_predefinido(tmp_path, capsys):
    program(tmp_path)
    sp_list.main(["--root", str(tmp_path)])
    base = capsys.readouterr().out
    sp_list.main(["--root", str(tmp_path), "--tree"])
    assert capsys.readouterr().out == base


def test_main_all_mostra_done(tmp_path, capsys):
    program(tmp_path)
    sp_list.main(["--root", str(tmp_path), "--all"])
    out = capsys.readouterr().out
    assert any("├─ a" in line and "Done" in line for line in out.splitlines())


def test_main_flat_nao_agrupa(tmp_path, capsys):
    program(tmp_path)
    sp_list.main(["--root", str(tmp_path), "--flat"])
    out = capsys.readouterr().out.splitlines()
    assert out[0].split() == ["#", "Estado", "Prio", "Criado", "Projeto", "Slug"]
    assert "aguarda" not in " ".join(out)


def test_tree_marca_mae_pronta_para_fechar(tmp_path):
    groups, _ = sp_list.build_tree(program(tmp_path))
    mother, kids = groups[0]
    done_kids = [(dataclasses.replace(sp, status="Done"), []) for sp, _ in kids]
    assert "pronto para fechar" in sp_list.render_tree([(mother, done_kids)], [], lambda sp: True)
    assert "pronto para fechar" not in sp_list.render_tree(groups, [], lambda sp: True)
