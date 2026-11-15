"""Testes de scripts/plan-validate.py (planos DP em ficheiros temporários)."""
import sys
from pathlib import Path
from sp_carregar import carregar  # noqa: E402

pv = carregar(Path(__file__).with_name("plan-validate.py"), "plan_validate", fresco=True)

HEAD = "---\nstatus: DRAFT\nproject: p\nscope-gate: Full\nresearch-brief: b.md\ncreated: 2026-10-31T10:00:00\n---\n\n# Plan: x\n\n## Phases\n"
TAIL = "\n## Risks\n- r | mitigação: m | gatilho: g\n\n## Out of Scope\n- nada\n"


def fase(n, done="obs", gate="`python -I scripts/test-fast.py`", risco="r1"):
    s = f"### {n}. Nome\n- **What:** w\n- **Scope:** s\n"
    if done:
        s += f"- **Done when:** {done}\n"
    if gate:
        s += f"- **Gate:** {gate}\n"
    if risco:
        s += f"- **Risco:** {risco}\n"
    return s


def plano(tmp_path, *fases, head=HEAD, tail=TAIL):
    p = tmp_path / "_PLAN_x.md"
    p.write_text(head + "\n".join(fases) + tail, encoding="utf-8")
    return p


def test_plano_bom_aceite(tmp_path):
    assert pv.validate(plano(tmp_path, fase(1), fase(2), fase(3))) == []


def test_fase_sem_gate_rejeitada(tmp_path):
    erros = pv.validate(plano(tmp_path, fase(1), fase(2, gate=None), fase(3)))
    assert any("fase 2" in e and "Gate" in e for e in erros)


def test_fase_sem_done_when_rejeitada(tmp_path):
    erros = pv.validate(plano(tmp_path, fase(1, done=None), fase(2), fase(3)))
    assert any("fase 1" in e and "Done when" in e for e in erros)


def test_fase_sem_risco_rejeitada(tmp_path):
    erros = pv.validate(plano(tmp_path, fase(1), fase(2, risco=None), fase(3)))
    assert any("fase 2" in e and "Risco" in e for e in erros)


def test_gate_vazio_ou_placeholder_rejeitado(tmp_path):
    erros = pv.validate(plano(tmp_path, fase(1, gate="TBD"), fase(2), fase(3)))
    assert any("fase 1" in e for e in erros)


def test_numero_de_fases_fora_de_2_a_7(tmp_path):
    assert any("fases" in e for e in pv.validate(plano(tmp_path, fase(1))))
    assert any("fases" in e for e in pv.validate(plano(tmp_path, *[fase(i) for i in range(1, 9)])))


def test_sem_frontmatter_ou_secao_risks(tmp_path):
    erros = pv.validate(plano(tmp_path, fase(1), fase(2), head="# Plan\n\n## Phases\n", tail=""))
    assert any("frontmatter" in e for e in erros)
    assert any("Risks" in e for e in erros)


def test_gates_extrai_comandos_para_o_sp(tmp_path):
    p = plano(tmp_path, fase(1), fase(2, gate="`python -I scripts/context-budget.py`"))
    assert pv.gates(p) == ["python -I scripts/test-fast.py", "python -I scripts/context-budget.py"]


def test_main_rc(tmp_path, capsys):
    assert pv.main([str(plano(tmp_path, fase(1), fase(2)))]) == 0
    assert pv.main([str(plano(tmp_path, fase(1, gate=None), fase(2)))]) == 1
    assert pv.main([str(plano(tmp_path, fase(1), fase(2))), "--gates"]) == 0
    assert "- cmd: python -I scripts/test-fast.py" in capsys.readouterr().out


def fase_scope(n, scope, nome="Nome"):
    return fase(n).replace("### %d. Nome" % n, "### %d. %s" % (n, nome)).replace("- **Scope:** s", "- **Scope:** %s" % scope)


def test_aviso_skeleton_em_plano_de_codigo(tmp_path):
    p = plano(tmp_path, fase_scope(1, "`scripts/x.py`"), fase_scope(2, "`scripts/y.py`"))
    assert pv.validate(p) == []  # aviso nunca é erro
    assert any("skeleton" in a for a in pv.avisos(p))


def test_sem_aviso_com_skeleton_ou_so_vault(tmp_path):
    com = plano(tmp_path, fase_scope(1, "`scripts/x.py`", nome="Skeleton fino"), fase_scope(2, "`scripts/y.py`"))
    vault = plano(tmp_path, fase_scope(1, "`knowledge/a.md`"), fase_scope(2, "`knowledge/b.md`"))
    assert pv.avisos(com) == [] and pv.avisos(vault) == []
