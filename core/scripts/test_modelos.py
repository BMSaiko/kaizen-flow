"""Testes de scripts/modelos.py (config de modelo/effort por papel)."""
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "modelos.py"

BASE = {
    "papeis": {
        "sp-autor": {"model": "claude-opus-5-5", "effort": "medium"},
        "michi-exec": {"model": "claude-sonnet-5-5", "effort": "medium"},
        "michi-leve": {"model": "claude-haiku-5-5", "effort": "low"},
    },
    "aliases": {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5",
                "haiku": "claude-haiku-5-5", "fable": "claude-fable-5-1"},
}


@pytest.fixture
def cfg(tmp_path):
    p = tmp_path / "modelos.json"
    p.write_bytes(json.dumps(BASE, indent=2).encode() + b"\r\n")
    return p


def run(cfg, *args):
    """Corre modelos.main em-processo (a cobertura do pacote kf so mede o que corre aqui)."""
    spec = importlib.util.spec_from_file_location("modelos_sob_teste", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    err = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = mod.main(["--config", str(cfg), *args])
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else 1
    out.flush()
    err.flush()
    return rc or 0, out.buffer.getvalue().decode("utf-8").strip(), err.buffer.getvalue().decode("utf-8").strip()


def test_list(cfg):
    rc, out, _ = run(cfg, "list")
    assert rc == 0
    assert "michi-exec" in out and "claude-sonnet-5-5" in out and "low" in out


def test_get_e_json(cfg):
    assert run(cfg, "get", "sp-autor")[1] == "claude-opus-5-5"
    rc, out, _ = run(cfg, "get", "michi-leve", "--json")
    assert rc == 0 and json.loads(out) == {"model": "claude-haiku-5-5", "effort": "low"}


def test_args(cfg):
    assert run(cfg, "args", "michi-exec")[1] == "--model claude-sonnet-5-5 --effort medium"


def test_set_alias_preserva_resto_e_crlf(cfg):
    rc, _, _ = run(cfg, "set", "michi-exec", "fable")
    assert rc == 0
    assert run(cfg, "args", "michi-exec")[1] == "--model claude-fable-5-1 --effort medium"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["papeis"]["sp-autor"] == BASE["papeis"]["sp-autor"]
    assert data["aliases"] == BASE["aliases"]
    assert cfg.read_bytes().endswith(b"}\r\n")


def test_set_effort(cfg):
    rc, _, _ = run(cfg, "set", "sp-autor", "opus", "--effort", "high")
    assert rc == 0
    assert run(cfg, "args", "sp-autor")[1] == "--model claude-opus-5-5 --effort high"


def test_effort_invalido(cfg):
    rc, _, _ = run(cfg, "set", "sp-autor", "opus", "--effort", "turbo")
    assert rc == 2
    assert json.loads(cfg.read_text(encoding="utf-8")) == BASE


def test_papel_inexistente(cfg):
    assert run(cfg, "get", "nada")[0] == 2
    assert run(cfg, "set", "nada", "opus")[0] == 2


def test_modelo_desconhecido_avisa_e_grava(cfg):
    rc, _, err = run(cfg, "set", "michi-exec", "fable-5-2")
    assert rc == 0 and "aviso" in err
    assert run(cfg, "get", "michi-exec")[1] == "fable-5-2"


def test_id_completo_sem_aviso(cfg):
    rc, _, err = run(cfg, "set", "michi-exec", "claude-fable-5-2")
    assert rc == 0 and err == ""
    assert run(cfg, "get", "michi-exec")[1] == "claude-fable-5-2"


def test_config_inexistente(tmp_path):
    assert run(tmp_path / "nao.json", "list")[0] == 2


SKILL = (b"---\r\nname: super-prompt\r\nmodel: claude-haiku-5-5\r\ntriggers:\r\n- sp\r\n---\r\n"
         b"# corpo\r\nmodel: nao-mexer\r\n")
CMD = b"---\ndescription: atalho\n---\nInvoca model: x\n"


@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "SKILL.md").write_bytes(SKILL)
    (tmp_path / "s" / "cmd.md").write_bytes(CMD)
    data = dict(BASE, alvos={"sp-autor": ["s/SKILL.md", "s/cmd.md"]})
    p = tmp_path / ".claude" / "modelos.json"
    p.write_bytes(json.dumps(data, indent=2).encode() + b"\n")
    return p


def test_sync_escreve_frontmatter_e_preserva_resto(repo):
    root = repo.parent.parent
    assert run(repo, "sync", "--check")[0] == 1
    rc, out, _ = run(repo, "sync")
    assert rc == 0 and "s/SKILL.md" in out and "s/cmd.md" in out
    assert (root / "s" / "SKILL.md").read_bytes() == SKILL.replace(
        b"model: claude-haiku-5-5\r\n", b"model: claude-opus-5-5\r\n").replace(
        b"- sp\r\n---", b"- sp\r\neffort: medium\r\n---")
    assert (root / "s" / "cmd.md").read_bytes() == (
        b"---\ndescription: atalho\nmodel: claude-opus-5-5\neffort: medium\n---\nInvoca model: x\n")
    assert run(repo, "sync", "--check")[0] == 0


def test_set_corre_sync(repo):
    root = repo.parent.parent
    rc, out, _ = run(repo, "set", "sp-autor", "fable", "--effort", "high")
    assert rc == 0 and "sync:" in out
    for f in ("SKILL.md", "cmd.md"):
        raw = (root / "s" / f).read_bytes()
        assert b"model: claude-fable-5-1" in raw and b"effort: high" in raw
    assert run(repo, "sync", "--check")[0] == 0


def test_sync_alvo_em_falta(repo):
    (repo.parent.parent / "s" / "cmd.md").unlink()
    assert run(repo, "sync")[0] == 2


@pytest.mark.skipif(not (SCRIPT.parent / "sb.py").exists(), reason="sb.py só existe no vault (não no pacote kaizen-flow)")
def test_sb_models_encaminha(cfg):
    sb = SCRIPT.parent / "sb.py"
    r = subprocess.run([sys.executable, "-I", str(sb), "models", "--config", str(cfg), "get", "sp-autor"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "claude-opus-5-5"


# --- cadeia do sp-autor e níveis do michi ---

NOVO = {
    "papeis": {
        "sp-autor": {"model": "claude-fable-5-2", "effort": "medium",
                     "fallback": ["claude-fable-5-1", "claude-opus-5-5"]},
        "michi-exec": {"model": "claude-sonnet-5-5", "effort": "low"},
        "michi-leve": {"model": "claude-haiku-5-5", "effort": "low"},
        "michi-complexo": {"model": "claude-opus-5-5", "effort": "low"},
    },
    "michi_modelo": {"simples": "michi-leve", "default": "michi-exec", "complexo": "michi-complexo"},
    "aliases": {},
}


@pytest.fixture
def cfg_novo(tmp_path):
    p = tmp_path / "modelos.json"
    p.write_bytes(json.dumps(NOVO, indent=2).encode() + b"\n")
    return p


def test_cadeia_sp_autor(cfg_novo):
    rc, out, _ = run(cfg_novo, "get", "sp-autor", "--cadeia")
    assert rc == 0
    assert out.splitlines() == ["claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5"]


def test_cadeia_sem_fallback(cfg):
    rc, out, _ = run(cfg, "get", "michi-leve", "--cadeia")
    assert (rc, out) == (0, "claude-haiku-5-5")


def test_get_json_traz_fallback(cfg_novo):
    rc, out, _ = run(cfg_novo, "get", "sp-autor", "--json")
    d = json.loads(out)
    assert rc == 0 and d["effort"] == "medium"
    assert d["fallback"] == ["claude-fable-5-1", "claude-opus-5-5"]


@pytest.mark.parametrize("nivel,modelo", [("simples", "claude-haiku-5-5"),
                                          ("default", "claude-sonnet-5-5"),
                                          ("complexo", "claude-opus-5-5")])
def test_michi_niveis(cfg_novo, nivel, modelo):
    rc, out, _ = run(cfg_novo, "michi", nivel)
    assert (rc, out) == (0, modelo)
    rc, out, _ = run(cfg_novo, "michi", nivel, "--json")
    d = json.loads(out)
    assert d["model"] == modelo and d["effort"] == "low"


@pytest.mark.parametrize("nivel", ["xpto", ""])
def test_michi_nivel_invalido_resolve_default(cfg_novo, nivel):
    rc, out, err = run(cfg_novo, "michi", nivel)
    assert rc == 0 and out == "claude-sonnet-5-5"
    assert "aviso" in err


def test_michi_effort_sempre_low(tmp_path):
    d = json.loads(json.dumps(NOVO))
    for p in ("michi-exec", "michi-leve", "michi-complexo"):
        d["papeis"][p]["effort"] = "high"
    f = tmp_path / "m.json"
    f.write_bytes(json.dumps(d).encode())
    for nivel in ("simples", "default", "complexo"):
        rc, out, _ = run(f, "michi", nivel, "--json")
        assert json.loads(out)["effort"] == "low"


def test_json_antigo_sem_campos_novos(cfg):
    rc, out, _ = run(cfg, "michi", "default")
    assert (rc, out) == (0, "claude-sonnet-5-5")
    rc, out, err = run(cfg, "michi", "complexo")
    assert rc == 0 and out == "claude-sonnet-5-5" and "aviso" in err


def test_json_real_do_repo():
    real = Path(__file__).resolve().parent.parent / ".claude" / "modelos.json"
    if not real.exists():
        pytest.skip("sem .claude/modelos.json (pacote kf)")
    d = json.loads(real.read_bytes())
    assert d["papeis"]["michi-exec"]["effort"] == "low"
    assert d["papeis"]["michi-complexo"] == {"model": "claude-opus-5-5", "effort": "low"}
    assert d["michi_modelo"] == NOVO["michi_modelo"]
    assert d["papeis"]["sp-autor"]["effort"] == "medium"
