"""Testes de scripts/sp-validate.py (fixtures em ficheiros temporários)."""
import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("sp_validate", Path(__file__).with_name("sp-validate.py"))
sp_validate = importlib.util.module_from_spec(_spec)
sys.modules["sp_validate"] = sp_validate
_spec.loader.exec_module(sp_validate)

SECTIONS = [
    ("1. Role", "És o the agent."),
    ("2. Context", "- Repo: Second Brain."),
    ("3. Objective (single sentence)", "Fazer uma coisa."),
    ("4. Success criteria (verifiable)", "- [ ] RC 0."),
    ("5. Constraints / invariants", "- Must keep: X."),
    ("6. Seams (public interfaces to test / change)", "- `scripts/x.py`."),
    ("7. Steps (numbered, ordered)", "1. Fazer."),
    ("8. Done-when", "Testes verdes."),
]


def build(status="TODO", drop=None, no_priority=False, empty=None, modo=None, extra=()):
    fm = ["---", f"status: {status}", "created: 2026-10-18T00:00:00Z", "updated: 2026-10-18T00:00:00Z",
          "phase: SP", "slug: abc", "date: 2026-10-18", "project: atlas"]
    if not no_priority:
        fm.append("priority: P2")
    if modo:
        fm.append(f"modo: {modo}")
    fm += list(extra)
    fm.append("---")
    body = ["# Super Prompt - abc", ""]
    for title, text in SECTIONS:
        if title.startswith(f"{drop}."):
            continue
        body += [f"## {title}", "" if title.startswith(f"{empty}.") else text, ""]
    return "\n".join(fm + body)


def test_sp_valido_nao_tem_erros():
    assert sp_validate.validate(build(), folder="TODO") == []


def test_sem_seccao_5_nomeia_a_seccao():
    errors = sp_validate.validate(build(drop=5), folder="TODO")
    assert len(errors) == 1 and "5." in errors[0]


def test_sem_priority_nomeia_o_campo():
    errors = sp_validate.validate(build(no_priority=True), folder="TODO")
    assert len(errors) == 1 and "priority" in errors[0]


def test_status_diferente_da_pasta():
    errors = sp_validate.validate(build(status="Doing"), folder="TODO")
    assert len(errors) == 1 and "status" in errors[0] and "TODO" in errors[0]


def test_seccao_vazia():
    errors = sp_validate.validate(build(empty=8), folder="TODO")
    assert len(errors) == 1 and "8." in errors[0] and "vazia" in errors[0]


def test_modo_ausente_ou_valido_nao_tem_erros():
    assert sp_validate.validate(build(modo="auto"), folder="TODO") == []
    assert sp_validate.validate(build(modo="manual"), folder="TODO") == []


def test_modo_invalido_nomeia_o_campo():
    errors = sp_validate.validate(build(modo="semi"), folder="TODO")
    assert len(errors) == 1 and "modo" in errors[0] and "auto|manual" in errors[0]


def test_sem_frontmatter():
    errors = sp_validate.validate("# só corpo\n", folder=None)
    assert any("frontmatter" in e for e in errors)


def test_folder_none_nao_compara_status():
    assert sp_validate.validate(build(status="Doing"), folder=None) == []


def test_cli_rc0_e_rc1_com_lista(tmp_path, capsys):
    ok = tmp_path / "atlas" / "sp" / "TODO" / "ok.md"
    ok.parent.mkdir(parents=True)
    ok.write_text(build(), encoding="utf-8")
    bad = tmp_path / "atlas" / "sp" / "TODO" / "bad.md"
    bad.write_text(build(drop=5, no_priority=True), encoding="utf-8")
    assert sp_validate.main([str(ok)]) == 0
    assert sp_validate.main([str(bad)]) == 1
    err = capsys.readouterr().err
    assert "5." in err and "priority" in err


@pytest.mark.parametrize("extra", [
    ["commit: auto", "push: nunca", "pr: nunca"],
    ["commit: pergunta", "push: auto", "pr: auto"],
    ["restricoes: pasta X intocável"],
])
def test_autorizacoes_validas(extra):
    assert sp_validate.validate(build(extra=extra), folder="TODO") == []


@pytest.mark.parametrize("extra,fragment", [
    (["push: sim"], "push"),
    (["commit: nunca", "push: auto"], "commit"),
    (["commit: auto", "push: pergunta", "pr: auto"], "push"),
])
def test_autorizacoes_invalidas(extra, fragment):
    errors = sp_validate.validate(build(extra=extra), folder="TODO")
    assert len(errors) == 1 and fragment in errors[0]


GATES = ["gates:", "  - cmd: python -I scripts/test_sp_list.py", "    timeout: 60", "  - cmd: npm test"]


def test_gates_validos_passam():
    assert sp_validate.validate(build(extra=GATES + ["prova: python -I scripts/x.py"]), "TODO") == []


@pytest.mark.parametrize("gates, msg", [
    (["gates:", "  - cmd:"], "vazio"),
    (["gates:", "  - cmd: npm test", "  - cmd: npm test"], "duplicado"),
    (["gates:", "  - cmd: git reset --hard"], "proibido"),
    (["gates:", "  - cmd: cat .env.local"], "proibido"),
])
def test_gates_invalidos_dao_erro(gates, msg):
    assert any(msg in e for e in sp_validate.validate(build(extra=gates), "TODO"))


def test_prova_vazia_da_erro():
    assert any("prova" in e for e in sp_validate.validate(build(extra=["prova:"]), "TODO"))


def test_prova_proibida_da_erro():
    assert any("prova proibida" in e for e in sp_validate.validate(build(extra=["prova: type .env"]), "TODO"))


def test_aviso_modo_auto_sem_gates():
    assert sp_validate.warnings(build(modo="auto"))
    assert not sp_validate.warnings(build(modo="auto", extra=GATES))
    assert not sp_validate.warnings(build(modo="manual"))
    assert sp_validate.validate(build(modo="auto"), "TODO") == []


@pytest.mark.parametrize("extra", [
    ["perfil: cauteloso"],
    ["perfil: normal", "max_tentativas: 3", "max_requests: 40", "parar_se: [gate-falha, custo]"],
    ["perfil: autonomo"] + GATES,
])
def test_perfil_valido(extra):
    assert sp_validate.validate(build(extra=extra), "TODO") == []


@pytest.mark.parametrize("extra,fragment", [
    (["perfil: ousado"], "perfil"),
    (["max_tentativas: 0"], "max_tentativas"),
    (["max_requests: muitos"], "max_requests"),
    (["parar_se: [gate-falha, sempre]"], "parar_se"),
    (["perfil: autonomo"], "gates"),
])
def test_perfil_invalido(extra, fragment):
    errors = sp_validate.validate(build(extra=extra), "TODO")
    assert len(errors) == 1 and fragment in errors[0]


def test_permitir_proibido_ou_vazio_e_rejeitado():
    base = "---\nstatus: TODO\ncreated: c\nupdated: u\nphase: SP\nslug: s\ndate: d\nproject: p\npriority: P2\n{}---\n"
    body = "".join(f"## {t}\n{c}\n" for t, c in SECTIONS)
    errs = sp_validate.validate(base.format("permitir: git reset --hard\n") + body)
    assert any("permitir" in e and "git reset --hard" in e for e in errs)
    assert any("permitir vazio" in e for e in sp_validate.validate(base.format("permitir:\n") + body))
    assert not any("permitir" in e for e in sp_validate.validate(base.format("permitir: npm test\n") + body))
