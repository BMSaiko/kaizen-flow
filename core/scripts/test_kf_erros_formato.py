"""Testes de scripts/kf_erros.py: formato único das mensagens de erro (EC-NNN) e classificador de falhas do modelo.

Uso: python -m pytest scripts/test_kf_erros_formato.py -q
rc: o do pytest
"""
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sp_carregar import carregar

kf_erros = carregar(Path(__file__).with_name("kf_erros.py"), "kf_erros", fresco=True)

AGORA = datetime(2026, 11, 18, 10, 0, 0)


# --- formato -----------------------------------------------------------------

def test_formatar_tem_as_quatro_partes_e_o_ec_no_inicio():
    txt = kf_erros.formatar(kf_erros.Erro("EC-016", "limite de uso atingido", "o modelo recusou", "checkpoint intacto", "kaizen resume x"))
    linhas = txt.splitlines()
    assert len(linhas) == 4
    assert linhas[0] == "EC-016 O quê: limite de uso atingido"
    assert linhas[1].strip() == "Porquê: o modelo recusou"
    assert linhas[2].strip() == "Estado guardado: checkpoint intacto"
    assert linhas[3].strip() == "Próximo: kaizen resume x"


def test_erro_atalho_igual_a_formatar():
    a = kf_erros.erro("EC-010", "a", "b", "c", "d")
    assert a == kf_erros.formatar(kf_erros.Erro("EC-010", "a", "b", "c", "d"))


@pytest.mark.parametrize("ec", ["", "EC-1", "ec-010", "EC-0100", "UC-001", None, 16])
def test_ec_obrigatorio_e_bem_formado(ec):
    with pytest.raises(ValueError):
        kf_erros.Erro(ec, "a", "b", "c", "d")


@pytest.mark.parametrize("vazio", ["", "   ", None])
def test_partes_nao_vazias(vazio):
    for i in range(4):
        partes = ["a", "b", "c", "d"]
        partes[i] = vazio
        with pytest.raises(ValueError):
            kf_erros.Erro("EC-010", *partes)


def test_partes_multilinha_ficam_numa_linha():
    txt = kf_erros.erro("EC-010", "linha1\nlinha2", "x\r\ny", "z", "w")
    assert len(txt.splitlines()) == 4 and "linha1 linha2" in txt and "x y" in txt


def test_ecs_em_texto():
    assert kf_erros.ecs_em("a EC-016 e EC-060; UC-001 não; EC-1 não") == ["EC-016", "EC-060"]


texto_pt = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=80).filter(lambda s: s.strip())


@settings(max_examples=150, deadline=None)
@given(texto_pt, texto_pt, texto_pt, texto_pt, st.integers(min_value=0, max_value=999))
def test_hypothesis_formatar_sempre_quatro_linhas_e_reversivel(oque, porque, estado, proximo, n):
    ec = f"EC-{n:03d}"
    txt = kf_erros.formatar(kf_erros.Erro(ec, oque, porque, estado, proximo))
    linhas = txt.split("\n")
    assert len(linhas) == 4 and linhas[0].startswith(ec + " O quê: ")
    lido = kf_erros.ler(txt)
    assert lido is not None and lido.ec == ec
    for campo, original in (("oque", oque), ("porque", porque), ("estado", estado), ("proximo", proximo)):
        assert getattr(lido, campo) == kf_erros._uma_linha(original)


def test_hypothesis_acentos_preservados():
    txt = kf_erros.erro("EC-061", "ramo «agent/ação» não é o do SP", "çãõéà", "nada alterado", "git checkout agent/ação")
    assert "«agent/ação»" in txt and "çãõéà" in txt


def test_ler_texto_sem_formato_devolve_none():
    assert kf_erros.ler("erro: coisa") is None


# --- classificador -----------------------------------------------------------

def _cls(texto, rc=1, **kw):
    return kf_erros.classificar_falha(texto, rc, agora=AGORA, **kw)


def test_claude_limite_com_hora_pm():
    ec, motivo, retoma = _cls("Claude usage limit reached. Your limit will reset at 3pm (Europe/Lisbon).")
    assert ec == "EC-016" and "quota" in motivo
    assert retoma == "2026-11-18T15:00:00"


def test_claude_limite_resets_formato_novo_com_minutos():
    ec, _, retoma = _cls("5-hour limit reached ∙ resets 3:30pm\n/upgrade to increase your usage limit.")
    assert ec == "EC-016" and retoma == "2026-11-18T15:30:00"


def test_hora_ja_passada_vai_para_o_dia_seguinte():
    _, _, retoma = _cls("limit reached · resets 9am")
    assert retoma == "2026-11-19T09:00:00"


def test_claude_limite_epoch():
    ts = int(datetime(2026, 11, 18, 14, 0, 0).timestamp())
    ec, _, retoma = _cls(f"Claude AI usage limit reached|{ts}")
    assert ec == "EC-016" and retoma == "2026-11-18T14:00:00"


def test_codex_limite_try_again_in():
    ec, _, retoma = _cls("■ You've hit your usage limit. Upgrade to Pro (https://openai.com/chatgpt/pricing) or try again in 2 hours 5 minutes.")
    assert ec == "EC-016" and retoma == (AGORA + timedelta(hours=2, minutes=5)).isoformat(timespec="seconds")


def test_codex_limite_try_again_at():
    ec, _, retoma = _cls("You've hit your usage limit. Try again at 4:04 PM.")
    assert ec == "EC-016" and retoma == "2026-11-18T16:04:00"


@pytest.mark.parametrize("texto", [
    "API Error: 429 {\"type\":\"error\",\"error\":{\"type\":\"rate_limit_error\"}}",
    "API Error: 529 {\"type\":\"error\",\"error\":{\"type\":\"overloaded_error\",\"message\":\"Overloaded\"}}",
    "stream error: exceeded retry limit, last status: 429 Too Many Requests",
    "Rate limit reached for gpt-5 in organization",
])
def test_quota_sem_hora_usa_intervalo(texto):
    ec, _, retoma = _cls(texto, intervalo_min=20)
    assert ec == "EC-016" and retoma == (AGORA + timedelta(minutes=20)).isoformat(timespec="seconds")


@pytest.mark.parametrize("texto", [
    "API Error: Connection error. (getaddrinfo ENOTFOUND api.anthropic.com)",
    "Error: read ECONNRESET",
    "stream disconnected before completion: error sending request for url (https://chatgpt.com/backend-api/codex/responses)",
    "Request timed out.",
    "fatal: unable to access 'https://github.com/x/y.git/': Could not resolve host: github.com",
])
def test_rede(texto):
    ec, motivo, retoma = _cls(texto)
    assert ec == "EC-017" and "rede" in motivo and retoma is not None


@pytest.mark.parametrize("texto", [
    "OAuth token has expired. Please obtain a new token or refresh your existing token. · Please run /login",
    "Invalid API key · Please run /login",
    "Not logged in · Please run /login",
    "Your access token could not be refreshed. Please log out and sign in again (codex login).",
])
def test_sessao_expirada_sem_retoma_automatica(texto):
    ec, motivo, retoma = _cls(texto)
    assert ec == "EC-066" and "login" in motivo and retoma is None


@pytest.mark.parametrize("texto", [
    "", "Traceback ... KeyError: 'x'", "rc=1", "3 testes falharam (rate de sucesso 90%)",
    "a quota do disco está a 50%", "commit 4290abc", "Gerei 429 linhas de código",
])
def test_falha_generica_nao_e_classificada(texto):
    assert _cls(texto) is None


def test_so_olha_para_a_cauda():
    antigo = "Claude usage limit reached. resets 3pm\n" + "\n".join(f"linha {i}" for i in range(100))
    assert _cls(antigo) is None


def test_intervalo_por_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("KF_RETOMA_MIN", "45")
    _, _, retoma = _cls("Error: read ECONNRESET")
    assert retoma == (AGORA + timedelta(minutes=45)).isoformat(timespec="seconds")


@settings(max_examples=100, deadline=None)
@given(st.text(max_size=300), st.one_of(st.none(), st.integers(-5, 300)))
def test_hypothesis_classificador_nunca_levanta(texto, rc):
    r = kf_erros.classificar_falha(texto, rc, agora=AGORA)
    assert r is None or (re.fullmatch(r"EC-\d{3}", r[0]) and r[1])


def test_classificar_mede_menos_de_50ms():
    import time
    t = time.perf_counter()
    for _ in range(20):
        kf_erros.classificar_falha("x\n" * 2000 + "You've hit your usage limit. Try again at 4:04 PM.", 1, agora=AGORA)
    assert (time.perf_counter() - t) / 20 < 0.05


# --- contrato com o catálogo -------------------------------------------------

SCRIPTS_COM_EC = ("kf_erros.py", "kf_errlog.py", "sp-preflight.py", "sp-resume.py", "sp-fila.py", "sp-estado.py", "sp_vigia.py")


def _catalogo():
    return kf_erros.ecs_do_catalogo()


@pytest.mark.skipif(kf_erros.caminho_catalogo() is None, reason="sem docs/catalogo.json (vault sem KF_CATALOGO)")
def test_contrato_ecs_do_codigo_existem_no_catalogo():
    cat = _catalogo()
    aqui = Path(__file__).parent
    usados = {}
    for nome in SCRIPTS_COM_EC:
        p = aqui / nome
        if p.is_file():
            for ec in kf_erros.ecs_em(p.read_text(encoding="utf-8")):
                usados.setdefault(ec, nome)
    em_falta = {ec: f for ec, f in usados.items() if ec not in cat}
    assert usados and not em_falta, em_falta


@pytest.mark.skipif(kf_erros.caminho_catalogo() is None, reason="sem docs/catalogo.json (vault sem KF_CATALOGO)")
def test_contrato_ecs_do_modulo_existem():
    cat = _catalogo()
    assert set(kf_erros.ECS_USADOS) <= cat


def test_caminho_catalogo_por_env(tmp_path, monkeypatch):
    p = tmp_path / "c.json"
    p.write_text('{"edge_cases": [{"id": "EC-001"}, {"id": "EC-016"}]}', encoding="utf-8")
    monkeypatch.setenv("KF_CATALOGO", str(p))
    assert kf_erros.caminho_catalogo() == p
    assert kf_erros.ecs_do_catalogo() == {"EC-001", "EC-016"}


def test_catalogo_ilegivel_devolve_vazio(tmp_path, monkeypatch):
    p = tmp_path / "c.json"
    p.write_text("{", encoding="utf-8")
    monkeypatch.setenv("KF_CATALOGO", str(p))
    assert kf_erros.ecs_do_catalogo() == set()


def test_env_inexistente_cai_no_defeito(monkeypatch, tmp_path):
    monkeypatch.setenv("KF_CATALOGO", str(tmp_path / "nao.json"))
    c = kf_erros.caminho_catalogo()
    assert c is None or c.name == "catalogo.json"
    assert os.environ["KF_CATALOGO"].endswith("nao.json")


@pytest.mark.parametrize("valor,esperado", [
    (None, True), ("", True), ("lixo", True), ("2026-11-18T09:59:59", True), ("2026-11-18T10:00:00", True),
    ("2026-11-18T10:00:01", False), ("2026-11-18T10:00:00+00:00", True),
])
def test_ja_passou(valor, esperado):
    assert kf_erros.ja_passou(valor, agora=AGORA) is esperado
