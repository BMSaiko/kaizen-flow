"""Testes de painel_backend: contrato (abrir/estado/fechar), os três backends e a escolha/fallback."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import painel_backend as pb


class Falso(pb.Backend):
    """Backend em memória: serve de referência ao contrato."""
    nome = "falso"
    interativo = False

    def __init__(self):
        self.vivos = {}
        self.n = 0

    def abrir(self, cmd, cwd):
        self.n += 1
        self.vivos[str(self.n)] = str(cwd)
        return str(self.n)

    def listar(self):
        return dict(self.vivos)

    def fechar(self, id):
        return self.vivos.pop(str(id), None) is not None

    def ecra(self, id):
        return ""


def test_contrato_abrir_estado_fechar():
    b = Falso()
    i = b.abrir(["x"], "/tmp/a")
    assert b.estado(i) == "vivo"
    assert b.fechar(i) is True
    assert b.estado(i) == "morto"
    assert b.fechar(i) is False  # já não existe: não é erro


def test_backend_base_e_abstrato():
    with pytest.raises(TypeError):
        pb.Backend()


def _run(respostas, chamadas):
    def run(argv, **kw):
        chamadas.append(list(argv))
        out = respostas(argv) if callable(respostas) else respostas
        return SimpleNamespace(stdout=out, returncode=0)
    return run


def test_wezterm_abrir_estado_fechar(monkeypatch):
    monkeypatch.delenv("WEZTERM_PANE", raising=False)
    chamadas = []
    lista = json.dumps([{"pane_id": 7, "cwd": "file:///C:/wt"}])
    b = pb.WeztermBackend(_run(lambda a: "7\n" if a[:3] == ["wezterm", "cli", "spawn"] else lista, chamadas))
    assert b.abrir(["claude", "-p", "x"], "C:/wt") == "7"
    assert chamadas[0] == ["wezterm", "cli", "spawn", "--cwd", "C:/wt", "--", "claude", "-p", "x"]
    assert b.estado("7") == "vivo" and b.estado("8") == "morto"
    assert b.listar() == {"7": "file:///C:/wt"}
    assert b.fechar("7") is True
    assert ["wezterm", "cli", "kill-pane", "--pane-id", "7"] in chamadas
    chamadas.clear()
    assert b.fechar("9") is False and not any(c[2] == "kill-pane" for c in chamadas)


def test_wezterm_devolve_foco_ao_painel_de_origem(monkeypatch):
    monkeypatch.setenv("WEZTERM_PANE", "3")
    chamadas = []
    b = pb.WeztermBackend(_run("7\n", chamadas))
    b.abrir(["claude"], "C:/wt")
    assert ["wezterm", "cli", "activate-pane", "--pane-id", "3"] in chamadas


def test_wezterm_sem_executavel_lista_vazia():
    def run(argv, **kw):
        raise FileNotFoundError("wezterm")
    b = pb.WeztermBackend(run)
    assert b.listar() == {} and b.estado("1") == "morto"


def test_tmux_abrir_estado_fechar():
    chamadas = []
    saida = "%4\t/work/wt\n%5\t/work/outro\n"
    b = pb.TmuxBackend(_run(lambda a: "%9\n" if a[:2] == ["tmux", "split-window"] else saida, chamadas))
    assert b.abrir(["claude"], "/work/wt") == "%9"
    assert chamadas[0] == ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-c", "/work/wt", "claude"]
    assert b.listar() == {"%4": "/work/wt", "%5": "/work/outro"}
    assert b.estado("%4") == "vivo" and b.estado("%1") == "morto"
    assert b.fechar("%4") is True and ["tmux", "kill-pane", "-t", "%4"] in chamadas
    assert b.fechar("%1") is False


def test_background_corre_processo_escreve_log_e_da_estado_por_pid(tmp_path):
    b = pb.BackgroundBackend(tmp_path / "estado")
    cmd = [sys.executable, "-c", "import time; print('ola', flush=True); time.sleep(30)"]
    i = b.abrir(cmd, tmp_path)
    try:
        assert i.isdigit()
        assert b.estado(i) == "vivo"
        assert i in b.listar() and Path(b.listar()[i]) == tmp_path
        for _ in range(50):  # o log enche-se de forma assíncrona
            if "ola" in b.ecra(i):
                break
            time.sleep(0.1)
        assert "ola" in b.ecra(i)
    finally:
        assert b.fechar(i) is True
    for _ in range(50):
        if b.estado(i) == "morto":
            break
        time.sleep(0.1)
    assert b.estado(i) == "morto" and i not in b.listar()
    assert b.fechar(i) is False


def test_background_processo_que_termina_fica_morto(tmp_path):
    b = pb.BackgroundBackend(tmp_path)
    i = b.abrir([sys.executable, "-c", "print('fim')"], tmp_path)
    for _ in range(100):
        if b.estado(i) == "morto":
            break
        time.sleep(0.1)
    assert b.estado(i) == "morto"
    assert "fim" in b.ecra(i)  # o log sobrevive ao processo


def test_background_cwd_inexistente_levanta_erro_claro(tmp_path):
    b = pb.BackgroundBackend(tmp_path)
    with pytest.raises(pb.BackendError):
        b.abrir([sys.executable, "-c", "pass"], tmp_path / "nao-existe")


# --- escolha e fallback ---

def test_escolher_automatico_pelo_ambiente():
    sempre = lambda nome: "/bin/" + nome
    assert pb.escolher("auto", {"WEZTERM_PANE": "1"}, sempre).nome == "wezterm"
    assert pb.escolher("auto", {"TMUX_PANE": "%1"}, sempre).nome == "tmux"
    assert pb.escolher("auto", {"WEZTERM_PANE": "1", "TMUX_PANE": "%1"}, sempre).nome == "wezterm"


def test_escolher_automatico_sem_multiplexer_e_none():
    assert pb.escolher("auto", {}, lambda n: None) is None
    assert pb.escolher("auto", {"WEZTERM_PANE": "1"}, lambda n: None) is None  # sem executável


def test_escolher_por_config_manda_sobre_o_ambiente(tmp_path):
    sempre = lambda nome: "/bin/" + nome
    b = pb.escolher("background", {"WEZTERM_PANE": "1"}, sempre, estado_dir=tmp_path)
    assert b.nome == "background" and not b.interativo
    assert pb.escolher("tmux", {}, sempre).nome == "tmux"
    assert pb.escolher("tmux", {}, lambda n: None) is None  # pedido mas indisponível


def test_falta_diz_o_que_falta():
    assert "wezterm" in pb.falta("wezterm", {}, lambda n: None)
    assert "tmux" in pb.falta("tmux", {}, lambda n: None)
    msg = pb.falta("auto", {}, lambda n: None)
    assert "WezTerm" in msg and "tmux" in msg and "painelBackend" in msg and "background" in msg


def test_por_nome_desconhecido_levanta():
    with pytest.raises(pb.BackendError):
        pb.por_nome("zellij")
    assert pb.por_nome("background").nome == "background"


def test_config_painel_backend(tmp_path):
    import kaizen_config
    assert kaizen_config.painel_backend(tmp_path) == "auto"
    (tmp_path / "kaizen.config.json").write_text(json.dumps({"painelBackend": "tmux"}), encoding="utf-8")
    assert kaizen_config.painel_backend(tmp_path) == "tmux"
    (tmp_path / "kaizen.config.json").write_text(json.dumps({"painelBackend": "zellij"}), encoding="utf-8")
    assert kaizen_config.painel_backend(tmp_path) == "auto"  # valor inválido: defeito


def test_background_falha_a_lancar_da_backend_error_e_nao_deixa_log(tmp_path):
    def popen(*a, **kw):
        raise FileNotFoundError("sem claude")
    b = pb.BackgroundBackend(estado_dir=tmp_path / "e", popen=popen)
    with pytest.raises(pb.BackendError):
        b.abrir(["claude", "-p", "x"], str(tmp_path))
    assert list((tmp_path / "e").iterdir()) == []


def test_background_registo_anterior_ao_arranque_nao_e_vivo(tmp_path, monkeypatch):
    monkeypatch.setattr(pb, "_arranque_sistema", lambda: time.time() - 3600)
    b = pb.BackgroundBackend(estado_dir=tmp_path)
    (tmp_path / f"{os.getpid()}.json").write_text(json.dumps({"pid": os.getpid(), "cwd": str(tmp_path), "log": "x", "inicio": 1.0}), encoding="utf-8")
    assert b.estado(os.getpid()) == "morto"
    assert b.fechar(os.getpid()) is False


def test_background_limpa_registos_mortos_antigos(tmp_path):
    b = pb.BackgroundBackend(estado_dir=tmp_path)
    velho = tmp_path / "999999.json"
    velho.write_text(json.dumps({"pid": 999999, "cwd": "x", "log": str(tmp_path / "999999.log"), "inicio": 1.0}), encoding="utf-8")
    (tmp_path / "999999.log").write_text("x", encoding="utf-8")
    os.utime(velho, (1.0, 1.0))
    b._limpar()
    assert not velho.exists() and not (tmp_path / "999999.log").exists()
