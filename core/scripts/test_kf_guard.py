"""Testes negativos: cada caso indesejado tem um teste que falha se a guarda for removida."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from sp_carregar import carregar  # noqa: E402

HERE = Path(__file__).resolve().parent
guard = carregar(HERE / "kf_guard.py", "kf_guard", fresco=True)
cfg = carregar(HERE / "kaizen_config.py", "kaizen_config", fresco=True)

VERDE = lambda repo: True  # noqa: E731
VERMELHO = lambda repo: False  # noqa: E731


@pytest.fixture(autouse=True)
def _log(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "LOG", tmp_path / "guard.log")


def bash(repo, cmd, ci=VERMELHO):
    return guard.avaliar("Bash", {"command": cmd}, repo, env={}, ci=ci)


# --- config
def test_protected_files_defeito_e_config(tmp_path):
    assert {"MEMORY.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md"} <= set(cfg.protected_files(tmp_path))
    (tmp_path / "kaizen.config.json").write_text(json.dumps({"protectedFiles": ["X.md", 3, " "]}))
    assert cfg.protected_files(tmp_path) == ["X.md"]
    (tmp_path / "kaizen.config.json").write_text(json.dumps({"protectedFiles": "nope"}))
    assert "AGENTS.md" in cfg.protected_files(tmp_path)


def test_repo_kaizen_config_lista_protegidos():
    repo = HERE.parent.parent
    data = json.loads((repo / "kaizen.config.json").read_text(encoding="utf-8"))
    assert {"MEMORY.md", "AGENTS.md", "CLAUDE.md"} <= set(data["protectedFiles"])


# --- ficheiros protegidos
@pytest.mark.parametrize("f", ["MEMORY.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md"])
def test_editar_protegido_sem_override_bloqueia(tmp_path, f):
    for tool in ("Write", "Edit"):
        r = guard.avaliar(tool, {"file_path": str(tmp_path / f)}, tmp_path, env={})
        assert r and "protegido" in r and f in r


def test_protegido_com_override_passa_e_regista(tmp_path):
    env = {"KAIZEN_ALLOW_PROTECTED": "pedido do BMS"}
    assert guard.avaliar("Edit", {"file_path": str(tmp_path / "AGENTS.md")}, tmp_path, env=env) is None
    assert "pedido do BMS" in guard.LOG.read_text()


def test_override_vazio_nao_conta(tmp_path):
    assert guard.avaliar("Edit", {"file_path": str(tmp_path / "AGENTS.md")}, tmp_path, env={"KAIZEN_ALLOW_PROTECTED": " "})


def test_ficheiro_normal_passa(tmp_path):
    assert guard.avaliar("Write", {"file_path": str(tmp_path / "a/b.md")}, tmp_path, env={}) is None


def test_protegido_em_subpasta_nao_e_o_da_raiz(tmp_path):
    assert guard.avaliar("Write", {"file_path": str(tmp_path / "docs/AGENTS.md")}, tmp_path, env={}) is None


# --- gate de diff
def _git(repo, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=repo, check=True, capture_output=True)


def _repo_com_ramo(tmp_path, ficheiro):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "x.txt").write_text("x")
    _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "checkout", "-qb", "ramo")
    (tmp_path / ficheiro).write_text("alterado")
    _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "muda")


def test_diff_com_protegido_falha(tmp_path, capsys):
    _repo_com_ramo(tmp_path, "CLAUDE.md")
    assert guard.cmd_diff(tmp_path, "main", env={}) == 1
    assert "CLAUDE.md" in capsys.readouterr().err


def test_diff_com_override_passa(tmp_path):
    _repo_com_ramo(tmp_path, "CLAUDE.md")
    assert guard.cmd_diff(tmp_path, "main", env={"KAIZEN_ALLOW_PROTECTED": "ok"}) == 0


def test_diff_sem_protegido_passa(tmp_path):
    _repo_com_ramo(tmp_path, "outro.md")
    assert guard.cmd_diff(tmp_path, "main", env={}) == 0


# --- segredos
@pytest.mark.parametrize("nome", [".env", ".env.local", "k.key", "c.pem", "id_rsa", "id_rsa.pub", "x.p12", "x.pfx", "secrets.json", ".secrets-x"])
def test_ler_segredo_via_tool_bloqueia(tmp_path, nome):
    assert guard.avaliar("Read", {"file_path": str(tmp_path / nome)}, tmp_path, env={})


@pytest.mark.parametrize("cmd", ["cat .env", "head -n1 config/.env.prod", "grep KEY id_rsa", "cat a && cat server.pem"])
def test_ler_segredo_via_bash_bloqueia(tmp_path, cmd):
    assert "segredos" in bash(tmp_path, cmd)


def test_ler_ficheiro_normal_passa(tmp_path):
    assert bash(tmp_path, "cat README.md") is None
    assert guard.avaliar("Read", {"file_path": str(tmp_path / "environment.md")}, tmp_path, env={}) is None


# --- force-push
@pytest.mark.parametrize("cmd", ["git push --force", "git push -f origin main", "git push --force-with-lease", "git push origin +main", "git -C x push -fu origin b"])
def test_force_push_bloqueia(tmp_path, cmd):
    assert bash(tmp_path, cmd)


def test_push_normal_passa(tmp_path):
    assert bash(tmp_path, "git push -u origin agent/x") is None


# --- --admin e merge com CI
def test_admin_bloqueia_mesmo_com_ci_verde(tmp_path):
    assert "--admin" in bash(tmp_path, "gh pr merge 5 --squash --admin", ci=VERDE)


def test_merge_com_ci_vermelho_bloqueia(tmp_path):
    assert "CI" in bash(tmp_path, "gh pr merge 5 --squash", ci=VERMELHO)


def test_merge_com_ci_verde_passa(tmp_path):
    assert bash(tmp_path, "gh pr merge 5 --squash", ci=VERDE) is None


def test_ci_verde_sem_gh_ou_checks_falha(tmp_path, monkeypatch):
    def sem_gh(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(guard.subprocess, "run", sem_gh)
    assert guard.ci_verde(tmp_path) is False

    class R:
        returncode, stdout = 0, json.dumps([{"state": "SUCCESS"}, {"state": "FAILURE"}])

    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: R)
    assert guard.ci_verde(tmp_path) is False
    R.stdout = json.dumps([{"state": "SUCCESS"}, {"state": "SKIPPED"}])
    assert guard.ci_verde(tmp_path) is True


# --- tag/publish
@pytest.mark.parametrize("cmd", ["git tag v1.0.0", "git tag -a v1 -m x", "git push --tags", "git push --follow-tags", "npm publish", "pnpm publish --access public", "gh release create v1"])
def test_tag_e_publish_bloqueiam(tmp_path, cmd):
    assert bash(tmp_path, cmd)


def test_listar_tags_passa(tmp_path):
    assert bash(tmp_path, "git tag --list") is None


# --- escrita fora da worktree
@pytest.mark.parametrize("tool", ["Write", "Edit"])
def test_escrita_fora_do_repo_bloqueia(tmp_path, tool):
    repo = tmp_path / "wt"
    repo.mkdir()
    assert "fora" in guard.avaliar(tool, {"file_path": str(Path.home() / "fora.txt")}, repo, env={})
    assert "fora" in guard.avaliar(tool, {"file_path": "/etc/fora.txt"}, repo, env={})


def test_escrita_dentro_passa(tmp_path):
    assert guard.avaliar("Write", {"file_path": str(tmp_path / "src/a.py")}, tmp_path, env={}) is None


# --- hook (processo real)
def _hook(tmp_path, payload, env_extra=None):
    import os
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path), **(env_extra or {})}
    env.pop("KAIZEN_ALLOW_PROTECTED", None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-I", str(HERE / "kf_guard.py")], input=json.dumps(payload), capture_output=True, text=True, env=env)


def test_hook_bloqueia_com_rc2_e_razao(tmp_path):
    r = _hook(tmp_path, {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "CLAUDE.md")}})
    assert r.returncode == 2 and "protegido" in r.stderr


def test_hook_permite_e_tolera_lixo(tmp_path):
    assert _hook(tmp_path, {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "a.md")}}).returncode == 0
    r = subprocess.run([sys.executable, "-I", str(HERE / "kf_guard.py")], input="{lixo", capture_output=True, text=True)
    assert r.returncode == 0


# --- regressão de gates (ratchet)
def test_ratchet_falha_com_regressao(tmp_path):
    ratchet = carregar(HERE / "quality-ratchet.py", "quality_ratchet", fresco=True)
    pior, _ = ratchet.comparar({"a.py": {"C901": 2}}, {"a.py": {"C901": 1}})
    assert pior == ["a.py C901: 1 -> 2"]
