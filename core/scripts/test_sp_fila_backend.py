"""Testes do backend de painéis no sp-fila e no spawn: presente, ausente (fallback sequencial) e escolhido por config."""
import json
import sys
import painel_backend as pb
import handoff_spawn as hs
from sp_fila_testlib import sp_fila


class _Res:
    def __init__(self, out=""):
        self.stdout = out


def _repo(tmp_path, cfg=None):
    if cfg is not None:
        (tmp_path / "kaizen.config.json").write_text(json.dumps({"painelBackend": cfg}), encoding="utf-8")
    return tmp_path


def test_backend_presente_deteta_wezterm(tmp_path):
    b, cfg = sp_fila.backend_paineis(_repo(tmp_path), env={"WEZTERM_PANE": "1"}, which=lambda n: n)
    assert cfg == "auto" and b.nome == "wezterm"


def test_backend_ausente_devolve_none(tmp_path):
    b, cfg = sp_fila.backend_paineis(_repo(tmp_path), env={}, which=lambda n: None)
    assert b is None and cfg == "auto"


def test_backend_por_config_background(tmp_path):
    b, cfg = sp_fila.backend_paineis(_repo(tmp_path, "background"), env={}, which=lambda n: None)
    assert cfg == "background" and b.nome == "background" and not b.interativo


def _main_com(monkeypatch, tmp_path, backend, cfg, extra=()):
    visto = {}
    monkeypatch.setattr(sp_fila, "backend_paineis", lambda *a, **k: (backend, cfg))

    def falso(root, estado, rel, slug=None):
        visto["estado"] = json.loads(estado.read_text(encoding="utf-8"))
        return {"acao": "fim", "motivo": "teste", "relatorio": "r"}

    monkeypatch.setattr(sp_fila, "seguinte", falso)
    rc = sp_fila.main(["--concorrencia", "2", *extra, "--estado", str(tmp_path / "e.json"), "--root", str(tmp_path / "sps"), "--relatorios", str(tmp_path / "rel")])
    return rc, visto


def test_main_sem_backend_cai_para_sequencial_com_aviso(monkeypatch, tmp_path, capsys):
    (tmp_path / "sps").mkdir()
    rc, visto = _main_com(monkeypatch, tmp_path, None, "auto")
    assert rc == 0
    assert visto["estado"]["concorrencia"] is None and visto["estado"]["max"] == sp_fila.MAX_DEFEITO
    assert "sem backend de painéis" in capsys.readouterr().err


def test_main_com_backend_mantem_paralelo(monkeypatch, tmp_path, capsys):
    (tmp_path / "sps").mkdir()
    rc, visto = _main_com(monkeypatch, tmp_path, pb.BackgroundBackend(tmp_path / "bg"), "background")
    assert rc == 0 and visto["estado"]["concorrencia"] == 2 and visto["estado"]["max"] is None
    assert "AVISO" not in capsys.readouterr().err


def test_spawn_background_corre_claude_p_sem_esperar_prompt(tmp_path, monkeypatch):
    abertos = []

    class Falso(pb.BackgroundBackend):
        def abrir(self, cmd, cwd):
            abertos.append((cmd, cwd))
            return "4242"

    monkeypatch.setattr(pb, "por_nome", lambda nome, run=None, estado_dir=None: Falso(tmp_path))
    run = lambda argv, **kw: _Res("aviso\nC:/wt/x\n")
    res = hs.spawn(["x"], backend="background", run=run, sleep=lambda s: None, registar=False)
    assert res[0]["ok"] and res[0]["painel"] == "4242"
    assert abertos == [(["claude", "-p", "/michi --auto x"], "C:/wt/x")]
