"""Testes de scripts/kf_term_arranque.py (`kaizen term fila|michi`: seletor de SPs com preview e confirmação)."""
import io

import pytest

import kf_term_arranque as ar
import painel_backend as pb


class Falso(pb.Backend):
    nome = "falso"

    def __init__(self):
        self.titulos_postos = {}

    def abrir(self, cmd, cwd):
        raise AssertionError("o spawn é injetado")

    def listar(self):
        return {}

    def fechar(self, id):
        raise AssertionError("arrancar não fecha painéis")

    def ecra(self, id):
        return ""

    def titulo(self, id, texto):
        self.titulos_postos[id] = texto
        return True


def _sp(root, pasta, slug, extra="", corpo="## 1. Role\n\nFaz coisas.\n"):
    d = root / "proj" / "sp" / pasta
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text(
        f"---\nstatus: {pasta}\nslug: {slug}\nproject: proj\npriority: P2\ncreated: 2026-11-01\n{extra}---\n# SP {slug}\n\n{corpo}",
        encoding="utf-8")


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "vault"
    _sp(r, "Done", "feito")
    _sp(r, "TODO", "pronto", "depends_on: [feito]\nparent: mae\n")
    _sp(r, "Doing", "em-curso", "parent: mae\n")
    _sp(r, "TODO", "bloqueado", "depends_on: [pronto]\nparent: mae\n")
    _sp(r, "TODO", "solto")
    _sp(r, "TODO", "mae", "kind: program\n")
    return r


def _entrada(*respostas):
    it = iter(respostas)
    return lambda _="": next(it)


class Spawn:
    def __init__(self, id="11", erro=None):
        self.chamadas, self.id, self.erro = [], id, erro

    def __call__(self, modo, alvo):
        self.chamadas.append((modo, alvo))
        if self.erro:
            raise self.erro
        return self.id


def test_elegiveis_sem_maes_nem_bloqueados_nem_done(root):
    assert [s.slug for s in ar.elegiveis(root)] == ["em-curso", "pronto", "solto"]  # Doing primeiro


def test_programas_so_com_filhos_elegiveis(root):
    progs = ar.programas(root)
    assert [(m.slug, [f.slug for f in fs]) for m, fs in progs] == [("mae", ["em-curso", "pronto"])]


def test_preview_corta_e_marca_o_corte(root):
    sp = next(s for s in ar.elegiveis(root) if s.slug == "pronto")
    assert "Faz coisas." in ar.preview(sp.path, 30)
    assert "---" not in ar.preview(sp.path, 30).splitlines()[0]  # sem frontmatter
    curto = ar.preview(sp.path, 2)
    assert len(curto.splitlines()) <= 3 and "…" in curto


def test_escolher_por_numero_e_cancelar(root):
    ops = [(s.slug, s.path) for s in ar.elegiveis(root)]
    saida = io.StringIO()
    assert ar.escolher(ops, _entrada("2"), saida) == ops[1]
    assert "pronto" in saida.getvalue() and "Faz coisas." in saida.getvalue()  # preview do escolhido
    assert ar.escolher(ops, _entrada("q"), io.StringIO()) is None
    assert ar.escolher(ops, _entrada("9", ""), io.StringIO()) is None  # fora do intervalo, depois vazio: cancela
    assert ar.escolher([], _entrada(), io.StringIO()) is None


@pytest.mark.parametrize("resp,esperado", [("s", True), ("sim", True), ("y", True), ("", False), ("n", False), ("talvez", False)])
def test_confirmar_so_aceita_sim_explicito(resp, esperado):
    assert ar.confirmar("lançar?", _entrada(resp), io.StringIO()) is esperado


def test_comando_equivalente():
    assert ar.comando_equivalente("michi", "pronto") == "claude  # depois: /michi pronto"
    assert ar.comando_equivalente("fila", "mae") == "python -I scripts/sp-fila.py --programa mae"


def test_michi_confirmado_lanca_e_nomeia_pelo_slug(root, capsys):
    b, sp = Falso(), Spawn("42")
    rc = ar.main(["michi"], root=root, backend=b, spawn=sp, entrada=_entrada("2", "s"))
    assert rc == 0
    assert sp.chamadas == [("michi", "pronto")]
    assert b.titulos_postos == {"42": "pronto"}
    assert "42" in capsys.readouterr().out


def test_michi_cancelado_no_seletor_ou_na_confirmacao_nao_lanca(root):
    for respostas in (("q",), ("2", "n"), ("2", "")):
        sp = Spawn()
        assert ar.main(["michi"], root=root, backend=Falso(), spawn=sp, entrada=_entrada(*respostas)) == 0
        assert sp.chamadas == []


def test_michi_com_slug_ainda_pede_confirmacao(root):
    sp = Spawn()
    assert ar.main(["michi", "--slug", "solto"], root=root, backend=Falso(), spawn=sp, entrada=_entrada("n")) == 0
    assert sp.chamadas == []
    assert ar.main(["michi", "--slug", "solto"], root=root, backend=Falso(), spawn=sp, entrada=_entrada("s")) == 0
    assert sp.chamadas == [("michi", "solto")]


def test_michi_slug_inelegivel_recusa(root, capsys):
    sp = Spawn()
    assert ar.main(["michi", "--slug", "bloqueado", "--sim"], root=root, backend=Falso(), spawn=sp, entrada=_entrada()) == 2
    assert sp.chamadas == []
    assert "não elegível" in capsys.readouterr().err


def test_sim_e_a_confirmacao_explicita_sem_tty(root):
    sp = Spawn()
    assert ar.main(["michi", "--slug", "solto", "--sim"], root=root, backend=Falso(), spawn=sp, entrada=_entrada()) == 0
    assert sp.chamadas == [("michi", "solto")]


def test_fila_escolhe_programa_e_nomeia_fila(root):
    b, sp = Falso(), Spawn("7")
    assert ar.main(["fila"], root=root, backend=b, spawn=sp, entrada=_entrada("1", "s")) == 0
    assert sp.chamadas == [("fila", "mae")]
    assert b.titulos_postos == {"7": "fila-mae"}


def test_sem_backend_imprime_o_comando_e_nao_lanca(root, capsys):
    sp = Spawn()
    rc = ar.main(["michi", "--slug", "solto", "--sim"], root=root, backend=None, spawn=sp, entrada=_entrada(),
                 aviso_backend="sem painel: instala wezterm ou tmux")
    out = capsys.readouterr()
    assert rc == 0 and sp.chamadas == []
    assert "claude  # depois: /michi solto" in out.out and "sem painel" in out.err


def test_spawn_que_falha_da_rc_1_com_a_causa(root, capsys):
    sp = Spawn(erro=pb.BackendError("wezterm sem resposta"))
    assert ar.main(["michi", "--slug", "solto", "--sim"], root=root, backend=Falso(), spawn=sp, entrada=_entrada()) == 1
    assert "wezterm sem resposta" in capsys.readouterr().err


def test_sem_elegiveis_nao_pergunta_nada(tmp_path, capsys):
    vazio = tmp_path / "v"
    vazio.mkdir()
    assert ar.main(["michi"], root=vazio, backend=Falso(), spawn=Spawn(), entrada=_entrada()) == 0
    assert "sem SPs elegíveis" in capsys.readouterr().out


def test_titulo_que_falha_nao_desfaz_o_lancamento(root, capsys):
    class SemTitulo(Falso):
        def titulo(self, id, texto):
            raise pb.BackendError("sem separadores")

    sp = Spawn("5")
    assert ar.main(["michi", "--slug", "solto", "--sim"], root=root, backend=SemTitulo(), spawn=sp, entrada=_entrada()) == 0
    assert sp.chamadas == [("michi", "solto")] and "5" in capsys.readouterr().out
