"""Testes de scripts/michi-checkpoint.py (repo git temporário)."""
import subprocess
from pathlib import Path

import pytest
from sp_carregar import carregar  # noqa: E402

mc = carregar(Path(__file__).with_name("michi-checkpoint.py"), "michi_checkpoint", fresco=True)


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    git(r, "config", "core.autocrlf", "false")
    (r / "a.txt").write_text("a0", encoding="utf-8")
    (r / "b.txt").write_text("b0", encoding="utf-8")
    (r / "c.txt").write_text("c0", encoding="utf-8")
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "init")
    return r


@pytest.fixture
def store(tmp_path):
    return tmp_path / "store"


def read(repo, name):
    return (repo / name).read_text(encoding="utf-8")


def test_restaura_alteracao_criacao_e_apagamento(repo, store):
    mc.save(repo, store, "s")
    (repo / "a.txt").write_text("a1", encoding="utf-8")
    (repo / "novo.txt").write_text("n", encoding="utf-8")
    (repo / "b.txt").unlink()
    done = mc.restore(repo, store, "s")
    assert read(repo, "a.txt") == "a0" and read(repo, "b.txt") == "b0"
    assert not (repo / "novo.txt").exists()
    assert sorted(done) == ["a.txt", "b.txt", "novo.txt"]


def test_nao_toca_em_ficheiros_que_o_michi_nao_tocou(repo, store):
    (repo / "c.txt").write_text("c-user", encoding="utf-8")
    (repo / "user.txt").write_text("meu", encoding="utf-8")
    mc.save(repo, store, "s")
    (repo / "a.txt").write_text("a1", encoding="utf-8")
    mc.restore(repo, store, "s")
    assert read(repo, "c.txt") == "c-user" and read(repo, "user.txt") == "meu"
    assert read(repo, "a.txt") == "a0"


def test_repo_sujo_antes_volta_ao_estado_sujo_do_checkpoint(repo, store):
    (repo / "a.txt").write_text("a-user", encoding="utf-8")
    mc.save(repo, store, "s")
    (repo / "a.txt").write_text("a-michi", encoding="utf-8")
    mc.restore(repo, store, "s")
    assert read(repo, "a.txt") == "a-user"


def test_ficheiro_apagado_antes_do_checkpoint_continua_apagado(repo, store):
    (repo / "b.txt").unlink()
    mc.save(repo, store, "s")
    (repo / "b.txt").write_text("michi", encoding="utf-8")
    mc.restore(repo, store, "s")
    assert not (repo / "b.txt").exists()


def test_sem_alteracoes_nada_a_restaurar(repo, store):
    mc.save(repo, store, "s")
    assert mc.restore(repo, store, "s") == []


def test_only_limita_o_restauro(repo, store):
    mc.save(repo, store, "s")
    (repo / "a.txt").write_text("a1", encoding="utf-8")
    (repo / "b.txt").write_text("b1", encoding="utf-8")
    assert mc.restore(repo, store, "s", only=["a.txt"]) == ["a.txt"]
    assert read(repo, "b.txt") == "b1"


def test_dry_run_nao_escreve(repo, store):
    mc.save(repo, store, "s")
    (repo / "a.txt").write_text("a1", encoding="utf-8")
    (repo / "novo.txt").write_text("n", encoding="utf-8")
    assert sorted(mc.restore(repo, store, "s", apply=False)) == ["a.txt", "novo.txt"]
    assert read(repo, "a.txt") == "a1" and (repo / "novo.txt").exists()


def test_save_numera_e_list_mostra(repo, store):
    assert mc.save(repo, store, "s") == 1
    assert mc.save(repo, store, "s") == 2
    assert mc.save(repo, store, "outro") == 1
    assert [c["n"] for c in mc.list_checkpoints(store, "s")] == [1, 2]


def test_restore_usa_o_ultimo_ou_o_n_indicado(repo, store):
    mc.save(repo, store, "s")
    (repo / "a.txt").write_text("a1", encoding="utf-8")
    mc.save(repo, store, "s")
    (repo / "a.txt").write_text("a2", encoding="utf-8")
    mc.restore(repo, store, "s")
    assert read(repo, "a.txt") == "a1"
    mc.restore(repo, store, "s", n=1)
    assert read(repo, "a.txt") == "a0"


def test_head_mudou_recusa(repo, store):
    mc.save(repo, store, "s")
    (repo / "a.txt").write_text("a1", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "x")
    with pytest.raises(mc.CheckpointError):
        mc.restore(repo, store, "s")


def test_sem_checkpoint_e_slug_invalido_recusam(repo, store):
    with pytest.raises(mc.CheckpointError):
        mc.restore(repo, store, "s")
    with pytest.raises(mc.CheckpointError):
        mc.save(repo, store, "../x")


def test_only_fora_do_repo_recusado(repo, store):
    mc.save(repo, store, "s")
    with pytest.raises(mc.CheckpointError):
        mc.restore(repo, store, "s", only=["../fora.txt"])


def test_cli_save_list_restore(repo, store, capsys):
    base = ["--repo", str(repo), "--dir", str(store), "--slug", "s"]
    assert mc.main(["save", *base]) == 0
    (repo / "a.txt").write_text("a1", encoding="utf-8")
    assert mc.main(["restore", *base]) == 0  # sem --apply: só mostra
    assert read(repo, "a.txt") == "a1"
    assert mc.main(["restore", *base, "--apply"]) == 0
    assert read(repo, "a.txt") == "a0"
    assert mc.main(["list", *base]) == 0
    assert "1" in capsys.readouterr().out
