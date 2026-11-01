"""Testes de scripts/sp-report.py (SP de exemplo em texto, sem git)."""
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("sp_report", Path(__file__).with_name("sp-report.py"))
sp_report = importlib.util.module_from_spec(_spec)
sys.modules["sp_report"] = sp_report
_spec.loader.exec_module(sp_report)

SP = """---
status: Done
slug: exemplo
gates:
  - cmd: python -I scripts/test-fast.py
    timeout: 120
  - cmd: python -I scripts/context-budget.py
    timeout: 60
---
# SP exemplo

## 4. Success criteria (verifiable)

- [x] feito
- [ ] por fazer

## Prova

- `proofs/exemplo.txt`: output real.

## Reflect

Reflect fase: o pytest deixou cache suja · patch em scripts/x.py · cwd.
Reflect DP: sem patch
"""

STAT = [" scripts/x.py | 10 +++++-----", " 1 file changed, 5 insertions(+), 5 deletions(-)"]


def test_report_tem_as_cinco_seccoes_fixas():
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT)
    for titulo in ("## Alterado", "## Verificado", "## Provas", "## Dificuldades", "## Em aberto"):
        assert titulo in out
    assert out.index("## Alterado") < out.index("## Verificado") < out.index("## Provas") < out.index("## Dificuldades") < out.index("## Em aberto")


def test_alterado_usa_o_diff_stat():
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT)
    assert "scripts/x.py | 10" in out


def test_verificado_lista_comandos_e_rc_dos_resultados():
    res = [{"cmd": "python -I scripts/test-fast.py", "rc": 0, "secs": 3}, {"cmd": "python -I scripts/context-budget.py", "rc": 1, "secs": 0}]
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT, gates=res)
    assert "`python -I scripts/test-fast.py` rc=0" in out
    assert "`python -I scripts/context-budget.py` rc=1" in out


def test_sem_resultados_nao_inventa_rc():
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT)
    assert "`python -I scripts/test-fast.py` rc=não corrido" in out
    assert "rc=0" not in out


def test_dificuldades_vem_das_linhas_reflect_com_causa():
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT)
    assert "pytest deixou cache suja" in out
    assert sp_report.dificuldades_ok(SP)


def test_dificuldades_vazia_e_marcada():
    sem = SP.replace("Reflect fase: o pytest deixou cache suja · patch em scripts/x.py · cwd.\n", "")
    out = sp_report.gerar(sem, "exemplo", diff_stat=STAT)
    assert not sp_report.dificuldades_ok(sem)
    assert "SEM DIFICULDADES REGISTADAS" in out


def test_em_aberto_lista_criterios_por_cumprir():
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT)
    assert "por fazer" in out
    assert "feito" not in out.split("## Em aberto")[1]


def test_provas_lista_a_seccao_prova():
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT)
    assert "proofs/exemplo.txt" in out
