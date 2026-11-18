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


def test_titulo_por_defeito_nao_faz_nada():
    b = Falso()
    assert b.titulo(b.abrir(["x"], "/tmp/a"), "meu-sp") is False and b.titulos() == {}


def test_wezterm_titulo_e_titulos_do_separador():
    chamadas = []
    lista = json.dumps([{"pane_id": 7, "tab_title": "a"}, {"pane_id": 8, "tab_title": ""}, {"pane_id": 9}])
    b = pb.WeztermBackend(_run(lista, chamadas))
    assert b.titulo("7", "meu-sp") is True
    assert ["wezterm", "cli", "set-tab-title", "--pane-id", "7", "meu-sp"] in chamadas
    assert b.titulos() == {"7": "a"}


def test_wezterm_titulos_sem_executavel_e_vazio():
    def run(argv, **kw):
        raise FileNotFoundError("wezterm")
    assert pb.WeztermBackend(run).titulos() == {}


def test_wezterm_devolve_foco_ao_painel_de_origem(monkeypatch):
    monkeypatch.setenv("WEZTERM_PANE", "3")
    chamadas = []
    b = pb.WeztermBackend(_run("7\n", chamadas))
    b.abrir(["claude"], "C:/wt")
    assert ["wezterm", "cli", "activate-pane", "--pane-id", "3"] in chamadas


def test_wezterm_spawn_sem_no_color_no_ambiente(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("FORCE_COLOR", "0")
    monkeypatch.setenv("PATH_MARCA", "fica")
    envs = []

    def run(argv, **kw):
        if argv[:3] == ["wezterm", "cli", "spawn"]:
            envs.append(kw.get("env"))
        return SimpleNamespace(stdout="7\n", returncode=0)
    pb.WeztermBackend(run).abrir(["claude"], "C:/wt")
    assert envs[0] is not None
    assert "NO_COLOR" not in envs[0] and "FORCE_COLOR" not in envs[0]
    assert envs[0]["PATH_MARCA"] == "fica"


def test_wezterm_spawn_repete_sem_socket_herdado(monkeypatch):
    monkeypatch.setenv("WEZTERM_UNIX_SOCKET", "C:/velho/gui-sock-1")
    monkeypatch.delenv("WEZTERM_PANE", raising=False)
    envs = []

    def run(argv, **kw):
        envs.append(kw.get("env"))
        if "WEZTERM_UNIX_SOCKET" in kw["env"]:
            raise subprocess.CalledProcessError(1, argv, "", "connect failed")
        return SimpleNamespace(stdout="9\n", returncode=0)
    assert pb.WeztermBackend(run).abrir(["claude"], "C:/wt") == "9"
    assert len(envs) == 2 and "WEZTERM_UNIX_SOCKET" not in envs[1]


def test_wezterm_spawn_erro_final_traz_stderr(monkeypatch):
    monkeypatch.setenv("WEZTERM_UNIX_SOCKET", "C:/velho/gui-sock-1")

    def run(argv, **kw):
        raise subprocess.CalledProcessError(1, argv, "", "sem janela")
    with pytest.raises(subprocess.CalledProcessError) as e:
        pb.WeztermBackend(run).abrir(["claude"], "C:/wt")
    assert "sem janela" in e.value.stderr


def test_wezterm_sem_executavel_lista_vazia():
    def run(argv, **kw):
        raise FileNotFoundError("wezterm")
    b = pb.WeztermBackend(run)
    assert b.listar() == {} and b.estado("1") == "morto"


def test_tmux_abrir_estado_fechar(monkeypatch):
    monkeypatch.delenv("TMUX_PANE", raising=False)
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
            time.sleep(0.1)  # espera real: o subprocesso escreve o log e termina de forma assíncrona; relógio injetado não o acelera
        assert "ola" in b.ecra(i)
    finally:
        assert b.fechar(i) is True
    for _ in range(50):
        if b.estado(i) == "morto":
            break
        time.sleep(0.1)  # espera real: o subprocesso escreve o log e termina de forma assíncrona; relógio injetado não o acelera
    assert b.estado(i) == "morto" and i not in b.listar()
    assert b.fechar(i) is False


def test_background_processo_que_termina_fica_morto(tmp_path):
    b = pb.BackgroundBackend(tmp_path)
    i = b.abrir([sys.executable, "-c", "print('fim')"], tmp_path)
    for _ in range(100):
        if b.estado(i) == "morto":
            break
        time.sleep(0.1)  # espera real: o subprocesso escreve o log e termina de forma assíncrona; relógio injetado não o acelera
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


def test_tmux_foco_so_em_painel_existente():
    chamadas = []
    b = pb.TmuxBackend(_run(lambda a: "%4" + chr(9) + "/w" + chr(10), chamadas))
    assert b.foco("%4") is True and ["tmux", "select-pane", "-t", "%4"] in chamadas
    assert b.foco("%1") is False


def _herdr(argv):
    lista = {"result": {"panes": [{"pane_id": "w1:p1", "cwd": "/work/wt", "tab_id": "w1:t1", "workspace_id": "w1", "label": "sb"},
                                  {"pane_id": "w1:p2", "cwd": "/work/outro", "tab_id": "w1:t2", "workspace_id": "w1"}]}}
    if argv[1:3] == ["pane", "split"]:
        return json.dumps({"result": {"pane": {"pane_id": "w1:p9"}}})
    if argv[1:3] == ["tab", "create"]:
        return json.dumps({"result": {"root_pane": {"pane_id": "w2:p1"}}})
    return json.dumps(lista)


def test_herdr_abrir_divide_o_painel_de_origem(monkeypatch):
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    chamadas = []
    b = pb.HerdrBackend(_run(_herdr, chamadas))
    assert b.abrir(["claude", "/michi x y"], "/work/wt") == "w1:p9"
    assert chamadas[-2] == ["herdr", "pane", "split", "w1:p1", "--direction", "right", "--cwd", "/work/wt", "--no-focus"]
    assert chamadas[-1] == ["herdr", "pane", "run", "w1:p9", "exec claude '/michi x y'"]


def _herdr_com(panes):
    def f(argv):
        if argv[1:3] == ["pane", "list"]:
            return json.dumps({"result": {"panes": panes}})
        return _herdr(argv)
    return f


def test_herdr_abrir_tab_cheia_cria_tab_no_workspace_da_origem(monkeypatch):
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    panes = [{"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1"},
             {"pane_id": "w1:p3", "tab_id": "w1:t1", "workspace_id": "w1"},
             {"pane_id": "w1:p2", "tab_id": "w1:t2", "workspace_id": "w1"}]
    chamadas = []
    b = pb.HerdrBackend(_run(_herdr_com(panes), chamadas))
    assert b.abrir(["claude"], "/w") == "w2:p1"
    assert chamadas[-2] == ["herdr", "tab", "create", "--workspace", "w1", "--cwd", "/w", "--no-focus"]
    assert not any(c[1:3] == ["pane", "split"] for c in chamadas)


def test_herdr_abrir_lista_vazia_cria_tab_sem_split(monkeypatch):
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    chamadas = []
    b = pb.HerdrBackend(_run(_herdr_com([]), chamadas))
    assert b.abrir(["claude"], "/w") == "w2:p1"
    assert ["herdr", "tab", "create", "--cwd", "/w", "--no-focus"] in chamadas
    assert not any(c[1:3] == ["pane", "split"] for c in chamadas)


def test_herdr_abrir_fora_do_herdr_cria_tab(monkeypatch):
    monkeypatch.delenv("HERDR_PANE_ID", raising=False)
    chamadas = []
    b = pb.HerdrBackend(_run(_herdr, chamadas))
    assert b.abrir(["claude"], "/w") == "w2:p1"
    assert ["herdr", "tab", "create", "--cwd", "/w", "--no-focus"] in chamadas  # herdr sem workspace utilizável: comportamento anterior
    assert not any(c[1:3] == ["pane", "list"] for c in chamadas)  # sem origem não consulta os panes


def test_herdr_sem_id_levanta(monkeypatch):
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    b = pb.HerdrBackend(_run("{}", []))
    with pytest.raises(pb.BackendError):
        b.abrir(["claude"], "/w")


def test_herdr_listar_titulos_foco_enviar_fechar(monkeypatch):
    monkeypatch.setattr(pb.time, "sleep", lambda s: None)
    chamadas, ecra = [], {"txt": "❯ "}

    def herdr(argv):
        if argv[1:3] == ["pane", "send-text"]:
            ecra["txt"] = "❯ " + argv[4]
        elif argv[1:3] == ["pane", "send-keys"]:
            ecra["txt"] = "❯ "
        elif argv[1:3] == ["pane", "read"]:
            return ecra["txt"]
        return _herdr(argv)
    b = pb.HerdrBackend(_run(herdr, chamadas))
    assert b.listar() == {"w1:p1": "/work/wt", "w1:p2": "/work/outro"}
    assert b.titulos() == {"w1:p1": "sb"}
    assert b.estado("w1:p2") == "vivo" and b.estado("w9:p9") == "morto"
    assert b.foco("w1:p2") is True and ["herdr", "tab", "focus", "w1:t2"] in chamadas
    assert b.foco("w9:p9") is False
    assert b.enviar("w1:p1", "/michi a") is True
    assert ["herdr", "pane", "send-text", "w1:p1", "/michi a"] in chamadas
    assert ["herdr", "pane", "send-keys", "w1:p1", "Enter"] in chamadas
    assert chamadas.index(["herdr", "pane", "send-keys", "w1:p1", "Enter"]) > chamadas.index(["herdr", "pane", "read", "w1:p1", "--source", "visible"])
    assert b.enviar("w9:p9", "x") is False
    assert b.fechar("w1:p1") is True and ["herdr", "pane", "close", "w1:p1"] in chamadas
    assert b.fechar("w9:p9") is False


def test_herdr_listar_com_servidor_em_baixo():
    def falha(argv, **kw):
        raise OSError("sem herdr")
    assert pb.HerdrBackend(falha).listar() == {}


def test_painel_atual_prefere_herdr():
    assert pb.painel_atual({"HERDR_PANE_ID": "w1:p1", "WEZTERM_PANE": "3"}) == ("herdr", "w1:p1")
    assert pb.painel_atual({"TMUX_PANE": "%1"}) == ("tmux", "%1")
    assert pb.painel_atual({}) == (None, None)


def test_escolher_auto_deteta_herdr():
    sempre = lambda nome: "/usr/bin/" + nome  # noqa: E731
    assert pb.escolher("auto", {"HERDR_PANE_ID": "w1:p1"}, sempre).nome == "herdr"
    assert pb.escolher("herdr", {}, sempre).nome == "herdr"


def test_tmux_abrir_divide_o_painel_de_origem(monkeypatch):
    monkeypatch.setenv("TMUX_PANE", "%3")
    chamadas = []
    b = pb.TmuxBackend(_run("%9\n", chamadas))
    assert b.abrir(["claude"], "/w") == "%9"
    assert chamadas[0] == ["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", "%3", "-c", "/w", "claude"]


# --- workspace herdr por projeto ---------------------------------------------------------------

def _repo_git(tmp_path):
    import subprocess as sp
    raiz = tmp_path / "projx"
    raiz.mkdir()
    sp.run(["git", "init", "-q", str(raiz)], check=True)
    sp.run(["git", "-C", str(raiz), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"], check=True)
    return raiz


def _herdr_ws(workspaces, panes):
    def f(argv):
        if argv[1:3] == ["workspace", "list"]:
            return json.dumps({"result": {"workspaces": workspaces}})
        if argv[1:3] == ["workspace", "create"]:
            return json.dumps({"result": {"workspace": {"workspace_id": "w7"}, "root_pane": {"pane_id": "w7:p1"}}})
        if argv[1:3] == ["pane", "list"]:
            return json.dumps({"result": {"panes": panes}})
        if argv[1:3] == ["tab", "create"]:
            return json.dumps({"result": {"root_pane": {"pane_id": "w5:p8"}}})
        if argv[1:3] == ["pane", "split"]:
            return json.dumps({"result": {"pane": {"pane_id": "w5:p9"}}})
        return "{}"
    return f


def test_herdr_workspace_novo_para_repo_sem_workspace(monkeypatch, tmp_path):
    raiz = _repo_git(tmp_path)
    monkeypatch.delenv("HERDR_PANE_ID", raising=False)
    chamadas = []
    b = pb.HerdrBackend(_run(_herdr_ws([], []), chamadas))
    assert b.abrir(["claude"], str(raiz)) == "w7:p1"
    assert ["herdr", "workspace", "create", "--cwd", str(raiz), "--label", "projx", "--no-focus"] in chamadas
    assert chamadas[-1] == ["herdr", "pane", "run", "w7:p1", "exec claude"]


def test_herdr_workspace_existente_e_reutilizado(monkeypatch, tmp_path):
    raiz = _repo_git(tmp_path)
    monkeypatch.delenv("HERDR_PANE_ID", raising=False)
    chamadas = []
    b = pb.HerdrBackend(_run(_herdr_ws([{"workspace_id": "w5", "label": "projx"}], []), chamadas))
    assert b.abrir(["claude"], str(raiz)) == "w5:p8"
    assert not any(c[1:3] == ["workspace", "create"] for c in chamadas)
    assert ["herdr", "tab", "create", "--workspace", "w5", "--cwd", str(raiz), "--no-focus"] in chamadas


def test_herdr_worktree_usa_o_workspace_do_repo_principal(monkeypatch, tmp_path):
    import subprocess as sp
    raiz = _repo_git(tmp_path)
    wt = tmp_path / "wt-projx"
    sp.run(["git", "-C", str(raiz), "worktree", "add", "-q", "-b", "agent/x", str(wt)], check=True)
    monkeypatch.delenv("HERDR_PANE_ID", raising=False)
    chamadas = []
    b = pb.HerdrBackend(_run(_herdr_ws([{"workspace_id": "w5", "label": "projx"}], []), chamadas))
    assert b.abrir(["claude"], str(wt)) == "w5:p8"
    assert not any(c[1:3] == ["workspace", "create"] for c in chamadas)
    assert ["herdr", "tab", "create", "--workspace", "w5", "--cwd", str(wt), "--no-focus"] in chamadas


def test_herdr_origem_noutro_workspace_nunca_divide(monkeypatch, tmp_path):
    raiz = _repo_git(tmp_path)
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    panes = [{"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1"}]  # origem sozinha na tab, mas noutro workspace
    chamadas = []
    b = pb.HerdrBackend(_run(_herdr_ws([{"workspace_id": "w5", "label": "projx"}], panes), chamadas))
    assert b.abrir(["claude"], str(raiz)) == "w5:p8"
    assert not any(c[1:3] == ["pane", "split"] for c in chamadas)


def test_herdr_origem_no_workspace_do_projeto_divide(monkeypatch, tmp_path):
    raiz = _repo_git(tmp_path)
    monkeypatch.setenv("HERDR_PANE_ID", "w5:p1")
    panes = [{"pane_id": "w5:p1", "tab_id": "w5:t1", "workspace_id": "w5"}]
    chamadas = []
    b = pb.HerdrBackend(_run(_herdr_ws([{"workspace_id": "w5", "label": "projx"}], panes), chamadas))
    assert b.abrir(["claude"], str(raiz)) == "w5:p9"


def test_herdr_origem_no_workspace_do_projeto_tab_cheia_cria_tab(monkeypatch, tmp_path):
    raiz = _repo_git(tmp_path)
    monkeypatch.setenv("HERDR_PANE_ID", "w5:p1")
    panes = [{"pane_id": "w5:p1", "tab_id": "w5:t1", "workspace_id": "w5"}, {"pane_id": "w5:p2", "tab_id": "w5:t1", "workspace_id": "w5"}]
    chamadas = []
    b = pb.HerdrBackend(_run(_herdr_ws([{"workspace_id": "w5", "label": "projx"}], panes), chamadas))
    assert b.abrir(["claude"], str(raiz)) == "w5:p8"
    assert not any(c[1:3] == ["pane", "split"] for c in chamadas)


def test_herdr_max_panes_configuravel(monkeypatch):
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    panes = [{"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1"},
             {"pane_id": "w1:p3", "tab_id": "w1:t1", "workspace_id": "w1"}]
    chamadas = []
    b = pb.por_nome("herdr", _run(_herdr_com(panes), chamadas), herdr={"maxPanesPorTab": 3, "workspacePorProjeto": False})
    assert (b.max_panes, b.workspace_por_projeto) == (3, False)
    assert b.abrir(["claude"], "/w") == "w1:p9"  # 2 panes < 3: divide
    assert not any(c[1:3] == ["workspace", "list"] for c in chamadas)  # sem workspace por projeto


def test_herdr_defeitos_sem_config():
    b = pb.por_nome("herdr", _run("{}", []))
    assert (b.max_panes, b.workspace_por_projeto) == (2, True)
