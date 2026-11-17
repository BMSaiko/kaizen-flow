"""Testes de scripts/dr-check.py: 3 casos (pequena, média, vaga) + falhas."""
from pathlib import Path
from sp_carregar import carregar  # noqa: E402

dc = carregar(Path(__file__).with_name("dr-check.py"), "dr_check", fresco=True)

HEAD = "# Research Brief — t\n\n> **Scope Gate:** {gate}\n> **Orçamento:** {orc}\n\n## Síntese\n"
TAIL = "\n## Lacunas\n- nenhuma\n"


def brief(tmp_path, linhas, gate="Delta", orc="3 leituras, 2 greps, parou: alvo claro", tail=TAIL):
    p = tmp_path / "b.md"
    p.write_text(HEAD.format(gate=gate, orc=orc) + "\n".join(linhas) + tail, encoding="utf-8")
    return p


FONTES = ["- cai em `scripts/a.py:10`", "- respeitar `AGENTS.md:5`", "- risco `x/y.md:7`"]


def test_pequena_passa(tmp_path):
    assert dc.check(brief(tmp_path, FONTES, gate="Skipped")) == []


def test_media_passa(tmp_path):
    assert dc.check(brief(tmp_path, FONTES + [f"- facto {i} `f{i}.py:{i}`" for i in range(1, 15)], gate="Full")) == []


def test_vaga_sem_fontes_falha(tmp_path):
    erros = dc.check(brief(tmp_path, ["- algo vago", "- outra coisa"], gate="Full"))
    assert any("fontes" in e for e in erros)


def test_sintese_longa_falha(tmp_path):
    erros = dc.check(brief(tmp_path, FONTES + [f"- l{i}" for i in range(30)]))
    assert any("25" in e for e in erros)


def test_sem_orcamento_falha(tmp_path):
    erros = dc.check(brief(tmp_path, FONTES, orc=""))
    assert any("Orçamento" in e for e in erros)


def test_gate_invalido_falha(tmp_path):
    erros = dc.check(brief(tmp_path, FONTES, gate="Talvez"))
    assert any("Scope Gate" in e for e in erros)


def test_sem_sintese_falha(tmp_path):
    p = tmp_path / "b.md"
    p.write_text("# x\n\n> **Scope Gate:** Full\n> **Orçamento:** 1\n", encoding="utf-8")
    assert any("Síntese" in e for e in dc.check(p))
