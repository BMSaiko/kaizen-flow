"""Testes de scripts/da-stop.py: tentativas por perfil e relatório de paragem."""
import sys
from pathlib import Path
from sp_carregar import carregar  # noqa: E402

ds = carregar(Path(__file__).with_name("da-stop.py"), "da_stop", fresco=True)


def sp(tmp_path, front=""):
    p = tmp_path / "sp.md"
    p.write_text(f"---\nslug: x\n{front}---\n# SP\n", encoding="utf-8")
    return p


def test_defeito_normal_2_tentativas(tmp_path):
    assert ds.limites(sp(tmp_path)) == (2, ["gate-falha", "ficheiro-fora-de-escopo"])


def test_cauteloso_1_tentativa(tmp_path):
    assert ds.limites(sp(tmp_path, "perfil: cauteloso\n"))[0] == 1


def test_autonomo_so_gate_falha(tmp_path):
    assert ds.limites(sp(tmp_path, "perfil: autonomo\n")) == (2, ["gate-falha"])


def test_override_max_tentativas_e_parar_se(tmp_path):
    assert ds.limites(sp(tmp_path, "max_tentativas: 4\nparar_se: [custo]\n")) == (4, ["custo"])


def test_decide_continua_ate_ao_limite(tmp_path):
    p = sp(tmp_path)
    assert ds.decide(p, 1) == "tentar"
    assert ds.decide(p, 2) == "parar"


def test_decide_sem_gate_falha_na_lista_nunca_para_por_tentativas(tmp_path):
    assert ds.decide(sp(tmp_path, "parar_se: [custo]\n"), 9) == "tentar"


def test_relatorio_formato_fixo():
    r = ds.relatorio("3.2", 2, "teste vermelho", "ler o log e corrigir")
    assert r.splitlines() == [
        "## Paragem DA",
        "- Passo: 3.2",
        "- Tentativas: 2",
        "- Causa: teste vermelho",
        "- Próximo passo: ler o log e corrigir",
    ]


def test_main_rc_e_relatorio(tmp_path, capsys):
    p = sp(tmp_path)
    assert ds.main([str(p), "--passo", "1", "--tentativas", "1", "--causa", "c"]) == 0
    assert ds.main([str(p), "--passo", "1", "--tentativas", "2", "--causa", "c", "--proximo", "n"]) == 1
    assert "## Paragem DA" in capsys.readouterr().out
