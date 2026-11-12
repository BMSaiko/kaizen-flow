"""Testes de scripts/kf_term_ls.py (`kaizen term ls`: painéis com SP, fase, estado e fila; só leitura)."""
import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

import kf_term_ls as ls
import painel_backend as pb
import sp_painel_estado as pe

T0 = datetime(2026, 11, 12, 10, 0, 0)


class Falso(pb.Backend):
    nome = "falso"
    interativo = False

    def __init__(self, vivos=None, erro=None):
        self.vivos = dict(vivos or {})
        self.erro = erro

    def abrir(self, cmd, cwd):
        raise AssertionError("ls é só leitura")

    def listar(self):
        if self.erro:
            raise self.erro
        return dict(self.vivos)

    def fechar(self, id):
        raise AssertionError("ls não fecha painéis")

    def ecra(self, id):
        return ""


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "filas"
    pe.criar_fila(programa="prog-a", ordem=["a1", "a2", "a3"], root=r, agora=T0)
    pe.criar_fila(programa="prog-b", ordem=["b1"], root=r, agora=T0)
    pe.transitar("a1", "a-correr", fila="prog-a", root=r, agora=T0, pane="7", fase="DA")
    pe.transitar("a2", "a-correr", fila="prog-a", root=r, agora=T0, pane="8", fase="gates")
    pe.transitar("a2", "pergunta", fila="prog-a", root=r, agora=T0)
    pe.transitar("b1", "a-correr", fila="prog-b", root=r, agora=T0, pane="9")
    return r


def _por_slug(rows):
    return {r["slug"]: r for r in rows}


def test_linhas_cruza_estado_e_backend(root):
    rows = _por_slug(ls.linhas(root, Falso({"7": "x", "8": "y", "9": "z"})))
    assert rows["a1"] == {"painel": "7", "slug": "a1", "fila": "prog-a", "fase": "DA", "estado": "a-correr",
                          "pergunta": None, "vivo": "vivo"}
    assert rows["a2"]["estado"] == "pergunta" and rows["a2"]["vivo"] == "vivo"


def test_painel_morto_marcado(root):
    rows = _por_slug(ls.linhas(root, Falso({"7": "x"})))
    assert rows["a1"]["vivo"] == "vivo"
    assert rows["a2"]["vivo"] == "morto"
    assert rows["b1"]["vivo"] == "morto"
    assert rows["a3"]["vivo"] is None


def test_ativo_sem_pane_registado_e_morto(root):
    pe.transitar("b1", "done", fila="prog-b", root=root, agora=T0)  # liberta uma vaga do teto
    pe.transitar("a3", "a-correr", fila="prog-a", root=root, agora=T0)
    assert _por_slug(ls.linhas(root, Falso()))["a3"]["vivo"] == "morto"


def test_pendente_sem_painel_nao_e_morto(root):
    pe.criar_fila(programa="prog-c", ordem=["c1"], root=root, agora=T0)
    r = _por_slug(ls.linhas(root, Falso()))["c1"]
    assert r["painel"] is None and r["vivo"] is None


def test_acabado_com_painel_fechado_nao_e_morto(root):
    pe.transitar("b1", "done", fila="prog-b", root=root, agora=T0)
    r = _por_slug(ls.linhas(root, Falso()))["b1"]
    assert r["painel"] == "9" and r["vivo"] is None


def test_filtro_fila(root):
    rows = ls.linhas(root, Falso({"9": "z"}), fila="prog-b")
    assert [r["slug"] for r in rows] == ["b1"]


def test_filtro_fila_desconhecida_vazio(root):
    assert ls.linhas(root, Falso(), fila="nao-existe") == []


def test_sem_backend_vivo_desconhecido(root):
    rows = ls.linhas(root, None)
    assert {r["vivo"] for r in rows} == {None}


def test_main_sem_backend_avisa_e_lista(root, capsys):
    assert ls.main([], root=root, backend=None, aviso="sem backend de teste") == 0
    c = capsys.readouterr()
    assert "sem backend de teste" in c.err
    assert "a1" in c.out and "a2" in c.out


def test_backend_com_erro_avisa_e_lista(root, capsys):
    assert ls.main([], root=root, backend=Falso(erro=pb.BackendError("boom"))) == 0
    c = capsys.readouterr()
    assert "boom" in c.err and "a1" in c.out


def test_backend_timeout_avisa_e_lista(root, capsys):
    b = Falso(erro=subprocess.TimeoutExpired("wezterm", 5))
    assert ls.main([], root=root, backend=b) == 0
    c = capsys.readouterr()
    assert "timeout" in c.err.lower() and "a1" in c.out


def test_texto_uma_linha_por_painel_com_cabecalho(root, capsys):
    assert ls.main([], root=root, backend=Falso({"7": "x", "9": "z"})) == 0
    linhas = capsys.readouterr().out.splitlines()
    assert linhas[0].split()[:5] == ["PAINEL", "SP", "FASE", "ESTADO", "FILA"]
    assert len(linhas) == 1 + 4
    a2 = next(l for l in linhas if " a2 " in l)
    assert "morto" in a2 and "pergunta" in a2 and "prog-a" in a2
    a1 = next(l for l in linhas if " a1 " in l)
    assert "morto" not in a1 and "DA" in a1


def test_json_contrato_estavel(root, capsys):
    assert ls.main(["--json"], root=root, backend=Falso({"7": "x"})) == 0
    dados = json.loads(capsys.readouterr().out)
    assert isinstance(dados, list) and len(dados) == 4
    for r in dados:
        assert list(r) == ["painel", "slug", "fila", "fase", "estado", "pergunta", "vivo"]


def test_main_fila_x(root, capsys):
    assert ls.main(["--fila", "prog-b", "--json"], root=root, backend=Falso({"9": "z"})) == 0
    assert [r["slug"] for r in json.loads(capsys.readouterr().out)] == ["b1"]


def test_sem_estado_lista_vazia_rc0(tmp_path, capsys):
    assert ls.main([], root=tmp_path / "nada", backend=Falso()) == 0
    assert "sem SPs" in capsys.readouterr().out
    assert ls.main(["--json"], root=tmp_path / "nada", backend=Falso()) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_json_ilegivel_nao_rebenta(root, capsys):
    (root / "prog-b" / "b1.json").write_text("{lixo", encoding="utf-8")
    assert ls.main(["--json"], root=root, backend=Falso()) == 0
    rows = _por_slug(json.loads(capsys.readouterr().out))
    assert rows["b1"]["estado"] == "ilegível" or rows["b1"]["estado"]


def test_so_leitura_nao_altera_ficheiros(root):
    antes = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    ls.main([], root=root, backend=Falso({"7": "x"}))
    ls.main(["--json"], root=root, backend=Falso())
    assert {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()} == antes


def test_argumento_invalido_rc2(root, capsys):
    with pytest.raises(SystemExit) as e:
        ls.main(["--nao-existe"], root=root, backend=Falso())
    assert e.value.code == 2
