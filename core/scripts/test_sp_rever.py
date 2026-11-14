import http.client
import json
import re
import threading
from pathlib import Path

import pytest
from sp_carregar import carregar

sr = carregar(Path(__file__).resolve().parent / "sp-rever.py", "sp_rever", registar=False, fresco=True)

PROVAS = {
    "slug": "a-2026-11-13",
    "objetivo": "Fazer <b>A</b>",
    "feito": ["item um", "item dois"],
    "gates": [{"cmd": "pytest -q", "rc": 0, "tail": "ok"}, {"cmd": "lint", "rc": 1, "tail": "erro"}],
    "criterios": {"cumpridos": ["c1"], "por_cumprir": ["c2"]},
    "decisoes_auto": ["escolhi X"],
    "experimentar": ["python x.py"],
    "reverter": ["git revert abc"],
    "pr": "https://github.com/o/r/pull/1",
    "imagens": [{"ficheiro": "d.svg", "legenda": "antes", "tipo": "diagrama"}],
}


def sp_md(slug, date="2026-11-13", updated="2026-11-13T19:00:00Z", project="kz"):
    return f"---\nstatus: Done\nslug: {slug}\ndate: {date}\nupdated: {updated}\nproject: {project}\n---\n# SP\n"


@pytest.fixture
def raiz(tmp_path):
    root = tmp_path / "proj"
    done = root / "kz" / "sp" / "Done"
    done.mkdir(parents=True)
    (done / "a-2026-11-13.md").write_text(sp_md("a-2026-11-13", updated="2026-11-13T19:00:00Z"), encoding="utf-8")
    (done / "b-2026-11-14.md").write_text(sp_md("b-2026-11-14", date="2026-11-14", updated="2026-11-14T10:00:00Z"), encoding="utf-8")
    (done / "velho-2026-10-01.md").write_text(sp_md("velho-2026-10-01", date="2026-10-01"), encoding="utf-8")
    pack = root / "kz" / "sp" / "proofs" / "a-2026-11-13"
    pack.mkdir(parents=True)
    (pack / "provas.json").write_text(json.dumps(PROVAS), encoding="utf-8")
    (pack / "d.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    return root


@pytest.fixture
def estado(tmp_path):
    return tmp_path / "sp-revisao.json"


def test_por_rever_ordem_e_filtro_de_data(raiz, estado):
    r = sr.por_rever(raiz, estado)
    assert [c["slug"] for c in r] == ["a-2026-11-13", "b-2026-11-14"]


def test_por_rever_exclui_revistos_e_conta_pendente(raiz, estado):
    sr.gravar_veredicto("a-2026-11-13", "ok", "", estado, raiz=raiz)
    assert [c["slug"] for c in sr.por_rever(raiz, estado)] == ["b-2026-11-14"]
    sr.gravar_veredicto("a-2026-11-13", "pendente", "", estado, raiz=raiz)
    assert len(sr.por_rever(raiz, estado)) == 2


def test_cartao_le_provas_e_cai_para_minimo(raiz, estado):
    a, b = sr.por_rever(raiz, estado)
    assert a["provas"]["objetivo"].startswith("Fazer")
    assert b["provas"] == {}


def test_gravar_veredicto_valida(raiz, estado):
    with pytest.raises(ValueError):
        sr.gravar_veredicto("a-2026-11-13", "talvez", "", estado, raiz=raiz)
    with pytest.raises(ValueError):
        sr.gravar_veredicto("../x", "ok", "", estado, raiz=raiz)
    with pytest.raises(ValueError):
        sr.gravar_veredicto("nao-existe", "ok", "", estado, raiz=raiz)
    with pytest.raises(ValueError):
        sr.gravar_veredicto("a-2026-11-13", "ajustar", "x" * 5000, estado, raiz=raiz)


def test_gravar_grava_campos_e_devolve_anterior(raiz, estado):
    ant = sr.gravar_veredicto("a-2026-11-13", "ajustar", "mexe nisto", estado, raiz=raiz)
    assert ant is None
    d = json.loads(estado.read_text(encoding="utf-8"))["a-2026-11-13"]
    assert d["estado"] == "ajustar" and d["texto"] == "mexe nisto" and re.match(r"\d{4}-\d\d-\d\d", d["data"])
    ant2 = sr.gravar_veredicto("a-2026-11-13", "ok", "", estado, raiz=raiz)
    assert ant2["estado"] == "ajustar"


def test_pagina_escapa_e_nao_so_cor(raiz, estado):
    html = sr.pagina(sr.por_rever(raiz, estado), "tok")
    assert "<b>A</b>" not in html and "&lt;b&gt;A&lt;/b&gt;" in html
    assert "PASSOU" in html and "FALHOU" in html
    assert "data:image/svg+xml;base64," in html
    assert "https://github.com/o/r/pull/1" in html
    assert "escolhi X" in html and "prefers-color-scheme" in html
    assert "http://" not in html.replace("http://www.w3.org", "")  # sem CDN


def test_pagina_ignora_pr_nao_http(raiz, estado):
    cs = sr.por_rever(raiz, estado)
    cs[0]["provas"]["pr"] = "javascript:alert(1)"
    assert "javascript:" not in sr.pagina(cs, "t")


def test_imagem_fora_do_pacote_ignorada(raiz, estado):
    cs = sr.por_rever(raiz, estado)
    cs[0]["provas"]["imagens"] = [{"ficheiro": "../../../../x.svg", "legenda": "z"}]
    assert "data:image" not in sr.pagina(cs, "t")


def test_pagina_20_cartoes_rapida(raiz, estado):
    import time
    cs = sr.por_rever(raiz, estado) * 10
    t = time.time()
    sr.pagina(cs, "t")
    assert time.time() - t < 1


def test_teclado_no_html(raiz, estado):
    html = sr.pagina(sr.por_rever(raiz, estado), "t")
    for k in ("'j'", "'k'", "'o'", "'a'", "'r'", "'u'", "'?'", "'q'", "Enter", "Escape", "ctrlKey"):
        assert k in html


@pytest.fixture
def srv(raiz, estado):
    s = sr.criar_servidor(0, "tok", raiz, estado)
    porta = s.server_address[1]
    t = threading.Thread(target=sr.servir, args=(s,), kwargs={"ocioso": 30}, daemon=True)
    t.start()
    yield porta, estado
    s.fechar = True
    t.join(3)
    s.server_close()


def req(porta, metodo, caminho, corpo=None, host=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=5)
    h = {"Host": host or f"127.0.0.1:{porta}"}
    b = None
    if corpo is not None:
        b = json.dumps(corpo)
        h["Content-Type"] = "application/json"
    c.request(metodo, caminho, b, h)
    r = c.getresponse()
    return r.status, r.read().decode("utf-8")


def test_servidor_so_loopback(srv):
    porta, _ = srv
    assert sr.criar_servidor(0, "x", Path("."), Path("e.json")).server_address[0] == "127.0.0.1"


def test_get_exige_token(srv):
    porta, _ = srv
    assert req(porta, "GET", "/")[0] == 403
    assert req(porta, "GET", "/?t=errado")[0] == 403
    st, body = req(porta, "GET", "/?t=tok")
    assert st == 200 and "<article" in body


def test_handler_tem_timeout_por_ligacao(srv):
    assert 0 < sr._handler().timeout <= 10


def test_host_estranho_recusado(srv):
    porta, _ = srv
    assert req(porta, "GET", "/?t=tok", host="evil.example")[0] == 403


def test_post_veredicto_fluxo(srv):
    porta, estado = srv
    st, body = req(porta, "POST", "/veredicto?t=tok", {"slug": "a-2026-11-13", "estado": "ok", "texto": ""})
    assert st == 200 and json.loads(body)["estado"] == "ok"
    assert json.loads(estado.read_text(encoding="utf-8"))["a-2026-11-13"]["estado"] == "ok"


def test_post_recusa_token_slug_estado_e_tamanho(srv):
    porta, estado = srv
    ok = {"slug": "a-2026-11-13", "estado": "ok", "texto": ""}
    assert req(porta, "POST", "/veredicto?t=x", ok)[0] == 403
    assert req(porta, "POST", "/veredicto?t=tok", {**ok, "slug": "outro"})[0] == 400
    assert req(porta, "POST", "/veredicto?t=tok", {**ok, "estado": "pendente"})[0] == 400
    assert req(porta, "POST", "/veredicto?t=tok", {**ok, "texto": "x" * 20000})[0] in (400, 413)
    assert not estado.exists()


def test_desfazer_restaura(srv):
    porta, estado = srv
    req(porta, "POST", "/veredicto?t=tok", {"slug": "a-2026-11-13", "estado": "ajustar", "texto": "t"})
    st, body = req(porta, "POST", "/desfazer?t=tok", {})
    assert st == 200
    assert "a-2026-11-13" not in json.loads(estado.read_text(encoding="utf-8"))
    assert req(porta, "POST", "/desfazer?t=tok", {})[0] == 409


def test_sair_termina(raiz, estado):
    s = sr.criar_servidor(0, "tok", raiz, estado)
    porta = s.server_address[1]
    t = threading.Thread(target=sr.servir, args=(s,), kwargs={"ocioso": 30}, daemon=True)
    t.start()
    assert req(porta, "POST", "/sair?t=tok", {})[0] == 200
    t.join(5)
    assert not t.is_alive()


def test_ocioso_termina(raiz, estado):
    s = sr.criar_servidor(0, "tok", raiz, estado)
    t = threading.Thread(target=sr.servir, args=(s,), kwargs={"ocioso": 0.3}, daemon=True)
    t.start()
    t.join(5)
    assert not t.is_alive()


def test_listar_e_json(raiz, estado, capsys):
    assert sr.main(["--listar", "--root", str(raiz), "--estado", str(estado)]) == 0
    out = capsys.readouterr().out
    assert "a-2026-11-13" in out and "b-2026-11-14" in out
    assert sr.main(["--listar", "--json", "--root", str(raiz), "--estado", str(estado)]) == 0
    d = json.loads(capsys.readouterr().out)
    assert [x["slug"] for x in d] == ["a-2026-11-13", "b-2026-11-14"] and "pr" in d[0]


def test_hook_uma_linha_ou_nada(raiz, estado, capsys):
    assert sr.main(["--hook", "--root", str(raiz), "--estado", str(estado)]) == 0
    assert capsys.readouterr().out.strip() == "2 SPs por rever: /rever"
    sr.gravar_veredicto("a-2026-11-13", "ok", "", estado, raiz=raiz)
    sr.gravar_veredicto("b-2026-11-14", "ok", "", estado, raiz=raiz)
    assert sr.main(["--hook", "--root", str(raiz), "--estado", str(estado)]) == 0
    assert capsys.readouterr().out == ""


def test_hook_nunca_falha(tmp_path, capsys):
    assert sr.main(["--hook", "--root", str(tmp_path / "nada"), "--estado", str(tmp_path / "x.json")]) == 0
    estado = tmp_path / "mau.json"
    estado.write_text("{lixo", encoding="utf-8")
    assert sr.main(["--hook", "--root", str(tmp_path), "--estado", str(estado)]) == 0


def test_diaria_lista_fechados_com_estado(raiz, estado):
    sr.gravar_veredicto("a-2026-11-13", "ajustar", "", estado, raiz=raiz)
    linhas = sr.diaria_linhas("2026-11-13", raiz, estado)
    assert len(linhas) == 1 and "a-2026-11-13" in linhas[0] and "ajustar" in linhas[0]
    assert sr.diaria_linhas("2026-11-14", raiz, estado)[0].count("pendente") == 1
    assert sr.diaria_linhas("2026-01-01", raiz, estado) == []
