"""Testes de scripts/kf_term_limpar.py (`kaizen term limpar|retomar`: limpeza com dry-run e reabertura de SPs em Doing)."""
import io
from datetime import datetime

import pytest

import kf_term_limpar as lp
import painel_backend as pb
import sp_painel_estado as pe

T0 = datetime(2026, 11, 12, 10, 0, 0)


class Falso(pb.Backend):
    nome = "falso"

    def __init__(self, vivos=()):
        self.vivos = {str(v): None for v in vivos}
        self.fechados, self.titulos_postos = [], {}

    def abrir(self, cmd, cwd):
        raise AssertionError("o spawn é injetado")

    def listar(self):
        return dict(self.vivos)

    def fechar(self, id):
        self.fechados.append(str(id))
        return self.vivos.pop(str(id), "x") != "x"

    def ecra(self, id):
        return ""

    def titulo(self, id, texto):
        self.titulos_postos[id] = texto
        return True


def _entrada(*respostas):
    it = iter(respostas)
    return lambda _="": next(it)


def _estado(root, fila, slug, estado, pane=None, worktree=None):
    campos = {k: v for k, v in (("pane", pane), ("worktree", worktree)) if v}
    if estado == "done":
        pe.transitar(slug, "a-correr", fila=fila, root=root, agora=T0, **campos)
        pe.transitar(slug, "done", fila=fila, root=root, agora=T0)
    elif estado != "pendente":
        pe.transitar(slug, estado, fila=fila, root=root, agora=T0, **campos)


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "filas"
    pe.criar_fila(programa="p", ordem=["ativo", "feito", "orfao", "sujo", "proprio", "pend"], root=r, agora=T0)
    _estado(r, "p", "ativo", "a-correr", pane="1")
    _estado(r, "p", "feito", "done", pane="2")
    _estado(r, "p", "orfao", "a-correr", pane="3")
    _estado(r, "p", "sujo", "done", pane="4", worktree="W")
    _estado(r, "p", "proprio", "done", pane="5")
    return r


def _acoes(root, vivos, proprio=None, suja=lambda w: w == "W"):
    acoes, prot = lp.planear(pe.filas(root), set(vivos), proprio, suja)
    return {(a["acao"], a["slug"]) for a in acoes}, {p["slug"]: p["motivo"] for p in prot}


def test_planear_fecha_done_limpo_e_marca_orfao(root):
    acoes, _ = _acoes(root, {"1", "2", "4", "5"})
    assert ("fechar-painel", "feito") in acoes
    assert ("estado-orfao", "orfao") in acoes


def test_planear_nunca_fecha_vivo_ativo_nem_worktree_suja_nem_proprio(root):
    acoes, prot = _acoes(root, {"1", "2", "4", "5"}, proprio="5")
    fechados = {s for a, s in acoes if a == "fechar-painel"}
    assert fechados == {"feito"}
    assert prot["ativo"] == "SP a-correr"
    assert "suja" in prot["sujo"]
    assert "onde corre" in prot["proprio"]


def test_planear_worktree_nao_verificada_protege(root):
    acoes, prot = _acoes(root, {"4"}, suja=lambda w: None)
    assert ("fechar-painel", "sujo") not in acoes
    assert "não verificada" in prot["sujo"]


def test_planear_so_remove_fila_toda_done_e_sem_protegidos(tmp_path):
    r = tmp_path / "filas"
    pe.criar_fila(programa="q", ordem=["x", "y"], root=r, agora=T0)
    _estado(r, "q", "x", "done", pane="8")
    _estado(r, "q", "y", "done")
    acoes, _ = _acoes(r, {"8"})
    assert ("remover-fila", None) in acoes and ("fechar-painel", "x") in acoes
    acoes, _ = _acoes(r, {"8"}, proprio="8")  # painel próprio protegido: a fila fica
    assert ("remover-fila", None) not in acoes


def test_planear_pendente_sem_painel_nao_faz_nada(root):
    acoes, prot = _acoes(root, set())
    assert not any(s == "pend" for _, s in acoes) and "pend" not in prot


def test_limpar_dry_run_nao_toca_em_nada(root):
    b, saida = Falso({"1", "2", "4", "5"}), io.StringIO()
    rc = lp.main(["limpar"], root=root, backend=b, saida=saida, proprio=None, suja=lambda w: w == "W")
    assert rc == 0 and b.fechados == []
    assert "fechar-painel" in saida.getvalue() and "dry-run" in saida.getvalue()
    assert pe.ler("p", "orfao", root=root)["estado"] == "a-correr"


def test_limpar_apply_confirmado_executa(root):
    b = Falso({"1", "2", "4", "5"})
    rc = lp.main(["limpar", "--apply"], root=root, backend=b, saida=io.StringIO(), proprio="5",
                 suja=lambda w: w == "W", entrada=_entrada("s"))
    assert rc == 0 and b.fechados == ["2"]
    assert pe.ler("p", "orfao", root=root)["estado"] == "bloqueado"
    assert pe.ler("p", "ativo", root=root)["estado"] == "a-correr"


def test_limpar_apply_cancelado_nao_faz_nada(root):
    b = Falso({"1", "2"})
    rc = lp.main(["limpar", "--apply"], root=root, backend=b, saida=io.StringIO(), proprio=None,
                 suja=lambda w: False, entrada=_entrada(""))
    assert rc == 0 and b.fechados == []
    assert pe.ler("p", "orfao", root=root)["estado"] == "a-correr"


def test_limpar_apply_sim_dispensa_pergunta(root):
    b = Falso({"1", "2"})
    rc = lp.main(["limpar", "--apply", "--sim"], root=root, backend=b, saida=io.StringIO(), proprio=None,
                 suja=lambda w: False, entrada=_entrada())
    assert rc == 0 and b.fechados == ["2"]


def test_limpar_sem_backend_avisa_e_nao_faz_nada(root, capsys):
    rc = lp.main(["limpar", "--apply", "--sim"], root=root, backend=None, aviso="sem wezterm", saida=io.StringIO())
    assert rc == 0 and "sem wezterm" in capsys.readouterr().err


def test_limpar_backend_a_falhar_nao_age(root, capsys):
    class Mau(Falso):
        def listar(self):
            raise pb.BackendError("boom")
    b = Mau()
    rc = lp.main(["limpar", "--apply", "--sim"], root=root, backend=b, saida=io.StringIO())
    assert rc == 0 and b.fechados == [] and "boom" in capsys.readouterr().err


def test_limpar_falha_de_acao_devolve_rc_1(root, capsys):
    class Falha(Falso):
        def fechar(self, id):
            raise pb.BackendError("recusou")
    rc = lp.main(["limpar", "--apply", "--sim"], root=root, backend=Falha({"2"}), saida=io.StringIO(),
                 proprio=None, suja=lambda w: False)
    assert rc == 1 and "recusou" in capsys.readouterr().err


def test_limpar_nada_a_limpar(tmp_path):
    saida = io.StringIO()
    rc = lp.main(["limpar"], root=tmp_path / "vazio", backend=Falso(), saida=saida, proprio=None)
    assert rc == 0 and "nada a limpar" in saida.getvalue()


def test_argumentos_trocados_rc_2(root):
    assert lp.main(["limpar", "--slug", "x"], root=root, backend=Falso(), saida=io.StringIO()) == 2
    assert lp.main(["retomar", "--apply"], root=root, backend=Falso(), saida=io.StringIO()) == 2


def test_painel_proprio_le_wezterm_ou_tmux():
    assert lp.painel_proprio({"WEZTERM_PANE": "7"}) == "7"
    assert lp.painel_proprio({"TMUX_PANE": "%2"}) == "%2"
    assert lp.painel_proprio({}) is None


def test_worktree_suja_com_git_falso(tmp_path):
    class R:
        def __init__(self, rc, out):
            self.returncode, self.stdout = rc, out
    assert lp.worktree_suja(None) is False
    assert lp.worktree_suja(tmp_path / "nao-existe") is False
    assert lp.worktree_suja(tmp_path, run=lambda *a, **k: R(0, "")) is False
    assert lp.worktree_suja(tmp_path, run=lambda *a, **k: R(0, " M x\n")) is True
    assert lp.worktree_suja(tmp_path, run=lambda *a, **k: R(128, "")) is None

    def rebenta(*a, **k):
        raise OSError("sem git")
    assert lp.worktree_suja(tmp_path, run=rebenta) is None


# --- retomar ---
def _sp(root, pasta, slug, extra=""):
    d = root / "proj" / "sp" / pasta
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text(
        f"---\nstatus: {pasta}\nslug: {slug}\nproject: proj\npriority: P2\ncreated: 2026-11-01\n{extra}---\n# SP {slug}\n\n## 1. Role\n\nX.\n",
        encoding="utf-8")


@pytest.fixture
def vault(tmp_path):
    v = tmp_path / "vault"
    _sp(v, "Doing", "sem-painel")
    _sp(v, "Doing", "com-painel")
    _sp(v, "Doing", "mae", "kind: program\n")
    _sp(v, "TODO", "ainda-nao")
    (tmp_path / "handoffs").mkdir()
    (tmp_path / "handoffs" / "2026-11-12-1600-sem-painel.md").write_text("h", encoding="utf-8")
    return v


@pytest.fixture
def estado(tmp_path):
    r = tmp_path / "estado"
    pe.criar_fila(programa="f", ordem=["com-painel"], root=r, agora=T0)
    pe.transitar("com-painel", "a-correr", fila="f", root=r, agora=T0, pane="9")
    return r


class Spawn:
    def __init__(self, id="42", erro=None):
        self.chamadas, self.id, self.erro = [], id, erro

    def __call__(self, slug, auto):
        self.chamadas.append(slug)
        if self.erro:
            raise self.erro
        return self.id


def test_candidatos_so_doing_sem_painel_vivo_e_nao_mae(vault, estado):
    cs = lp.candidatos(vault, pe.filas(estado), {"9"})
    assert [s.slug for s in cs] == ["sem-painel"]
    assert {s.slug for s in lp.candidatos(vault, pe.filas(estado), set())} == {"sem-painel", "com-painel"}


def test_retomar_confirmado_reabre_e_mostra_handoff(vault, estado, tmp_path):
    b, sp, saida = Falso({"9"}), Spawn("42"), io.StringIO()
    rc = lp.main(["retomar"], root=estado, root_sp=vault, backend=b, saida=saida, entrada=_entrada("s"),
                 pasta_handoffs=tmp_path / "handoffs", spawn=sp)
    assert rc == 0 and sp.chamadas == ["sem-painel"]
    assert "2026-11-12-1600-sem-painel.md" in saida.getvalue()
    assert b.titulos_postos == {"42": "sem-painel"}


def test_retomar_cancelado_nao_abre(vault, estado, tmp_path):
    sp = Spawn()
    rc = lp.main(["retomar"], root=estado, root_sp=vault, backend=Falso({"9"}), saida=io.StringIO(),
                 entrada=_entrada("n"), pasta_handoffs=tmp_path / "handoffs", spawn=sp)
    assert rc == 0 and sp.chamadas == []


def test_retomar_slug_invalido_rc_2(vault, estado, tmp_path, capsys):
    rc = lp.main(["retomar", "--slug", "com-painel"], root=estado, root_sp=vault, backend=Falso({"9"}),
                 saida=io.StringIO(), pasta_handoffs=tmp_path / "handoffs", spawn=Spawn())
    assert rc == 2 and "com-painel" in capsys.readouterr().err


def test_retomar_spawn_falha_rc_1(vault, estado, tmp_path, capsys):
    rc = lp.main(["retomar", "--sim"], root=estado, root_sp=vault, backend=Falso({"9"}), saida=io.StringIO(),
                 pasta_handoffs=tmp_path / "handoffs", spawn=Spawn(erro=OSError("sem claude")))
    assert rc == 1 and "sem claude" in capsys.readouterr().err


def test_retomar_com_varios_pede_numero(vault, estado, tmp_path):
    sp = Spawn()
    rc = lp.main(["retomar", "--sim"], root=estado, root_sp=vault, backend=Falso(), saida=io.StringIO(),
                 entrada=_entrada("2"), pasta_handoffs=tmp_path / "handoffs", spawn=sp)  # nenhum painel vivo: 2 candidatos
    assert rc == 0 and len(sp.chamadas) == 1


def test_retomar_sem_backend_ou_sem_candidatos(vault, estado, tmp_path, capsys):
    assert lp.main(["retomar"], root=estado, root_sp=vault, backend=None, saida=io.StringIO()) == 0
    assert "sem painel para reabrir" in capsys.readouterr().err
    saida = io.StringIO()
    assert lp.main(["retomar"], root=estado, root_sp=tmp_path / "vazio", backend=Falso(), saida=saida) == 0
    assert "nada a retomar" in saida.getvalue()
