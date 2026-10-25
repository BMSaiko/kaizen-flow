"""Testes de scripts/kaizen_hooks.py e kaizen_config.hooks()."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_config
import kaizen_hooks


@pytest.fixture(autouse=True)
def _log(tmp_path, monkeypatch):
    monkeypatch.setattr(kaizen_hooks, "LOG", tmp_path / "hooks.log")


def cfg(repo, *hooks):
    (repo / "kaizen-hooks.json").write_text(json.dumps({"hooks": list(hooks)}), encoding="utf-8")


def py(code):
    return f'"{sys.executable}" -c "{code}"'


def test_sem_config_nao_faz_nada(tmp_path):
    assert kaizen_hooks.fire("sp.created", {"slug": "a"}, repo=tmp_path) == []


def test_dispara_com_env_e_stdin(tmp_path):
    out = tmp_path / "out.txt"
    cmd = py("import os,sys;open(r'%s','w').write(os.environ['KAIZEN_SLUG']+sys.stdin.read())" % out)
    cfg(tmp_path, {"event": "sp.created", "cmd": cmd})
    kaizen_hooks.fire("sp.created", {"slug": "abc"}, repo=tmp_path)
    text = out.read_text()
    assert text.startswith("abc") and '"event": "sp.created"' in text


def test_bloqueante_aborta_na_pre(tmp_path):
    cfg(tmp_path, {"event": "sp.moved", "cmd": py("import sys;sys.exit(3)"), "modo": "bloqueante"})
    with pytest.raises(kaizen_hooks.HookBlocked):
        kaizen_hooks.fire("sp.moved", {}, repo=tmp_path, phase="pre")


def test_fases_separam_bloqueante_de_informativo(tmp_path):
    cfg(tmp_path,
        {"event": "sp.moved", "cmd": py("import sys;sys.exit(3)"), "modo": "bloqueante"},
        {"event": "sp.moved", "cmd": py("import sys;sys.exit(3)")})
    with pytest.raises(kaizen_hooks.HookBlocked):
        kaizen_hooks.fire("sp.moved", {}, repo=tmp_path, phase="pre")
    assert len(kaizen_hooks.fire("sp.moved", {}, repo=tmp_path, phase="post")) == 1


def test_informativo_falha_so_avisa(tmp_path):
    cfg(tmp_path, {"event": "michi.commit", "cmd": py("import sys;sys.exit(1)")})
    w = kaizen_hooks.fire("michi.commit", {}, repo=tmp_path)
    assert len(w) == 1 and "falhou" in w[0]


def test_timeout_bloqueante_aborta(tmp_path):
    cfg(tmp_path, {"event": "sp.moved", "cmd": py("import time;time.sleep(5)"), "modo": "bloqueante", "timeout": 0.5})
    with pytest.raises(kaizen_hooks.HookBlocked, match="timeout"):
        kaizen_hooks.fire("sp.moved", {}, repo=tmp_path, phase="pre")


def test_filtro_if(tmp_path):
    out = tmp_path / "o.txt"
    cmd = py("open(r'%s','w').write('x')" % out)
    cfg(tmp_path, {"event": "sp.moved", "cmd": cmd, "if": {"para": "Done"}})
    kaizen_hooks.fire("sp.moved", {"para": "Doing"}, repo=tmp_path)
    assert not out.exists()
    kaizen_hooks.fire("sp.moved", {"para": "Done"}, repo=tmp_path)
    assert out.exists()


def test_enabled_false_e_entradas_invalidas_ignoradas(tmp_path):
    cfg(tmp_path,
        {"event": "sp.moved", "cmd": "x", "enabled": False},
        {"event": "inexistente", "cmd": "x"},
        {"event": "sp.moved"},
        {"event": "sp.moved", "cmd": "x", "modo": "outro"},
        {"event": "sp.moved", "cmd": "x", "timeout": -1},
        "lixo")
    assert kaizen_config.hooks(tmp_path) == []


def test_config_corrompida_ignorada(tmp_path):
    (tmp_path / "kaizen-hooks.json").write_text("{nao json", encoding="utf-8")
    assert kaizen_hooks.fire("sp.created", {}, repo=tmp_path) == []


def test_cli_bloqueado_rc1(tmp_path, monkeypatch):
    cfg(tmp_path, {"event": "michi.closed", "cmd": py("import sys;sys.exit(2)"), "modo": "bloqueante"})
    monkeypatch.setenv("KAIZEN_REPO", str(tmp_path))
    assert kaizen_hooks.main(["fire", "michi.closed", "--slug", "a", "--phase", "pre"]) == 1
    assert kaizen_hooks.main(["fire", "michi.closed", "--slug", "a", "--phase", "post"]) == 0


def _load(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), Path(__file__).with_name(f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _sp(root, slug="abc"):
    p = root / "atlas/sp/TODO" / f"{slug}.md"
    p.parent.mkdir(parents=True)
    p.write_text(f"---\nstatus: TODO\ncreated: 2026-10-01T10:00:00Z\nupdated: 2026-10-01T10:00:00Z\nslug: {slug}\nproject: atlas\n---\n# x\n", encoding="utf-8")
    return p


def test_sp_move_bloqueado_nao_move(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    src = _sp(tmp_path / "sps")
    cfg(repo, {"event": "sp.moved", "cmd": py("import sys;sys.exit(1)"), "modo": "bloqueante", "if": {"para": "Doing"}})
    monkeypatch.setenv("KAIZEN_REPO", str(repo))
    sp_move = _load("sp-move")
    with pytest.raises(sp_move.SpMoveError, match="hook"):
        sp_move.move(tmp_path / "sps", "abc", "doing")
    assert src.exists()


def test_sp_move_informativo_corre_na_post(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _sp(tmp_path / "sps")
    out = tmp_path / "o.txt"
    cfg(repo, {"event": "sp.moved", "cmd": py("import os;open(r'%s','w').write(os.environ['KAIZEN_DE']+os.environ['KAIZEN_PARA'])" % out)})
    monkeypatch.setenv("KAIZEN_REPO", str(repo))
    _load("sp-move").move(tmp_path / "sps", "abc", "doing")
    assert out.read_text() == "TODODoing"
