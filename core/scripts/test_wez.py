"""Testes de scripts/wez.py (sem WezTerm aberto: subprocess simulado)."""
import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest
from sp_carregar import carregar  # noqa: E402

wez = carregar(Path(__file__).with_name("wez.py"), "wez", registar=False, fresco=True)


def _done(rc=0, out="", err=""):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=out, stderr=err)


def test_run_cli_devolve_stdout():
    with mock.patch.object(wez.subprocess, "run", return_value=_done(out="ok\n")) as run:
        assert wez.run_cli(["list"]) == "ok\n"
    cmd = run.call_args.args[0]
    assert cmd[1:] == ["cli", "list"]


def test_run_cli_rc_diferente_de_zero_da_erro():
    with mock.patch.object(wez.subprocess, "run", return_value=_done(rc=1, err="boom")):
        with pytest.raises(wez.WezError, match="boom"):
            wez.run_cli(["list"])


def test_run_cli_sem_wezterm_da_erro():
    with mock.patch.object(wez.subprocess, "run", side_effect=FileNotFoundError):
        with pytest.raises(wez.WezError, match="PATH"):
            wez.run_cli(["list"])


def test_run_cli_timeout_da_erro():
    exc = subprocess.TimeoutExpired(cmd="wezterm", timeout=1)
    with mock.patch.object(wez.subprocess, "run", side_effect=exc):
        with pytest.raises(wez.WezError, match="tempo"):
            wez.run_cli(["list"])


def test_list_panes_le_json():
    panes = [{"pane_id": 3, "title": "a"}, {"pane_id": 5, "title": "b"}]
    with mock.patch.object(wez, "run_cli", return_value=json.dumps(panes)) as rc:
        assert wez.list_panes() == panes
    assert rc.call_args.args[0] == ["list", "--format", "json"]


def test_list_panes_json_invalido_da_erro():
    with mock.patch.object(wez, "run_cli", return_value="nao-json"):
        with pytest.raises(wez.WezError, match="JSON"):
            wez.list_panes()


def test_help_lista_subcomandos(capsys):
    with pytest.raises(SystemExit) as ex:
        wez.main(["--help"])
    assert ex.value.code == 0
    out = capsys.readouterr().out
    for sub in ("pane", "send", "read", "layout", "cfg"):
        assert sub in out


def test_subcomando_por_implementar_rc_2(capsys, monkeypatch):
    monkeypatch.delitem(wez._HANDLERS, "layout")
    assert wez.main(["layout"]) == 2
    assert "por implementar" in capsys.readouterr().err


def test_main_converte_wezerror_em_rc_1(capsys):
    with mock.patch.object(wez, "_HANDLERS", {"pane": mock.Mock(side_effect=wez.WezError("x"))}):
        assert wez.main(["pane"]) == 1
    assert "x" in capsys.readouterr().err


# --- wez pane (wezterm-wez-pane-2026-11-10) ---

PANES = [
    {"pane_id": 0, "title": "\u2810 Kf-bugs-motor-2026-11-07", "tab_title": "", "cwd": "file:///C:/sb/", "is_active": False},
    {"pane_id": 2, "title": "\u25d0 CLI tools para WezTerm", "tab_title": "wezterm-wez-pane", "cwd": "file:///C:/sb/", "is_active": True},
    {"pane_id": 3, "title": "pwsh.exe", "tab_title": "", "cwd": "file:///C:/x/", "is_active": False},
    {"pane_id": 7, "title": "\u2733 Claude Code", "tab_title": "", "cwd": "file:///C:/sb/", "is_active": False},
]


def test_norm_tira_icone_e_normaliza():
    assert wez.norm("\u25d0 CLI tools_para WezTerm") == "cli-tools-para-wezterm"


@pytest.mark.parametrize("nome,pid", [
    ("3", 3), ("pwsh.exe", 3), ("Kf-bugs-motor-2026-11-07", 0),
    ("kf-bugs", 0), ("wezterm-wez-pane", 2), ("claude code", 7), ("tools para", 2),
])
def test_resolve_pane(nome, pid):
    assert wez.resolve_pane(nome, PANES) == pid


def test_resolve_pane_ambiguo_lista_candidatos():
    panes = PANES + [{"pane_id": 9, "title": "kf-bugs-outro", "tab_title": ""}]
    with pytest.raises(wez.WezError, match="amb\u00edguo.*0.*9"):
        wez.resolve_pane("kf-bugs", panes)


def test_resolve_pane_exato_ganha_a_prefixo():
    panes = [{"pane_id": 1, "title": "michi", "tab_title": ""},
             {"pane_id": 4, "title": "michi-2", "tab_title": ""}]
    assert wez.resolve_pane("michi", panes) == 1


def test_resolve_pane_nao_encontrado():
    with pytest.raises(wez.WezError, match="n\u00e3o encontrado"):
        wez.resolve_pane("nada-disto", PANES)


def test_resolve_pane_id_inexistente():
    with pytest.raises(wez.WezError, match="n\u00e3o encontrado"):
        wez.resolve_pane("42", PANES)


def test_pane_ls(capsys):
    with mock.patch.object(wez, "list_panes", return_value=PANES):
        assert wez.main(["pane", "ls"]) == 0
    out = capsys.readouterr().out
    assert "pwsh.exe" in out and "wezterm-wez-pane" in out and "C:/x/" in out and "/C:/x/" not in out


def test_pane_ls_json(capsys):
    with mock.patch.object(wez, "list_panes", return_value=PANES):
        assert wez.main(["pane", "ls", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"] == 0


def test_pane_open_spawn_e_titulo(capsys):
    with mock.patch.object(wez, "run_cli", side_effect=["11\n", ""]) as rc:
        assert wez.main(["pane", "open", "wez-teste", "--cwd", "C:/sb", "--", "pwsh"]) == 0
    assert rc.call_args_list[0].args[0] == ["spawn", "--cwd", "C:/sb", "--", "pwsh"]
    assert rc.call_args_list[1].args[0] == ["set-tab-title", "--pane-id", "11", "wez-teste"]
    assert capsys.readouterr().out.strip() == "11"


def test_pane_open_new_window():
    with mock.patch.object(wez, "run_cli", side_effect=["5\n", ""]) as rc:
        assert wez.main(["pane", "open", "x", "--new-window"]) == 0
    assert rc.call_args_list[0].args[0] == ["spawn", "--new-window"]


def test_pane_focus():
    with mock.patch.object(wez, "list_panes", return_value=PANES), \
         mock.patch.object(wez, "run_cli", return_value="") as rc:
        assert wez.main(["pane", "focus", "pwsh"]) == 0
    assert rc.call_args.args[0] == ["activate-pane", "--pane-id", "3"]


def test_pane_kill(monkeypatch):
    monkeypatch.setenv("WEZTERM_PANE", "2")
    with mock.patch.object(wez, "list_panes", return_value=PANES), \
         mock.patch.object(wez, "run_cli", return_value="") as rc:
        assert wez.main(["pane", "kill", "pwsh"]) == 0
    assert rc.call_args.args[0] == ["kill-pane", "--pane-id", "3"]


def test_pane_kill_recusa_o_proprio_sem_force(monkeypatch, capsys):
    monkeypatch.setenv("WEZTERM_PANE", "3")
    with mock.patch.object(wez, "list_panes", return_value=PANES), \
         mock.patch.object(wez, "run_cli", return_value="") as rc:
        assert wez.main(["pane", "kill", "pwsh"]) == 1
        assert not rc.called
        assert wez.main(["pane", "kill", "pwsh", "--force"]) == 0
    assert "--force" in capsys.readouterr().err


def test_resolve_pane_titulo_ganha_a_separador_partilhado():
    panes = [{"pane_id": 0, "title": "✳ Kf-bugs", "tab_title": "sp-x"},
             {"pane_id": 2, "title": "◑ CLI tools", "tab_title": "sp-x"}]
    assert wez.resolve_pane("cli tools", panes) == 2
    with pytest.raises(wez.WezError, match="ambíguo"):
        wez.resolve_pane("sp-x", panes)


# --- send/read (wezterm-wez-send-2026-11-10) ---

def test_send_text_no_paste_sem_enter():
    with mock.patch.object(wez, "run_cli") as rc:
        wez.send_text(3, "ls")
    rc.assert_called_once_with(["send-text", "--no-paste", "--pane-id", "3", "ls"])


def test_send_text_com_enter_acrescenta_cr():
    with mock.patch.object(wez, "run_cli") as rc:
        wez.send_text(3, "ls", enter=True)
    assert rc.call_args[0][0][-1] == "ls\r"


def test_read_text_start_line_negativo_e_tira_vazias():
    with mock.patch.object(wez, "run_cli", return_value="a\nb\nc\n\n  \n") as rc:
        assert wez.read_text(4, lines=2) == "b\nc"
    rc.assert_called_once_with(["get-text", "--pane-id", "4", "--start-line", "-2"])


def test_read_text_lines_invalido():
    with pytest.raises(wez.WezError, match="lines"):
        wez.read_text(4, lines=0)


def test_main_send_resolve_nome_e_junta_texto():
    with mock.patch.object(wez, "resolve_pane", return_value=7) as rp, \
         mock.patch.object(wez, "send_text") as st:
        assert wez.main(["send", "kf-bugs", "--enter", "git", "status"]) == 0
    rp.assert_called_once_with("kf-bugs")
    st.assert_called_once_with(7, "git status", enter=True)


def test_main_send_stdin():
    with mock.patch.object(wez, "resolve_pane", return_value=7), \
         mock.patch.object(wez, "send_text") as st, \
         mock.patch.object(wez.sys, "stdin", mock.Mock(read=lambda: "linha1\nlinha2")):
        assert wez.main(["send", "x", "-"]) == 0
    st.assert_called_once_with(7, "linha1\nlinha2", enter=False)


def test_main_read_imprime(capsys):
    with mock.patch.object(wez, "resolve_pane", return_value=7), \
         mock.patch.object(wez, "read_text", return_value="out") as rt:
        assert wez.main(["read", "x", "--lines", "5"]) == 0
    rt.assert_called_once_with(7, 5)
    assert capsys.readouterr().out == "out\n"


def test_main_read_painel_ausente_rc_1(capsys):
    with mock.patch.object(wez, "list_panes", return_value=[]):
        assert wez.main(["read", "nada"]) == 1
    assert "não encontrado" in capsys.readouterr().err


# --- cfg (wezterm-wez-cfg-2026-11-10) ---

def _cfg(tmp_path, *argv):
    return wez.main(["cfg", argv[0], "--config-dir", str(tmp_path / "cfg"), "--repo", str(tmp_path / "repo"), *argv[1:]])


@pytest.fixture
def pastas(tmp_path):
    (tmp_path / "cfg" / "lib").mkdir(parents=True)
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    (tmp_path / "cfg" / "wezterm.lua").write_bytes(b"return {}\r\n")
    (tmp_path / "repo" / "wezterm.lua").write_bytes(b"return {}\n")
    (tmp_path / "cfg" / "lib" / "keys.lua").write_bytes(b"-- k\r\n")
    (tmp_path / "repo" / "velho.lua").write_bytes(b"x")
    (tmp_path / "repo" / ".git" / "HEAD").write_bytes(b"ref")
    return tmp_path


def test_config_errors_deteta_config_partida(tmp_path):
    f = tmp_path / "w.lua"
    f.write_text("return {")
    err = "14:12 ERROR wezterm_gui > syntax error: near <eof>\n"
    with mock.patch.object(wez.subprocess, "run", return_value=_done(err=err)) as run:
        erros = wez.config_errors(str(f))
    assert erros and "syntax error" in erros[0]
    assert run.call_args.args[0][1:] == ["--config-file", str(f), "ls-fonts"]


def test_config_errors_ok_e_rc_nao_zero(tmp_path):
    f = tmp_path / "w.lua"
    f.write_text("return {}")
    with mock.patch.object(wez.subprocess, "run", return_value=_done(err=" WARN  algo\n")):
        assert wez.config_errors(str(f)) == []
    with mock.patch.object(wez.subprocess, "run", return_value=_done(rc=3, err="falhou")):
        assert "rc 3" in wez.config_errors(str(f))[0]


def test_config_errors_ficheiro_inexistente(tmp_path):
    assert "não existe" in wez.config_errors(str(tmp_path / "nada.lua"))[0]


def test_cfg_check_rc(tmp_path, capsys):
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "wezterm.lua").write_text("return {")
    with mock.patch.object(wez.subprocess, "run", return_value=_done(err="ERROR boom\n")):
        assert _cfg(tmp_path, "check") == 1
    assert "config partida" in capsys.readouterr().out
    with mock.patch.object(wez.subprocess, "run", return_value=_done()):
        assert _cfg(tmp_path, "check") == 0


def test_files_diff_em_bytes_ignora_git(pastas):
    so_cfg, so_repo, dif = wez.files_diff(str(pastas / "cfg"), str(pastas / "repo"))
    assert so_cfg == ["lib/keys.lua"]
    assert so_repo == ["velho.lua"]
    assert dif == ["wezterm.lua"]  # só o fim de linha difere: CRLF conta


def test_cfg_diff_pastas_diferentes(pastas, capsys):
    assert _cfg(pastas, "diff") == 1
    out = capsys.readouterr().out
    assert "+ lib/keys.lua" in out and "- velho.lua" in out and "~ wezterm.lua" in out


def test_sync_copy_preserva_crlf_e_nao_apaga(pastas):
    git = mock.patch.object(wez, "git_state", return_value={"sujos": [], "frente": 0, "atras": 0})
    with git:
        assert _cfg(pastas, "sync") == 0
    assert (pastas / "repo" / "wezterm.lua").read_bytes() == b"return {}\r\n"
    assert (pastas / "repo" / "lib" / "keys.lua").read_bytes() == b"-- k\r\n"
    assert (pastas / "repo" / "velho.lua").exists()
    assert wez.files_diff(str(pastas / "cfg"), str(pastas / "repo"))[2] == []


def test_cfg_diff_mesma_pasta_usa_git(tmp_path, capsys):
    saidas = {"status": " M lib/keys.lua\n", "rev-list": "2\t0\n"}
    def fake(cmd, **kw):
        return _done(out=saidas[cmd[3]])
    with mock.patch.object(wez.subprocess, "run", side_effect=fake):
        rc = wez.main(["cfg", "diff", "--config-dir", str(tmp_path)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "M lib/keys.lua" in out and "2 commit(s) à frente" in out


def _git_fake(chamadas, frente="1", sujo=""):
    saidas = {"status": sujo, "rev-list": f"{frente}\t0\n", "log": "abc fix\n", "push": ""}
    def fake(cmd, **kw):
        chamadas.append(cmd[3])
        return _done(out=saidas[cmd[3]])
    return fake


def test_sync_push_so_com_confirmacao(tmp_path, capsys):
    ch = []
    with mock.patch.object(wez.subprocess, "run", side_effect=_git_fake(ch)), \
         mock.patch.object(wez, "_confirm", return_value=False):
        assert wez.main(["cfg", "sync", "--config-dir", str(tmp_path), "--push"]) == 1
    assert "push" not in ch and "push cancelado" in capsys.readouterr().out
    ch.clear()
    with mock.patch.object(wez.subprocess, "run", side_effect=_git_fake(ch)), \
         mock.patch.object(wez, "_confirm", return_value=True):
        assert wez.main(["cfg", "sync", "--config-dir", str(tmp_path), "--push"]) == 0
    assert ch[-1] == "push"


def test_sync_push_recusa_repo_sujo_e_sem_push_nao_envia(tmp_path):
    ch = []
    with mock.patch.object(wez.subprocess, "run", side_effect=_git_fake(ch, sujo=" M a\n")), \
         mock.patch.object(wez, "_confirm", return_value=True):
        assert wez.main(["cfg", "sync", "--config-dir", str(tmp_path), "--push"]) == 1
    assert "push" not in ch
    ch.clear()
    with mock.patch.object(wez.subprocess, "run", side_effect=_git_fake(ch)):
        assert wez.main(["cfg", "sync", "--config-dir", str(tmp_path)]) == 0
    assert "push" not in ch


def test_confirm_eof_e_nao(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _p: (_ for _ in ()).throw(EOFError))
    assert wez._confirm("?") is False
    monkeypatch.setattr("builtins.input", lambda _p: "s")
    assert wez._confirm("?") is True


# --- layout (wezterm-wez-layout-2026-11-10) ---

LAY = {"titulo": "t", "paineis": [
    {"nome": "a", "cwd": "~/x"},
    {"nome": "b", "cmd": "pwsh", "split": {"dir": "right", "percent": 30}},
    {"nome": "c", "split": {"de": "a", "dir": "bottom"}},
]}


def test_validate_layout_normaliza_defeitos():
    lay = wez.validate_layout(LAY, "dev")
    assert lay["titulo"] == "t" and lay["janela_nova"] is False
    a, b, c = lay["paineis"]
    assert a["split"] is None and a["cmd"] == []
    assert b["cmd"] == ["pwsh"] and b["split"] == {"de": "a", "dir": "right", "percent": 30}
    assert c["split"] == {"de": "a", "dir": "bottom", "percent": 50}


@pytest.mark.parametrize("data,msg", [
    ([], "objeto"),
    ({"paineis": []}, "não vazia"),
    ({"paineis": [{"cwd": "x"}]}, "falta 'nome'"),
    ({"paineis": [{"nome": "a"}, {"nome": "a"}]}, "repetido"),
    ({"paineis": [{"nome": "a", "split": {"dir": "right"}}]}, "primeiro"),
    ({"paineis": [{"nome": "a"}, {"nome": "b", "split": {"de": "z"}}]}, "não é um painel anterior"),
    ({"paineis": [{"nome": "a"}, {"nome": "b", "split": {"dir": "cima"}}]}, "'dir'"),
    ({"paineis": [{"nome": "a"}, {"nome": "b", "split": {"percent": 100}}]}, "'percent'"),
    ({"paineis": [{"nome": "a", "cmd": 3}]}, "'cmd'"),
])
def test_validate_layout_erros(data, msg):
    with pytest.raises(wez.WezError, match=msg):
        wez.validate_layout(data)


def test_open_layout_sequencia_de_chamadas(monkeypatch):
    monkeypatch.setenv("HOME", "/h")
    monkeypatch.setenv("USERPROFILE", "/h")
    respostas = iter(["10\n", "", "11\n", "12\n"])
    chamadas = []
    def fake(args):
        chamadas.append(args)
        return next(respostas)
    monkeypatch.setattr(wez, "run_cli", fake)
    ids = wez.open_layout(wez.validate_layout(LAY))
    assert ids == {"a": "10", "b": "11", "c": "12"}
    assert chamadas[0][:2] == ["spawn", "--cwd"] and chamadas[0][2].endswith("x")
    assert chamadas[1] == ["set-tab-title", "--pane-id", "10", "t"]
    assert chamadas[2] == ["split-pane", "--pane-id", "10", "--right", "--percent", "30", "--", "pwsh"]
    assert chamadas[3] == ["split-pane", "--pane-id", "10", "--bottom", "--percent", "50"]


def test_open_layout_janela_nova_e_id_invalido(monkeypatch):
    monkeypatch.setattr(wez, "run_cli", lambda args: "erro")
    lay = wez.validate_layout({"janela_nova": True, "paineis": [{"nome": "a"}]})
    with pytest.raises(wez.WezError, match="spawn não devolveu"):
        wez.open_layout(lay)


def test_load_layout_e_ls(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WEZ_LAYOUTS_DIR", str(tmp_path))
    (tmp_path / "ok.json").write_text(json.dumps(LAY), encoding="utf-8")
    (tmp_path / "mau.json").write_text("{", encoding="utf-8")
    assert wez.list_layouts() == ["mau", "ok"]
    assert wez.load_layout("ok")["titulo"] == "t"
    with pytest.raises(wez.WezError, match="JSON inválido"):
        wez.load_layout("mau")
    with pytest.raises(wez.WezError, match="não existe"):
        wez.load_layout("nada")
    with pytest.raises(wez.WezError, match="inválido"):
        wez.load_layout("../x")
    assert wez.main(["layout", "ls"]) == 0
    out = capsys.readouterr().out
    assert "3 painéis" in out and "INVÁLIDO" in out


def test_main_layout_open(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WEZ_LAYOUTS_DIR", str(tmp_path))
    (tmp_path / "um.json").write_text(json.dumps({"paineis": [{"nome": "a"}]}), encoding="utf-8")
    monkeypatch.setattr(wez, "run_cli", lambda args: "7\n")
    assert wez.main(["layout", "open", "um"]) == 0
    assert "7  a" in capsys.readouterr().out


def test_exemplo_dev_valido():
    lay = wez.load_layout("dev", str(Path(__file__).with_name("wez-layouts")))
    assert [p["nome"] for p in lay["paineis"]] == ["vault", "atlas", "michi"]
