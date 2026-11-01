"""Fecho vs kaizen-flow: um SP que altera ficheiros ligados ao pacote não fecha com a cópia desatualizada."""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import kf_ligados  # noqa: E402

PROJECT = "demo"
FILL = "conteúdo de teste"


def run(script, *args, env=None):
    e = {**os.environ, **(env or {})}
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / script), *args],
                       capture_output=True, text=True, encoding="utf-8", env=e, cwd=tempfile.gettempdir())
    return r.returncode, r.stdout, r.stderr


@pytest.fixture
def cenario(tmp_path):
    """Vault com um SP em Doing, repo com scripts/wt_redirect.py novo e pacote kf falso em core/scripts."""
    vault = tmp_path / "vault"
    (vault / PROJECT).mkdir(parents=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "wt_redirect.py").write_text("# versão nova\n", encoding="utf-8")
    (repo / "outro.txt").write_text("x", encoding="utf-8")
    core = tmp_path / "pkg" / "core" / "scripts"
    core.mkdir(parents=True)
    (core / "wt_redirect.py").write_text("# versão nova\n", encoding="utf-8")
    gate = f'"{sys.executable}" -c "import sys; sys.exit(0)"'
    assert run("sp-new.py", "--root", str(vault), "--project", PROJECT, "--slug", "s1",
               "--priority", "P3", "--gate", gate)[0] == 0
    f = next((vault / PROJECT / "sp" / "TODO").glob("s1-*.md"))
    f.write_text(re.sub(r"(## \d\. [^\n]*\n)\n+", rf"\1\n{FILL}\n\n", f.read_text(encoding="utf-8")), encoding="utf-8")
    assert run("sp-move.py", "--root", str(vault), "--project", PROJECT, "s1", "doing")[0] == 0
    return tmp_path


def fechar(base, env=None):
    return run("sp-fechar.py", "--root", str(base / "vault"), "--project", PROJECT, "s1",
               "--sem-budget", "--commit-dir", str(base / "repo"),
               env={"KAIZEN_FLOW_HOME": str(base / "pkg"), **(env or {})})


def done(base):
    return list((base / "vault" / PROJECT / "sp" / "Done").glob("s1-*.md"))


def test_sem_ficheiros_kf_fecha(cenario):
    (cenario / "repo" / "scripts" / "wt_redirect.py").unlink()  # só sobra outro.txt
    (cenario / "pkg" / "core" / "scripts" / "wt_redirect.py").write_text("# diferente\n", encoding="utf-8")
    rc, out, err = fechar(cenario)
    assert rc == 0, out + err
    assert done(cenario)


def test_ficheiro_kf_em_sincronia_fecha(cenario):
    rc, out, err = fechar(cenario)
    assert rc == 0, out + err
    assert done(cenario)


def test_ficheiro_kf_fora_de_sincronia_bloqueia(cenario):
    (cenario / "pkg" / "core" / "scripts" / "wt_redirect.py").write_text("# desatualizado\n", encoding="utf-8")
    rc, out, err = fechar(cenario)
    assert rc == 1
    assert "/kaizen-sync" in out and "wt_redirect.py" in out
    assert not done(cenario)
    assert not list((cenario / "repo").glob("COMMIT_*.md"))


def test_sem_pacote_no_disco_nao_bloqueia(cenario):
    rc, out, err = fechar(cenario, env={"KAIZEN_FLOW_HOME": str(cenario / "nao-existe")})
    assert rc == 0, out + err


def test_ligados_e_fora_de_sincronia(cenario):
    core = cenario / "pkg" / "core" / "scripts"
    assert kf_ligados.core_dir(cenario / "pkg") == core
    assert kf_ligados.ligados(core) == ["wt_redirect.py"]
    assert kf_ligados.fora_de_sincronia(cenario / "repo" / "scripts", core) == []
    (core / "wt_redirect.py").write_text("# x\n", encoding="utf-8")
    assert kf_ligados.fora_de_sincronia(cenario / "repo" / "scripts", core) == ["wt_redirect.py"]
    assert kf_ligados.fora_de_sincronia(cenario / "repo" / "scripts", core, ["outro.py"]) == []
    assert kf_ligados.core_dir(cenario / "nada") is None
