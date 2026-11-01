"""Testes de scripts/sp-handoff.py (fixtures em ficheiros temporários)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("sp_handoff", Path(__file__).with_name("sp-handoff.py"))
sp_handoff = importlib.util.module_from_spec(_spec)
sys.modules["sp_handoff"] = sp_handoff
_spec.loader.exec_module(sp_handoff)


def make_sp(root, rel, slug, status="Doing", project="atlas", body="# Super Prompt\n\n## 1. Role\nx\n"):
    path = root / rel / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    head = f"---\nstatus: {status}\ncreated: 2026-10-01T10:00:00Z\nupdated: 2026-10-01T10:00:00Z\nslug: {slug}\nproject: {project}\n---\n"
    path.write_bytes((head + body).encode("utf-8"))
    return path


def test_resolve_unico_doing_sem_slug(tmp_path):
    make_sp(tmp_path, "atlas/sp/TODO", "a", status="TODO")
    doing = make_sp(tmp_path, "atlas/sp/Doing", "b")
    assert sp_handoff.resolve(tmp_path) == doing


def test_resolve_slug_explicito_entre_varios_doing(tmp_path):
    make_sp(tmp_path, "atlas/sp/Doing", "a")
    b = make_sp(tmp_path, "kaizen/sp/Doing", "b", project="kaizen")
    assert sp_handoff.resolve(tmp_path, "b") == b


def test_resolve_varios_doing_sem_slug_lista_opcoes(tmp_path):
    make_sp(tmp_path, "atlas/sp/Doing", "a")
    make_sp(tmp_path, "kaizen/sp/Doing", "b", project="kaizen")
    with pytest.raises(sp_handoff.HandoffError, match="vários") as exc:
        sp_handoff.resolve(tmp_path)
    assert "a (atlas)" in str(exc.value) and "b (kaizen)" in str(exc.value)


def test_resolve_nenhum_doing(tmp_path):
    make_sp(tmp_path, "atlas/sp/TODO", "a", status="TODO")
    with pytest.raises(sp_handoff.HandoffError, match="nenhum SP em Doing"):
        sp_handoff.resolve(tmp_path)


def test_resolve_slug_em_todo_resolve(tmp_path):
    todo = make_sp(tmp_path, "atlas/sp/TODO", "a", status="TODO")
    assert sp_handoff.resolve(str(tmp_path), "a") == todo.resolve()


def test_resolve_slug_em_done_recusa(tmp_path):
    make_sp(tmp_path, "atlas/sp/Done", "a", status="Done")
    with pytest.raises(sp_handoff.HandoffError, match="não está em TODO nem Doing"):
        sp_handoff.resolve(tmp_path, "a")


def test_resolve_devolve_caminho_absoluto(tmp_path):
    make_sp(tmp_path, "atlas/sp/Doing", "a")
    assert sp_handoff.resolve(tmp_path).is_absolute()


def test_write_acrescenta_seccao_e_atualiza_updated(tmp_path):
    path = make_sp(tmp_path, "atlas/sp/Doing", "a")
    before = path.read_text(encoding="utf-8")
    sp_handoff.write(path, "- feito: x\n", today="2026-10-17")
    after = path.read_text(encoding="utf-8")
    assert after.endswith("\n## Progresso (sessão 2026-10-17)\n\n- feito: x\n")
    assert before.split("---\n", 2)[2] in after
    assert "status: Doing\n" in after and "created: 2026-10-01T10:00:00Z\n" in after
    assert "updated: 2026-10-01T10:00:00Z" not in after


def test_write_mesma_data_substitui_so_a_seccao(tmp_path):
    path = make_sp(tmp_path, "atlas/sp/Doing", "a")
    sp_handoff.write(path, "primeira\n", today="2026-10-17")
    sp_handoff.write(path, "segunda\n", today="2026-10-17")
    text = path.read_text(encoding="utf-8")
    assert text.count("## Progresso (sessão 2026-10-17)") == 1
    assert "segunda" in text and "primeira" not in text
    assert "## 1. Role\nx\n" in text


def test_write_data_diferente_mantem_historico(tmp_path):
    path = make_sp(tmp_path, "atlas/sp/Doing", "a")
    sp_handoff.write(path, "ontem\n", today="2026-10-16")
    sp_handoff.write(path, "hoje\n", today="2026-10-17")
    text = path.read_text(encoding="utf-8")
    assert "## Progresso (sessão 2026-10-16)" in text and "ontem" in text
    assert "## Progresso (sessão 2026-10-17)" in text and "hoje" in text


def test_write_substituicao_nao_come_seccao_seguinte(tmp_path):
    path = make_sp(tmp_path, "atlas/sp/Doing", "a", body="# SP\n\n## Progresso (sessão 2026-10-17)\nvelho\n\n## Notas\nficam\n")
    sp_handoff.write(path, "novo\n", today="2026-10-17")
    text = path.read_text(encoding="utf-8")
    assert "novo" in text and "velho" not in text
    assert text.endswith("## Notas\nficam\n")


def test_write_preserva_crlf(tmp_path):
    path = make_sp(tmp_path, "atlas/sp/Doing", "a")
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    sp_handoff.write(path, "x\n", today="2026-10-17")
    raw = path.read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n")


def test_write_nao_toca_no_status(tmp_path):
    path = make_sp(tmp_path, "atlas/sp/Doing", "a")
    sp_handoff.write(path, "x\n", today="2026-10-17")
    assert path.parent.name == "Doing"
    assert "status: Doing\n" in path.read_text(encoding="utf-8")


def test_pane_id_do_ambiente():
    assert sp_handoff.pane_id({"WEZTERM_PANE": "7"}) == "7"


def test_pane_id_em_falta_da_erro():
    with pytest.raises(sp_handoff.HandoffError, match="WEZTERM_PANE"):
        sp_handoff.pane_id({})


def test_send_argv_escreve_so_o_texto_sem_enter():
    assert sp_handoff.send_argv("3", "/clear") == [
        "wezterm", "cli", "send-text", "--pane-id", "3", "--no-paste", "/clear"]


def test_enter_argv_e_um_envio_so_com_cr():
    assert sp_handoff.enter_argv("3") == [
        "wezterm", "cli", "send-text", "--pane-id", "3", "--no-paste", "\r"]


def test_send_argv_recusa_caracteres_de_controlo():
    with pytest.raises(sp_handoff.HandoffError, match="controlo"):
        sp_handoff.send_argv("3", "/michi a\nb")


def test_send_ordem_espera_clear_espera_michi_com_espacos_no_caminho():
    sp = Path(r"C:\Meu Vault\sp\Doing\a b.md")
    eventos = []
    sp_handoff.send(sp, "3", delay=5, gap=2, enter_gap=0.5,
                    run=lambda argv, **kw: eventos.append(("run", argv[-1])),
                    sleep=lambda s: eventos.append(("sleep", s)))
    assert eventos == [
        ("sleep", 5), ("run", "/clear "), ("sleep", 0.5), ("run", "\r"),
        ("sleep", 2), ("run", f"/michi {sp}"), ("sleep", 0.5), ("run", "\r"),
    ]


def test_launch_em_segundo_plano_nao_corre_o_wezterm_diretamente(monkeypatch, tmp_path):
    sp = make_sp(tmp_path, "atlas/sp/Doing", "a")
    calls = []
    monkeypatch.setattr(sp_handoff.subprocess, "Popen", lambda argv, **kw: calls.append(argv))
    monkeypatch.setattr(sp_handoff, "pane_exists", lambda pane: None)
    argv = sp_handoff.launch(sp, "3", "wezterm")
    assert calls == [argv]
    assert argv[1] == "-I"
    assert argv[3:] == ["--send", str(sp), "--pane", "3", "--backend", "wezterm", "--harness", "claude"]
    assert argv[0] != "wezterm" and "send-text" not in argv


MAE = (
    "---\nstatus: TODO\ncreated: 2026-10-01T10:00:00Z\nupdated: 2026-10-01T10:00:00Z\nslug: mae\nproject: atlas\n"
    "kind: program\nchildren:\n  - slug: a\n    depends_on: []\n    state: Done\n"
    "  - slug: b\n    depends_on: [a]\n    state: TODO\n  - slug: c\n    depends_on: [a, b]\n    state: TODO\n---\n# mãe\n"
)


def make_program(root, state_b="Doing"):
    mae = root / "atlas/sp/TODO/mae.md"
    mae.parent.mkdir(parents=True)
    mae.write_bytes(MAE.encode("utf-8"))
    for slug, folder, deps in (("a", "Done", ""), ("b", state_b, "depends_on: [a]\n"), ("c", "TODO", "depends_on: [a, b]\n")):
        path = root / f"atlas/sp/{folder}/{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            f"---\nstatus: {folder}\ncreated: 2026-10-01T10:00:00Z\nupdated: 2026-10-01T10:00:00Z\nslug: {slug}\n"
            f"project: atlas\nparent: mae\n{deps}---\n# {slug}\n".encode("utf-8"))
    return mae


def test_resolve_slug_da_mae_devolve_o_filho_em_doing(tmp_path):
    make_program(tmp_path)
    assert sp_handoff.resolve(tmp_path, "mae") == (tmp_path / "atlas/sp/Doing/b.md").resolve()


def test_resolve_mae_sem_filho_em_doing(tmp_path):
    make_program(tmp_path, state_b="TODO")
    with pytest.raises(sp_handoff.HandoffError, match="nenhum filho em Doing"):
        sp_handoff.resolve(tmp_path, "mae")


def test_sync_program_atualiza_state_do_filho_no_mae(tmp_path):
    mae = make_program(tmp_path)
    sp_handoff.sync_program(tmp_path, tmp_path / "atlas/sp/Doing/b.md")
    text = mae.read_text(encoding="utf-8")
    assert "  - slug: b\n    depends_on: [a]\n    state: Doing\n" in text
    assert "  - slug: a\n    depends_on: []\n    state: Done\n" in text
    assert "  - slug: c\n    depends_on: [a, b]\n    state: TODO\n" in text


def test_sync_program_proximo_elegivel_respeita_dependencias(tmp_path):
    make_program(tmp_path)
    msg = sp_handoff.sync_program(tmp_path, tmp_path / "atlas/sp/Doing/b.md")
    assert msg == "próximo elegível: nenhum (c aguarda: b)"


def test_sync_program_proximo_elegivel_quando_dependencia_cumprida(tmp_path):
    make_program(tmp_path, state_b="Done")
    msg = sp_handoff.sync_program(tmp_path, tmp_path / "atlas/sp/Done/b.md")
    assert msg == "próximo elegível: c"


def test_sync_program_sem_parent_nao_faz_nada(tmp_path):
    sp = make_sp(tmp_path, "atlas/sp/Doing", "solto")
    assert sp_handoff.sync_program(tmp_path, sp) is None


def test_main_write_sincroniza_o_mae(tmp_path, capsys):
    mae = make_program(tmp_path)
    progress = tmp_path / "p.md"
    progress.write_text("feito", encoding="utf-8")
    assert sp_handoff.main(["--root", str(tmp_path), "--write", str(tmp_path / "atlas/sp/Doing/b.md"), "--file", str(progress)]) == 0
    assert "próximo elegível" in capsys.readouterr().out
    assert "state: Doing" in mae.read_text(encoding="utf-8")


def test_sync_program_todos_done_diz_programa_completo_sem_mover_a_mae(tmp_path):
    mae = make_program(tmp_path, state_b="Done")
    c = tmp_path / "atlas/sp/TODO/c.md"
    done_c = tmp_path / "atlas/sp/Done/c.md"
    done_c.write_bytes(c.read_bytes().replace(b"status: TODO", b"status: Done"))
    c.unlink()
    msg = sp_handoff.sync_program(tmp_path, done_c)
    assert msg == "programa completo: mae; fechar com: python -I scripts/sp-move.py --project atlas mae done"
    assert mae.exists()


def test_require_doing_aceita_doing_e_recusa_o_resto(tmp_path):
    doing = make_sp(tmp_path, "atlas/sp/Doing", "a")
    todo = make_sp(tmp_path, "atlas/sp/TODO", "b", status="TODO")
    sp_handoff.require_doing(doing)
    sp_handoff.require_doing(todo)
    with pytest.raises(sp_handoff.HandoffError, match="só com SP em TODO ou Doing"):
        sp_handoff.require_doing(make_sp(tmp_path, "atlas/sp/Done", "c", status="Done"))


def test_main_launch_auto_aceita_sp_em_todo_sem_o_mover(tmp_path, capsys):
    todo = make_sp(tmp_path, "atlas/sp/TODO", "b", status="TODO")
    assert sp_handoff.main(["--launch", str(todo), "--auto", "--dry-run", "--pane", "3"]) == 0
    assert "/clear" in capsys.readouterr().out
    assert todo.is_file() and "status: TODO" in todo.read_text(encoding="utf-8")


def test_main_launch_auto_recusa_sp_em_done(tmp_path, capsys):
    done = make_sp(tmp_path, "atlas/sp/Done", "b", status="Done")
    assert sp_handoff.main(["--launch", str(done), "--auto", "--dry-run", "--pane", "3"]) == 1
    assert "só com SP em TODO ou Doing" in capsys.readouterr().err


def test_main_launch_auto_com_doing_mostra_os_comandos(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("WEZTERM_PANE", "3")
    doing = make_sp(tmp_path, "atlas/sp/Doing", "a")
    assert sp_handoff.main(["--launch", str(doing), "--auto", "--dry-run", "--pane", "3"]) == 0
    assert "/clear" in capsys.readouterr().out


def test_main_launch_manual_continua_sem_exigir_doing(tmp_path, capsys):
    todo = make_sp(tmp_path, "atlas/sp/TODO", "b", status="TODO")
    assert sp_handoff.main(["--launch", str(todo), "--dry-run", "--pane", "3"]) == 0


class _Out:
    def __init__(self, stdout):
        self.stdout = stdout


def test_pane_exists_aceita_painel_listado_e_recusa_o_resto():
    run = lambda argv, **kw: _Out('[{"pane_id": 0}, {"pane_id": 7}]')
    sp_handoff.pane_exists("7", run=run)
    with pytest.raises(sp_handoff.HandoffError, match="não existe"):
        sp_handoff.pane_exists("9", run=run)


def test_prompt_has_text_so_com_texto_depois_do_marcador():
    assert not sp_handoff.prompt_has_text("----\n❯   \n----\n")
    assert sp_handoff.prompt_has_text("----\n❯ ola\n----\n")


def test_check_prompt_aborta_com_texto_por_enviar():
    with pytest.raises(sp_handoff.HandoffError, match="texto por enviar"):
        sp_handoff.check_prompt("3", run=lambda argv, **kw: _Out("❯ rascunho\n"))


def test_send_aborta_antes_do_clear_se_inspect_falha():
    eventos = []

    def inspect(pane):
        raise sp_handoff.HandoffError("sujo")

    with pytest.raises(sp_handoff.HandoffError):
        sp_handoff.send("x.md", "3", run=lambda argv, **kw: eventos.append(argv), sleep=lambda s: None, inspect=inspect)
    assert eventos == []


def test_resolve_sem_slug_filtra_pelos_claims_do_agente(tmp_path):
    make_sp(tmp_path, "atlas/sp/Doing", "a")
    b = make_sp(tmp_path, "atlas/sp/Doing", "b")
    assert sp_handoff.resolve(tmp_path, mine={"b"}) == b
    with pytest.raises(sp_handoff.HandoffError):
        sp_handoff.resolve(tmp_path, mine={"zzz"})


# --- backends e harnesses (kaizen-flow público) ---

def test_detect_backend_prefere_wezterm_depois_tmux_depois_clipboard():
    assert sp_handoff.detect_backend({"WEZTERM_PANE": "3", "TMUX_PANE": "%1"}) == ("wezterm", "3")
    assert sp_handoff.detect_backend({"TMUX_PANE": "%1"}) == ("tmux", "%1")
    assert sp_handoff.detect_backend({}) == ("clipboard", None)


def test_tmux_argv_literal_e_enter_separado():
    assert sp_handoff.tmux_send_argv("%1", "/michi a b.md") == ["tmux", "send-keys", "-t", "%1", "-l", "/michi a b.md"]
    assert sp_handoff.tmux_enter_argv("%1") == ["tmux", "send-keys", "-t", "%1", "Enter"]
    with pytest.raises(sp_handoff.HandoffError):
        sp_handoff.tmux_send_argv("%1", "a\nb")


def test_harness_retoma_claude_e_codex():
    assert sp_handoff.resume_commands("claude", "x.md") == ["/clear ", "/michi x.md"]
    assert sp_handoff.resume_commands("codex", "x.md") == ["/new", "Follow .agents/skills/michi/SKILL.md on x.md"]
    with pytest.raises(sp_handoff.HandoffError, match="harness"):
        sp_handoff.resume_commands("vim", "x.md")


def test_send_tmux_ordem_clear_michi():
    eventos = []
    sp_handoff.send("x.md", "%1", backend="tmux", run=lambda argv, **kw: eventos.append(argv), sleep=lambda s: None)
    assert [e[-1] for e in eventos] == ["/clear ", "Enter", "/michi x.md", "Enter"]
    assert all(e[0] == "tmux" for e in eventos)


def test_clipboard_copia_comando_de_retoma_e_imprime(capsys):
    copiado = []
    ok = sp_handoff.deliver_clipboard("claude", "x.md", copy=copiado.append)
    assert ok is True and copiado == ["/michi x.md"]
    assert "/michi x.md" in capsys.readouterr().out


def test_clipboard_sem_ferramenta_so_imprime(capsys):
    def copy(text):
        raise OSError("sem clip")

    assert sp_handoff.deliver_clipboard("codex", "x.md", copy=copy) is False
    assert "Follow .agents/skills/michi/SKILL.md on x.md" in capsys.readouterr().out


def test_main_launch_sem_multiplexer_cai_no_clipboard(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("WEZTERM_PANE", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.setattr(sp_handoff, "_copy", lambda text: None)
    doing = make_sp(tmp_path, "atlas/sp/Doing", "a")
    assert sp_handoff.main(["--launch", str(doing), "--harness", "codex"]) == 0
    assert "Follow .agents/skills/michi/SKILL.md" in capsys.readouterr().out


def test_main_dry_run_tmux_mostra_comandos(tmp_path, capsys):
    doing = make_sp(tmp_path, "atlas/sp/Doing", "a")
    assert sp_handoff.main(["--launch", str(doing), "--dry-run", "--backend", "tmux", "--pane", "%2"]) == 0
    assert "send-keys" in capsys.readouterr().out


# --- --spawn: um painel e uma worktree por SP ---

WT = "C:" + chr(92) + "wt" + chr(92)


class FakeRun:
    """Regista os comandos; `spawn` devolve ids de painel 11, 12, ... e falha para os slugs em `falha`."""

    def __init__(self, falha=()):
        self.calls, self.falha, self.next_pane = [], set(falha), 11

    screens = None  # ecrãs sucessivos de get-text/capture-pane; omissão: prompt vazio

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        if "get-text" in argv or "capture-pane" in argv:
            out = self.screens.pop(0) if self.screens else "❯ \n"
            return sp_handoff.subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")
        if "sb-worktree.py" in " ".join(map(str, argv)):
            slug = argv[-1]
            if slug in self.falha:
                raise sp_handoff.subprocess.CalledProcessError(1, argv, stderr="sem worktree")
            return sp_handoff.subprocess.CompletedProcess(argv, 0, stdout=WT + slug + chr(10), stderr="")
        if argv[:3] == ["wezterm", "cli", "spawn"]:
            self.next_pane += 1
            return sp_handoff.subprocess.CompletedProcess(argv, 0, stdout=f"{self.next_pane - 1}\n", stderr="")
        return sp_handoff.subprocess.CompletedProcess(argv, 0, stdout="", stderr="")


def spawn(slugs, tmp_path, run, **kw):
    return sp_handoff.spawn(slugs, backend=kw.pop("backend", "wezterm"), run=run, sleep=lambda s: None,
                            estado_path=tmp_path / "estado.json", **kw)


def test_spawn_abre_um_painel_por_sp_com_worktree_e_michi_auto(tmp_path):
    run = FakeRun()
    res = spawn(["a", "b"], tmp_path, run)
    assert [r["slug"] for r in res] == ["a", "b"] and [r["painel"] for r in res] == ["11", "12"]
    spawns = [c for c in run.calls if c[:3] == ["wezterm", "cli", "spawn"]]
    assert [c[c.index("--cwd") + 1] for c in spawns] == [WT + "a", WT + "b"]
    sent = [c[-1] for c in run.calls if "send-text" in c]
    assert "/michi --auto a" in sent and "/michi --auto b" in sent


def test_spawn_regista_cada_painel_no_estado(tmp_path):
    spawn(["a", "b"], tmp_path, FakeRun())
    sessoes = json.loads((tmp_path / "estado.json").read_text(encoding="utf-8"))["sessoes"]
    assert sessoes["a"]["painel"] == "11" and sessoes["b"]["worktree"] == WT + "b"
    assert sessoes["a"]["estado"] == "lancado" and "inicio" in sessoes["a"]


def test_spawn_falha_num_sp_nao_afeta_os_outros(tmp_path):
    res = spawn(["a", "b", "c"], tmp_path, FakeRun(falha={"b"}))
    assert [(r["slug"], r["ok"]) for r in res] == [("a", True), ("b", False), ("c", True)]
    assert "sem worktree" in res[1]["erro"]
    assert set(json.loads((tmp_path / "estado.json").read_text(encoding="utf-8"))["sessoes"]) == {"a", "c"}


def test_spawn_respeita_concorrencia_maxima(tmp_path):
    res = spawn(["a", "b", "c", "d"], tmp_path, FakeRun(), maximo=2)
    assert [r["slug"] for r in res if r["ok"]] == ["a", "b"]
    assert all("adiado" in r["erro"] for r in res[2:])


def test_spawn_tmux_usa_split_window(tmp_path):
    run = FakeRun()
    res = spawn(["a"], tmp_path, run, backend="tmux")
    assert res[0]["ok"] and any(c[:2] == ["tmux", "split-window"] for c in run.calls)


def test_spawn_clipboard_imprime_comandos_sem_painel(tmp_path, capsys):
    run = FakeRun()
    res = spawn(["a"], tmp_path, run, backend="clipboard", copy=lambda t: None)
    out = capsys.readouterr().out
    assert res[0]["ok"] and res[0]["painel"] is None
    assert WT + "a" in out and "/michi --auto a" in out
    assert not any(c[0] in ("wezterm", "tmux") for c in run.calls)


def test_spawn_espera_pelo_prompt_e_repete_enter_perdido(tmp_path):
    run = FakeRun()
    # 1.º ecrã: a arrancar (sem prompt); 2.º: prompt pronto; 3.º: texto ficou por submeter; 4.º: submetido
    run.screens = ["a iniciar\n", "❯ \n", "❯ /michi --auto a\n", "❯ \n"]
    res = spawn(["a"], tmp_path, run)
    assert res[0]["ok"]
    assert sum(1 for c in run.calls if c[-1] == "\r") == 2
    assert sum(1 for c in run.calls if "send-text" in c and c[-1] == "/michi --auto a") == 1


def test_spawn_aprova_so_o_vault_no_aviso_mcp(tmp_path):
    run = FakeRun()
    nl = chr(10)
    aviso = "2 new MCP servers found in this project" + nl + "❯ [✓] vault" + nl + "  [✓] roblox" + nl
    run.screens = [aviso, "❯ " + nl, "❯ " + nl]
    res = spawn(["a"], tmp_path, run)
    assert res[0]["ok"]
    teclas = [c[-1] for c in run.calls if "send-text" in c][:4]
    assert teclas == [chr(27) + "[B", " ", chr(27) + "[B", chr(13)]
    assert sum(1 for c in run.calls if "send-text" in c and c[-1] == "/michi --auto a") == 1


def test_spawn_enter_que_nunca_submete_falha_so_esse_sp(tmp_path):
    run = FakeRun()
    run.screens = ["❯ \n"] + ["❯ /michi --auto a\n"] * 3
    res = spawn(["a"], tmp_path, run)
    assert not res[0]["ok"] and "Enter" in res[0]["erro"]


def test_spawn_dry_run_nao_tem_efeitos(tmp_path):
    run = FakeRun()
    res = spawn(["a", "b"], tmp_path, run, dry_run=True)
    assert run.calls == []
    assert not (tmp_path / "estado.json").exists()
    assert [r["slug"] for r in res] == ["a", "b"] and all(r["ok"] and r["painel"] is None for r in res)


def test_cli_spawn_dry_run_nao_lanca_nada(tmp_path, capsys, monkeypatch):
    run = FakeRun()
    monkeypatch.setattr(sp_handoff, "run_hidden", run)
    monkeypatch.setattr(sp_handoff, "detect_backend", lambda env=None: ("wezterm", None))
    assert sp_handoff.main(["--spawn", "a", "--dry-run"]) == 0
    assert run.calls == [] and "a: dry-run" in capsys.readouterr().out
