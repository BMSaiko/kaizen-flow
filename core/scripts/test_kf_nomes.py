"""Testes de kf_nomes.py: nome canónico de painéis, registo nome→pane, `heimdall` reservado, poda e atomicidade."""
import json

import pytest

import kf_nomes as kn


@pytest.fixture
def raiz(tmp_path):
    return tmp_path / "estado"


SB = "/home/x/Second Brain"


def test_nome_basico_papel_slug():
    assert kn.nome_painel("sp", "Meu-SP_1", []) == "sp-meu-sp-1"


def test_nome_colisao_sufixo():
    assert kn.nome_painel("sp", "a", ["sp-a"]) == "sp-a-2"
    assert kn.nome_painel("sp", "a", ["sp-a", "sp-a-2"]) == "sp-a-3"


def test_nome_max_48_chars():
    n = kn.nome_painel("autor", "x" * 100, [])
    assert len(n) <= 48 and n.startswith("autor-")


def test_nome_max_48_com_sufixo():
    base = kn.nome_painel("sp", "x" * 100, [])
    n = kn.nome_painel("sp", "x" * 100, [base])
    assert len(n) <= 48 and n.endswith("-2") and n != base


@pytest.mark.parametrize("papel", ["", "outro", "heimdall", "SP"])
def test_papel_invalido(papel):
    with pytest.raises(ValueError):
        kn.nome_painel(papel, "a", [])


@pytest.mark.parametrize("slug", ["", "---", "çãé"])
def test_slug_sem_caracteres_validos(slug):
    with pytest.raises(ValueError):
        kn.nome_painel("sp", slug, [])


def test_registar_e_resolver(raiz):
    kn.registar("sp-a", "herdr", "w1:p2", "/wt", "sp", "a", root=raiz)
    e = kn.resolver("sp-a", root=raiz)
    assert e["pane"] == "w1:p2" and e["backend"] == "herdr" and e["papel"] == "sp" and e["slug"] == "a" and e["cwd"] == "/wt"
    assert e["criado"]
    assert kn.resolver("nao-existe", root=raiz) is None


def test_registar_nome_invalido(raiz):
    with pytest.raises(ValueError):
        kn.registar("SP A", "herdr", "1", "/wt", "sp", "a", root=raiz)


def test_registar_duplicado_outro_pane_recusa(raiz):
    kn.registar("sp-a", "herdr", "1", "/wt", "sp", "a", root=raiz)
    with pytest.raises(ValueError):
        kn.registar("sp-a", "herdr", "2", "/wt", "sp", "a", root=raiz)


def test_registar_mesmo_pane_idempotente(raiz):
    kn.registar("sp-a", "herdr", "1", "/wt", "sp", "a", root=raiz)
    kn.registar("sp-a", "herdr", "1", "/wt", "sp", "a", root=raiz)
    assert len(kn.listar(root=raiz)) == 1


def test_poda_panes_mortos_na_leitura(raiz):
    kn.registar("sp-a", "herdr", "1", "/wt", "sp", "a", root=raiz)
    kn.registar("sp-b", "herdr", "2", "/wt", "sp", "b", root=raiz)
    assert [e["nome"] for e in kn.listar(vivos={"2"}, root=raiz)] == ["sp-b"]
    assert kn.resolver("sp-a", vivos={"2"}, root=raiz) is None
    # a poda persiste
    assert [e["nome"] for e in kn.listar(root=raiz)] == ["sp-b"]


def test_nome_sobrevive_enquanto_pane_existe(raiz):
    kn.registar("sp-a", "herdr", "1", "/wt", "sp", "a", root=raiz)
    assert kn.resolver("sp-a", vivos={"1"}, root=raiz)["pane"] == "1"


def test_reabrir_mesmo_slug_recupera_nome(raiz):
    kn.registar("sp-a", "herdr", "1", "/wt", "sp", "a", root=raiz)
    # pane morreu: poda; o nome volta a estar livre e é o mesmo
    kn.listar(vivos=set(), root=raiz)
    existentes = [e["nome"] for e in kn.listar(root=raiz)]
    assert kn.nome_painel("sp", "a", existentes) == "sp-a"


def test_remover(raiz):
    kn.registar("sp-a", "herdr", "1", "/wt", "sp", "a", root=raiz)
    assert kn.remover("sp-a", root=raiz) is True
    assert kn.remover("sp-a", root=raiz) is False
    assert kn.listar(root=raiz) == []


def test_heimdall_so_no_cwd_do_second_brain(raiz):
    with pytest.raises(ValueError, match="heimdall"):
        kn.registar("heimdall", "herdr", "1", "/outro", "livre", "x", root=raiz, raiz_sb=SB)
    kn.registar("heimdall", "herdr", "1", SB, "livre", "heimdall", root=raiz, raiz_sb=SB)
    assert kn.resolver("heimdall", root=raiz)["pane"] == "1"


def test_heimdall_outro_pane_falha(raiz):
    kn.registar("heimdall", "herdr", "1", SB, "livre", "heimdall", root=raiz, raiz_sb=SB)
    with pytest.raises(ValueError, match="heimdall"):
        kn.registar("heimdall", "herdr", "2", SB, "livre", "heimdall", root=raiz, raiz_sb=SB)


def test_remover_heimdall_recusado(raiz):
    kn.registar("heimdall", "herdr", "1", SB, "livre", "heimdall", root=raiz, raiz_sb=SB)
    with pytest.raises(PermissionError, match="heimdall"):
        kn.remover("heimdall", root=raiz)
    assert kn.resolver("heimdall", root=raiz)


def test_detetar_heimdall_pelo_cwd(raiz):
    vivos = {"1": "/x", "2": SB}
    assert kn.detetar_heimdall("herdr", vivos, root=raiz, raiz_sb=SB) == "2"
    assert kn.resolver("heimdall", root=raiz)["pane"] == "2"
    assert kn.detetar_heimdall("herdr", {"1": "/x"}, root=raiz, raiz_sb=SB) is None


def test_ficheiro_corrompido_recria_e_avisa(raiz, capsys):
    raiz.mkdir(parents=True)
    (raiz / kn.FICHEIRO).write_text("{não json", encoding="utf-8")
    assert kn.listar(root=raiz) == []
    assert "corrompido" in capsys.readouterr().err
    kn.registar("sp-a", "herdr", "1", "/wt", "sp", "a", root=raiz)
    assert kn.resolver("sp-a", root=raiz)


def test_escrita_atomica_sem_tmp_e_json_valido(raiz):
    kn.registar("sp-a", "herdr", "1", "/wt", "sp", "a", root=raiz)
    assert [p.name for p in raiz.iterdir()] == [kn.FICHEIRO]
    json.loads((raiz / kn.FICHEIRO).read_text(encoding="utf-8"))


def test_escrita_falhada_nao_corrompe(raiz, monkeypatch):
    kn.registar("sp-a", "herdr", "1", "/wt", "sp", "a", root=raiz)
    antes = (raiz / kn.FICHEIRO).read_text(encoding="utf-8")

    def falha(*a, **k):
        raise OSError("disco cheio")

    monkeypatch.setattr(kn.os, "replace", falha)
    with pytest.raises(OSError):
        kn.registar("sp-b", "herdr", "2", "/wt", "sp", "b", root=raiz)
    assert (raiz / kn.FICHEIRO).read_text(encoding="utf-8") == antes
    assert [p.name for p in raiz.iterdir()] == [kn.FICHEIRO]


def test_ref_a_pane_nome_primeiro_depois_id(raiz):
    kn.registar("sp-a", "herdr", "7", "/wt", "sp", "a", root=raiz)
    assert kn.ref_a_pane("sp-a", {"7", "8"}, root=raiz) == "7"
    assert kn.ref_a_pane("8", {"7", "8"}, root=raiz) == "8"  # id opaco continua a funcionar
    assert kn.ref_a_pane("sp-x", {"7"}, root=raiz) == "sp-x"  # desconhecido passa tal e qual


def test_ref_nome_morto_nao_resolve(raiz):
    kn.registar("sp-a", "herdr", "7", "/wt", "sp", "a", root=raiz)
    assert kn.ref_a_pane("sp-a", {"8"}, root=raiz) == "sp-a"


def test_nome_de_pane(raiz):
    kn.registar("sp-a", "herdr", "7", "/wt", "sp", "a", root=raiz)
    assert kn.nome_de_pane("7", root=raiz) == "sp-a"
    assert kn.nome_de_pane("9", root=raiz) is None
