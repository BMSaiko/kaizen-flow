"""Testes do handoff com socket do WezTerm morto e painel inexistente (run injetado; sem WezTerm real)."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff_pane as hp  # noqa: E402
from sp_carregar import carregar  # noqa: E402

handoff = carregar(Path(__file__).with_name("handoff.py"), "handoff_sock", fresco=True)


class _Res:
    def __init__(self, stdout):
        self.stdout = stdout


def _gui(vivos):
    """run falso: `list` responde conforme o WEZTERM_UNIX_SOCKET do env; socket fora de `vivos` = morto."""
    chamadas = []

    def run(argv, **k):
        sock = (k.get("env") or {}).get("WEZTERM_UNIX_SOCKET", "")
        chamadas.append((argv, sock))
        if sock not in vivos:
            raise hp.HandoffError("inacessível")
        return _Res(json.dumps([{"pane_id": n} for n in vivos[sock]]))
    return run, chamadas


def _ambiente(tmp_path, n_vivos=2):
    d = tmp_path / ".local" / "share" / "wezterm"
    d.mkdir(parents=True)
    morto = d / "gui-sock-1"
    socks = []
    for n in range(2, 2 + n_vivos):
        f = d / f"gui-sock-{n}"
        f.write_text("")
        os.utime(f, (1000 + n, 1000 + n))
        socks.append(str(f))
    env = {"USERPROFILE": str(tmp_path), "WEZTERM_UNIX_SOCKET": str(morto), "WEZTERM_PANE": "36"}
    return env, socks


def test_live_socket_prefere_o_atual_se_vivo(tmp_path):
    env, socks = _ambiente(tmp_path)
    run, _ = _gui({env["WEZTERM_UNIX_SOCKET"]: [36], socks[1]: [0]})
    assert hp.live_socket(env, run) == env["WEZTERM_UNIX_SOCKET"]


def test_live_socket_morto_escolhe_o_vivo_mais_recente(tmp_path):
    env, socks = _ambiente(tmp_path)
    run, _ = _gui({socks[0]: [0], socks[1]: [0]})
    assert hp.live_socket(env, run) == socks[1]  # mtime maior


def test_live_socket_sem_nenhum_vivo(tmp_path):
    env, _ = _ambiente(tmp_path)
    run, _c = _gui({})
    assert hp.live_socket(env, run) is None


def test_launch_socket_morto_usa_o_vivo_e_passa_ao_send(tmp_path, monkeypatch):
    env, socks = _ambiente(tmp_path, 1)
    run, chamadas = _gui({socks[0]: [36, 0]})
    lancado = {}
    monkeypatch.setattr(handoff.pane_lib, "launch_detached", lambda s, a, e=None: lancado.update(args=a, env=e) or a)
    handoff.launch("h/x.md", env=env, run=run)
    assert lancado["env"]["WEZTERM_UNIX_SOCKET"] == socks[0]
    assert lancado["args"][-2:] == ["--socket", socks[0]]
    assert all("send-text" not in a for a, _ in chamadas)


def test_launch_painel_ausente_nao_envia_nada(tmp_path, monkeypatch):
    env, socks = _ambiente(tmp_path, 1)
    run, chamadas = _gui({socks[0]: [0]})
    monkeypatch.setattr(handoff.pane_lib, "launch_detached", lambda *a, **k: pytest.fail("não deve lançar"))
    with pytest.raises(hp.HandoffError, match=r"painel 36 não existe no WezTerm \(janela fechada\?\).*--consume"):
        handoff.launch("h/x.md", env=env, run=run)
    assert all("send-text" not in a for a, _ in chamadas)


def test_launch_sem_gui_vivo_da_mensagem_com_consume(tmp_path):
    env, _ = _ambiente(tmp_path)
    run, _c = _gui({})
    with pytest.raises(hp.HandoffError, match=r'nenhum GUI do WezTerm vivo.*--consume "h/x.md"'):
        handoff.launch("h/x.md", env=env, run=run)


def test_send_text_usa_sempre_o_painel_pedido():
    vistos = []
    run = lambda argv, **k: vistos.append(argv) or _Res("")  # noqa: E731
    hp.send_lines(["/clear", "x"], 36, hp.send_argv, hp.enter_argv, run=run, sleep=lambda s: None)
    assert vistos and all(a[a.index("--pane-id") + 1] == "36" for a in vistos)


def test_send_destacado_exporta_o_socket(monkeypatch):
    monkeypatch.setattr(handoff, "send", lambda *a, **k: None)
    monkeypatch.delenv("WEZTERM_UNIX_SOCKET", raising=False)
    assert handoff.main(["--send", "h/x.md", "--pane", "3", "--socket", "S"]) == 0
    assert os.environ.pop("WEZTERM_UNIX_SOCKET") == "S"
