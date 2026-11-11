"""sp-autor.py: o SP é preenchido num painel `sp-autor` (modelo do papel), com semente efémera e estado em ficheiro."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import sp_painel_estado as pe  # noqa: E402

_spec = importlib.util.spec_from_file_location("sp_autor", SCRIPTS / "sp-autor.py")
sa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sa)


class FakeBackend:
    nome = "fake"
    interativo = True

    def __init__(self, enviar_ok=True):
        self.abertos, self.enviados, self.titulos_postos, self.fechados = [], [], {}, []
        self.enviar_ok = enviar_ok

    def abrir(self, cmd, cwd):
        self.abertos.append((cmd, cwd))
        return "p1"

    def enviar(self, pane, texto):
        self.enviados.append((pane, texto))
        return self.enviar_ok

    def titulo(self, pane, texto):
        self.titulos_postos[pane] = texto
        return True

    def titulos(self):
        return dict(self.titulos_postos)

    def fechar(self, pane):
        self.fechados.append(pane)
        return True


@pytest.fixture
def modelos_json(tmp_path, monkeypatch):
    p = tmp_path / "modelos.json"
    p.write_text(json.dumps({"papeis": {"sp-autor": {"model": "claude-teste-1", "effort": "low"}}}), encoding="utf-8")
    monkeypatch.setattr(sa, "MODELOS", p)
    return p


@pytest.fixture
def sp_vazio(tmp_path):
    p = tmp_path / "proj-algo-2026-11-11.md"
    p.write_text("---\nslug: proj-algo-2026-11-11\n---\n# Super Prompt\n", encoding="utf-8")
    return p


def _semente(tmp_path, texto="decisões do grill"):
    s = tmp_path / "semente.md"
    s.write_text(texto, encoding="utf-8")
    return s


def test_comando_usa_o_modelo_do_papel(modelos_json):
    assert sa.comando() == ["claude", "--model", "claude-teste-1", "--effort", "low"]


def test_titulo_e_chave():
    assert sa.titulo("x-2026") == "sp-autor x-2026"
    assert sa.chave("x-2026") == "sp-autor-x-2026"


def test_prompt_numa_linha_com_consumo_e_estado(sp_vazio, tmp_path):
    s = _semente(tmp_path)
    t = sa.prompt(sp_vazio, s)
    assert "\n" not in t
    assert f'sp-autor.py --consume "{s}"' in t
    assert "sp-estado.py sp-autor-proj-algo-2026-11-11 done" in t
    assert str(sp_vazio) in t
    assert "Agent" not in t


def test_lancar_abre_painel_titulo_envia_e_regista(modelos_json, sp_vazio, tmp_path):
    b = FakeBackend()
    root = tmp_path / "estado"
    res = sa.lancar(sp_vazio, _semente(tmp_path), b, cwd=tmp_path, estado_root=root, sleep=lambda s: None)
    assert res["estado"] == "a-correr"
    cmd, cwd = b.abertos[0]
    assert cmd[:3] == ["claude", "--model", "claude-teste-1"] and Path(cwd) == tmp_path
    assert b.titulos_postos["p1"] == "sp-autor proj-algo-2026-11-11"
    assert "sp-autor.py --consume" in b.enviados[0][1]
    k = "sp-autor-proj-algo-2026-11-11"
    sp = pe.ler(pe.procurar(k, root=root), k, root=root)
    assert sp["estado"] == "a-correr" and sp["pane"] == "p1" and sp["modelo"] == "claude-teste-1"


def test_lancar_conta_para_o_teto_global(modelos_json, sp_vazio, tmp_path):
    root = tmp_path / "estado"
    f = pe.criar_fila("outra", root=root)
    for i in range(pe.MAX_PARALELO):
        pe.registar(f, f"s{i}", root=root)
        assert pe.reclamar_vaga(f"s{i}", fila=f, root=root)
    b = FakeBackend()
    res = sa.lancar(sp_vazio, _semente(tmp_path), b, cwd=tmp_path, estado_root=root, sleep=lambda s: None)
    assert res["estado"] == "pendente" and b.abertos == []


def test_lancar_falha_no_envio_fecha_o_painel_e_liberta(modelos_json, sp_vazio, tmp_path):
    b = FakeBackend(enviar_ok=False)
    root = tmp_path / "estado"
    res = sa.lancar(sp_vazio, _semente(tmp_path), b, cwd=tmp_path, estado_root=root, sleep=lambda s: None)
    assert res["estado"] == "falhou" and b.fechados == ["p1"]
    assert pe.vagas_livres(root=root) == pe.MAX_PARALELO


def test_semente_inexistente_falha_antes_de_abrir(modelos_json, sp_vazio, tmp_path):
    b = FakeBackend()
    with pytest.raises(sa.SpAutorErro):
        sa.lancar(sp_vazio, tmp_path / "nao.md", b, cwd=tmp_path, estado_root=tmp_path / "e", sleep=lambda s: None)
    assert b.abertos == []


def test_consume_imprime_e_apaga(tmp_path):
    s = _semente(tmp_path, "olá semente")
    vistos = []
    sa.consume(s, out=vistos.append)
    assert vistos == ["olá semente"] and not s.exists()


def test_consume_falha_ao_imprimir_mantem_o_ficheiro(tmp_path):
    s = _semente(tmp_path)

    def rebenta(_):
        raise OSError("sem stdout")

    with pytest.raises(OSError):
        sa.consume(s, out=rebenta)
    assert s.exists()


def test_cli_dry_run_mostra_o_plano(modelos_json, sp_vazio, tmp_path, monkeypatch, capsys):
    rc = sa.main(["--sp", str(sp_vazio), "--semente", str(_semente(tmp_path)), "--dry-run", "--modelos", str(modelos_json)])
    out = capsys.readouterr().out
    assert rc == 0 and "sp-autor proj-algo-2026-11-11" in out and "claude-teste-1" in out


def test_cli_help_corre():
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "sp-autor.py"), "--help"], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and "--semente" in r.stdout
