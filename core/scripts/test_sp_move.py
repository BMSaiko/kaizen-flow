"""Testes de scripts/sp-move.py (fixtures em ficheiros temporários)."""
import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("sp_move", Path(__file__).with_name("sp-move.py"))
sp_move = importlib.util.module_from_spec(_spec)
sys.modules["sp_move"] = sp_move
_spec.loader.exec_module(sp_move)


def make_sp(root, rel, slug, status="TODO", project="atlas", body="# corpo\r\nlinha 2\r\n"):
    path = root / rel / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    head = f"---\nstatus: {status}\ncreated: 2026-10-01T10:00:00Z\nupdated: 2026-10-01T10:00:00Z\nslug: {slug}\nproject: {project}\n---\n"
    path.write_bytes((head + body).encode("utf-8"))
    return path


def test_move_todo_para_doing_atualiza_pasta_status_e_updated(tmp_path):
    src = make_sp(tmp_path, "atlas/sp/TODO", "abc")
    msg = sp_move.move(tmp_path, "abc", "doing")
    dst = tmp_path / "atlas/sp/Doing/abc.md"
    assert not src.exists() and dst.exists()
    text = dst.read_text(encoding="utf-8")
    assert "status: Doing\n" in text
    assert "updated: 2026-10-01T10:00:00Z" not in text
    assert "created: 2026-10-01T10:00:00Z" in text
    assert msg.startswith("abc: TODO → Doing")


def test_move_preserva_corpo_byte_a_byte(tmp_path):
    make_sp(tmp_path, "atlas/sp/Doing", "abc", status="Doing", body="# corpo\r\nlinha 2\r\n\r\nfim")
    sp_move.move(tmp_path, "abc", "done")
    raw = (tmp_path / "atlas/sp/Done/abc.md").read_bytes()
    assert raw.endswith(b"# corpo\r\nlinha 2\r\n\r\nfim")


def test_ja_no_destino_nao_faz_nada(tmp_path):
    path = make_sp(tmp_path, "atlas/sp/Doing", "abc", status="Doing")
    before = path.read_bytes()
    msg = sp_move.move(tmp_path, "abc", "doing")
    assert path.read_bytes() == before
    assert "já está" in msg


def test_slug_inexistente(tmp_path):
    make_sp(tmp_path, "atlas/sp/TODO", "abc")
    with pytest.raises(sp_move.SpMoveError, match="não encontrado"):
        sp_move.move(tmp_path, "xyz", "doing")


def test_slug_ambiguo_lista_opcoes_e_project_resolve(tmp_path):
    make_sp(tmp_path, "atlas/sp/TODO", "abc", project="atlas")
    make_sp(tmp_path, "kaizen/sp/TODO", "abc", project="kaizen")
    with pytest.raises(sp_move.SpMoveError, match="ambíguo") as exc:
        sp_move.move(tmp_path, "abc", "doing")
    assert "atlas" in str(exc.value) and "kaizen" in str(exc.value)
    sp_move.move(tmp_path, "abc", "doing", project="kaizen")
    assert (tmp_path / "kaizen/sp/Doing/abc.md").exists()
    assert (tmp_path / "atlas/sp/TODO/abc.md").exists()


def test_destino_invalido(tmp_path):
    make_sp(tmp_path, "atlas/sp/TODO", "abc")
    with pytest.raises(sp_move.SpMoveError, match="destino"):
        sp_move.move(tmp_path, "abc", "arquivo")


def test_destino_ja_ocupado_nao_sobrescreve(tmp_path):
    make_sp(tmp_path, "atlas/sp/TODO", "abc")
    other = make_sp(tmp_path, "atlas/sp/Doing", "abc", status="Doing")
    before = other.read_bytes()
    with pytest.raises(sp_move.SpMoveError, match="ambíguo"):
        sp_move.move(tmp_path, "abc", "doing")
    assert other.read_bytes() == before


def make_child(root, folder, slug, deps="", parent="mae"):
    path = root / f"atlas/sp/{folder}/{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        f"---\nstatus: {folder}\ncreated: 2026-10-01T10:00:00Z\nupdated: 2026-10-01T10:00:00Z\nslug: {slug}\n"
        f"project: atlas\nparent: {parent}\n{deps}---\n# {slug}\n".encode("utf-8"))
    return path


def make_mae(root):
    path = root / "atlas/sp/TODO/mae.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        ("---\nstatus: TODO\ncreated: 2026-10-01T10:00:00Z\nupdated: 2026-10-01T10:00:00Z\nslug: mae\nproject: atlas\n"
         "kind: program\nchildren:\n  - slug: a\n    depends_on: []\n    state: Doing\n"
         "  - slug: b\n    depends_on: [a]\n    state: TODO\n---\n# mãe\n").encode("utf-8"))
    return path


def test_next_fecha_o_filho_e_abre_o_proximo_elegivel(tmp_path):
    mae = make_mae(tmp_path)
    make_child(tmp_path, "Doing", "a")
    make_child(tmp_path, "TODO", "b", deps="depends_on: [a]\n")
    out = sp_move.advance(tmp_path, "a", "atlas")
    assert (tmp_path / "atlas/sp/Done/a.md").exists()
    assert (tmp_path / "atlas/sp/Doing/b.md").exists()
    assert not (tmp_path / "atlas/sp/TODO/b.md").exists()
    text = mae.read_text(encoding="utf-8")
    assert "  - slug: a\n    depends_on: []\n    state: Done\n" in text
    assert "  - slug: b\n    depends_on: [a]\n    state: Doing\n" in text
    assert out.splitlines()[-1] == f"/michi {tmp_path / 'atlas/sp/Doing/b.md'}"


def test_next_sem_elegivel_nao_abre_nada_e_diz_o_que_aguarda(tmp_path):
    make_mae(tmp_path)
    make_child(tmp_path, "Doing", "a")
    make_child(tmp_path, "Doing", "x")
    make_child(tmp_path, "TODO", "b", deps="depends_on: [a, x]\n")
    out = sp_move.advance(tmp_path, "a", "atlas")
    assert (tmp_path / "atlas/sp/TODO/b.md").exists()
    assert "próximo elegível: nenhum (b aguarda: x)" in out


def test_next_nao_abre_segundo_filho_se_outro_ja_esta_em_doing(tmp_path):
    make_mae(tmp_path)
    make_child(tmp_path, "Doing", "a")
    make_child(tmp_path, "Doing", "x")
    make_child(tmp_path, "TODO", "b", deps="depends_on: [a]\n")
    out = sp_move.advance(tmp_path, "a", "atlas")
    assert (tmp_path / "atlas/sp/TODO/b.md").exists()
    assert "x já está em Doing" in out


def test_next_sem_parent_so_fecha(tmp_path):
    make_sp(tmp_path, "atlas/sp/Doing", "solto", status="Doing")
    out = sp_move.advance(tmp_path, "solto", "atlas")
    assert (tmp_path / "atlas/sp/Done/solto.md").exists()
    assert "/michi" not in out


def test_next_ultimo_filho_diz_programa_completo_e_nao_move_a_mae(tmp_path):
    mae = make_mae(tmp_path)
    make_child(tmp_path, "Done", "a")
    make_child(tmp_path, "Doing", "b", deps="depends_on: [a]\n")
    out = sp_move.advance(tmp_path, "b", "atlas")
    assert "programa completo: mae" in out
    assert mae.exists()


def test_main_next_exige_done(tmp_path, capsys):
    make_sp(tmp_path, "atlas/sp/TODO", "abc")
    assert sp_move.main(["--root", str(tmp_path), "abc", "doing", "--next"]) == 1
    assert "--next" in capsys.readouterr().err


def test_move_leva_as_provas_do_slug_e_deixa_as_de_outros(tmp_path):
    make_sp(tmp_path, "atlas/sp/Doing", "abc", status="Doing")
    proofs = tmp_path / "atlas/sp/Doing/proofs"
    proofs.mkdir()
    (proofs / "abc-fase1.png").write_bytes(b"x")
    (proofs / "outro-fase1.png").write_bytes(b"y")
    msg = sp_move.move(tmp_path, "abc", "done")
    assert (tmp_path / "atlas/sp/Done/proofs/abc-fase1.png").read_bytes() == b"x"
    assert (proofs / "outro-fase1.png").exists() and not (proofs / "abc-fase1.png").exists()
    assert "+1 provas" in msg


def test_move_sem_provas_nao_cria_pasta(tmp_path):
    make_sp(tmp_path, "atlas/sp/Doing", "abc", status="Doing")
    sp_move.move(tmp_path, "abc", "done")
    assert not (tmp_path / "atlas/sp/Done/proofs").exists()


# --- claim de SP por agente (worktrees) ---
import os
import subprocess

_GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def _agent_worktree(tmp_path, name="alfa"):
    vault = tmp_path / "vault"
    vault.mkdir()
    for args in (["init", "-b", "master"], ["commit", "--allow-empty", "-m", "base"]):
        subprocess.run(["git", "-C", str(vault), *args], check=True, capture_output=True, env=_GIT_ENV)
    subprocess.run(["git", "-C", str(vault), "worktree", "add", "-b", f"agent/{name}", str(tmp_path / "wt"), "master"],
                   check=True, capture_output=True, env=_GIT_ENV)
    return vault, tmp_path / "wt"


@pytest.mark.skipif(not Path(__file__).with_name("sb-agent.py").exists(), reason="claims precisam do sb-agent.py (só no vault)")
def test_doing_num_worktree_reclama_o_sp(tmp_path, monkeypatch):
    vault, wt = _agent_worktree(tmp_path)
    sps = tmp_path / "sps"
    make_sp(sps, "atlas/sp/TODO", "abc")
    monkeypatch.chdir(wt)
    sp_move.move(sps, "abc", "doing")
    assert (vault / ".git" / "sb-claims" / "abc.lock").read_text(encoding="utf-8").strip() == "alfa"


@pytest.mark.skipif(not Path(__file__).with_name("sb-agent.py").exists(), reason="claims precisam do sb-agent.py (só no vault)")
def test_doing_num_worktree_falha_se_outro_agente_reclamou(tmp_path, monkeypatch):
    vault, wt = _agent_worktree(tmp_path)
    claims = vault / ".git" / "sb-claims"
    claims.mkdir()
    (claims / "abc.lock").write_text("beta\n", encoding="utf-8")
    sps = tmp_path / "sps"
    src = make_sp(sps, "atlas/sp/TODO", "abc")
    monkeypatch.chdir(wt)
    with pytest.raises(sp_move.SpMoveError, match="beta"):
        sp_move.move(sps, "abc", "doing")
    assert src.exists()


def test_done_num_worktree_liberta_o_claim(tmp_path, monkeypatch):
    vault, wt = _agent_worktree(tmp_path)
    sps = tmp_path / "sps"
    make_sp(sps, "atlas/sp/TODO", "abc")
    monkeypatch.chdir(wt)
    sp_move.move(sps, "abc", "doing")
    sp_move.move(sps, "abc", "done")
    assert not (vault / ".git" / "sb-claims" / "abc.lock").exists()


def test_doing_fora_de_worktree_nao_exige_claim(tmp_path, monkeypatch):
    vault, _ = _agent_worktree(tmp_path)
    sps = tmp_path / "sps"
    make_sp(sps, "atlas/sp/TODO", "abc")
    monkeypatch.chdir(vault)
    sp_move.move(sps, "abc", "doing")
    assert not (vault / ".git" / "sb-claims" / "abc.lock").exists()


def test_erro_nao_encontrado_sugere_sp_list(tmp_path):
    with pytest.raises(sp_move.SpMoveError, match="sp-list.py"):
        sp_move.move(tmp_path, "nada", "doing")


def test_next_sem_done_sugere_correcao(tmp_path, capsys):
    make_sp(tmp_path, "atlas/sp/TODO", "abc")
    rc = sp_move.main(["--root", str(tmp_path), "abc", "doing", "--next"])
    assert rc == 1 and "done --next" in capsys.readouterr().err


def test_alias_slug_flag(tmp_path):
    make_sp(tmp_path, "atlas/sp/TODO", "abc")
    assert sp_move.main(["--root", str(tmp_path), "--slug", "abc", "doing"]) == 0
    assert (tmp_path / "atlas/sp/Doing/abc.md").exists()


# --- arranque: filho + cadeia de mães para Doing ---
def make_mae_todo(root, slug="mae", parent=None):
    path = root / f"atlas/sp/TODO/{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    par = f"parent: {parent}\n" if parent else ""
    path.write_bytes(
        (f"---\nstatus: TODO\ncreated: 2026-10-01T10:00:00Z\nupdated: 2026-10-01T10:00:00Z\nslug: {slug}\nproject: atlas\n"
         f"{par}kind: program\nchildren:\n  - slug: a\n    depends_on: []\n    state: TODO\n---\n# mãe\n").encode("utf-8"))
    return path


def test_start_sp_simples_vai_para_doing(tmp_path):
    make_sp(tmp_path, "atlas/sp/TODO", "abc")
    out = sp_move.start(tmp_path, "abc", "atlas")
    assert (tmp_path / "atlas/sp/Doing/abc.md").exists()
    assert "abc: TODO → Doing" in out


def test_start_filho_com_mae_em_todo_deixa_ambos_em_doing(tmp_path):
    make_mae_todo(tmp_path)
    make_child(tmp_path, "TODO", "a")
    sp_move.start(tmp_path, "a", "atlas")
    assert (tmp_path / "atlas/sp/Doing/a.md").exists()
    assert (tmp_path / "atlas/sp/Doing/mae.md").exists()
    assert not (tmp_path / "atlas/sp/TODO/mae.md").exists()


def test_start_sobe_a_cadeia_de_ancestrais(tmp_path):
    make_mae_todo(tmp_path, "avo")
    make_mae_todo(tmp_path, "mae", parent="avo")
    make_child(tmp_path, "TODO", "a")
    sp_move.start(tmp_path, "a", "atlas")
    for slug in ("a", "mae", "avo"):
        assert (tmp_path / f"atlas/sp/Doing/{slug}.md").exists()


def test_start_mae_ja_em_doing_ou_done_nao_muda(tmp_path):
    mae = make_mae_todo(tmp_path)
    mae.unlink()
    mae_doing = tmp_path / "atlas/sp/Doing/mae.md"
    mae_doing.parent.mkdir(parents=True, exist_ok=True)
    mae_doing.write_bytes(b"---\nstatus: Doing\ncreated: 2026-10-01T10:00:00Z\nupdated: 2026-10-01T10:00:00Z\nslug: mae\nproject: atlas\nkind: program\n---\n# mae\n")
    before = mae_doing.read_bytes()
    make_child(tmp_path, "TODO", "a")
    sp_move.start(tmp_path, "a", "atlas")
    assert mae_doing.read_bytes() == before
    assert (tmp_path / "atlas/sp/Doing/a.md").exists()


def test_start_e_idempotente(tmp_path):
    make_mae_todo(tmp_path)
    make_child(tmp_path, "TODO", "a")
    sp_move.start(tmp_path, "a", "atlas")
    snap = {p: p.read_bytes() for p in (tmp_path / "atlas/sp/Doing").glob("*.md")}
    out = sp_move.start(tmp_path, "a", "atlas")
    assert {p: p.read_bytes() for p in (tmp_path / "atlas/sp/Doing").glob("*.md")} == snap
    assert "já está" in out


def test_start_nao_move_os_irmaos(tmp_path):
    make_mae_todo(tmp_path)
    make_child(tmp_path, "TODO", "a")
    make_child(tmp_path, "TODO", "b")
    sp_move.start(tmp_path, "a", "atlas")
    assert (tmp_path / "atlas/sp/TODO/b.md").exists()


def test_main_start_via_cli(tmp_path):
    make_mae_todo(tmp_path)
    make_child(tmp_path, "TODO", "a")
    assert sp_move.main(["--root", str(tmp_path), "a", "--start"]) == 0
    assert (tmp_path / "atlas/sp/Doing/mae.md").exists()
