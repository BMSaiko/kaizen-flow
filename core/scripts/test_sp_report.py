"""Testes de scripts/sp-report.py (SP de exemplo em texto, sem git)."""
from pathlib import Path
from sp_carregar import carregar  # noqa: E402

sp_report = carregar(Path(__file__).with_name("sp-report.py"), "sp_report", fresco=True)

SP = """---
status: Done
slug: exemplo
gates:
  - cmd: python -I scripts/test-fast.py
    timeout: 120
  - cmd: python -I scripts/context-budget.py
    timeout: 60
---
# SP exemplo

## 4. Success criteria (verifiable)

- [x] feito
- [ ] por fazer

## Prova

- `proofs/exemplo.txt`: output real.

## Reflect

Reflect fase: o pytest deixou cache suja · patch em scripts/x.py · cwd.
Reflect DP: sem patch
"""

STAT = [" scripts/x.py | 10 +++++-----", " 1 file changed, 5 insertions(+), 5 deletions(-)"]


def test_report_tem_as_cinco_seccoes_fixas():
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT)
    for titulo in ("## Alterado", "## Verificado", "## Provas", "## Dificuldades", "## Em aberto"):
        assert titulo in out
    assert out.index("## Alterado") < out.index("## Verificado") < out.index("## Provas") < out.index("## Dificuldades") < out.index("## Em aberto")


def test_alterado_usa_o_diff_stat():
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT)
    assert "scripts/x.py | 10" in out


def test_verificado_lista_comandos_e_rc_dos_resultados():
    res = [{"cmd": "python -I scripts/test-fast.py", "rc": 0, "secs": 3}, {"cmd": "python -I scripts/context-budget.py", "rc": 1, "secs": 0}]
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT, gates=res)
    assert "`python -I scripts/test-fast.py` rc=0" in out
    assert "`python -I scripts/context-budget.py` rc=1" in out


def test_sem_resultados_nao_inventa_rc():
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT)
    assert "`python -I scripts/test-fast.py` rc=não corrido" in out
    assert "rc=0" not in out


def test_dificuldades_vem_das_linhas_reflect_com_causa():
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT)
    assert "pytest deixou cache suja" in out
    assert sp_report.dificuldades_ok(SP)


def test_dificuldades_vazia_e_marcada():
    sem = SP.replace("Reflect fase: o pytest deixou cache suja · patch em scripts/x.py · cwd.\n", "")
    out = sp_report.gerar(sem, "exemplo", diff_stat=STAT)
    assert not sp_report.dificuldades_ok(sem)
    assert "SEM DIFICULDADES REGISTADAS" in out


def test_em_aberto_lista_criterios_por_cumprir():
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT)
    assert "por fazer" in out
    assert "feito" not in out.split("## Em aberto")[1]


def test_provas_lista_a_seccao_prova():
    out = sp_report.gerar(SP, "exemplo", diff_stat=STAT)
    assert "proofs/exemplo.txt" in out


def test_aviso_atraso_so_quando_ha_commits_em_falta():
    assert sp_report.aviso_atraso(0) == ""
    assert "3 commit(s) atrás de master" in sp_report.aviso_atraso(3)


def test_report_mostra_aviso_na_seccao_alterado():
    out = sp_report.gerar(SP, "exemplo", ["a | 1 +"], None, atras=2)
    assert out.split("## Alterado\n")[1].startswith("AVISO: a worktree está 2 commit(s)")
    assert "AVISO" not in sp_report.gerar(SP, "exemplo", ["a | 1 +"], None)


def test_provas_aceita_prova_de_done():
    txt = SP.replace("## Prova\n", "## Prova de done\n")
    assert "proofs/exemplo.txt" in sp_report.gerar(txt, "exemplo", diff_stat=STAT)


def _git_repo(path, ramo="main"):
    import subprocess
    path.mkdir(parents=True, exist_ok=True)
    g = ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", "-b", ramo, str(path)], check=True)
    (path / "a.txt").write_text("1\n", encoding="utf-8")
    subprocess.run(g + ["add", "a.txt"], check=True)
    subprocess.run(g + ["commit", "-qm", "base"], check=True)
    subprocess.run(g + ["checkout", "-qb", "sp/x"], check=True)
    (path / "novo.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(g + ["add", "novo.py"], check=True)
    subprocess.run(g + ["commit", "-qm", "sp"], check=True)
    return path


def test_repo_alvo_vem_do_cwd_dos_gates(tmp_path):
    ext = _git_repo(tmp_path / "ext")
    gates = [{"cmd": "a", "cwd": "."}, {"cmd": "b", "cwd": str(ext / "sub")}, {"cmd": "c", "cwd": str(ext)}]
    (ext / "sub").mkdir()
    assert sp_report.repo_alvo(gates, sp_report.HERE.parent) == ext.resolve()
    assert sp_report.repo_alvo([{"cmd": "a", "cwd": "."}], sp_report.HERE.parent) is None
    assert sp_report.repo_alvo([{"cmd": "a", "cwd": str(tmp_path / "nada")}], sp_report.HERE.parent) is None


def test_main_alterado_usa_o_repo_externo(tmp_path, capsys):
    ext = _git_repo(tmp_path / "ext")
    sp = tmp_path / "sp.md"
    sp.write_text(SP.replace("    timeout: 120\n", f"    cwd: {ext}\n"), encoding="utf-8")
    sp_report.main([str(sp)])
    out = capsys.readouterr().out
    alterado = out.split("## Alterado\n")[1].split("## Verificado")[0]
    assert f"repo: {ext.resolve()} (base main...HEAD)" in alterado
    assert "novo.py" in alterado and "scripts/" not in alterado


def test_alterado_externo_ignora_commits_novos_da_base(tmp_path, capsys):
    import subprocess
    ext = _git_repo(tmp_path / "ext")
    g = ["git", "-C", str(ext), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(g + ["checkout", "-q", "main"], check=True)
    (ext / "alheio.txt").write_text("y\n", encoding="utf-8")
    subprocess.run(g + ["add", "alheio.txt"], check=True)
    subprocess.run(g + ["commit", "-qm", "alheio"], check=True)
    subprocess.run(g + ["checkout", "-q", "sp/x"], check=True)
    sp = tmp_path / "sp.md"
    sp.write_text(SP.replace("    timeout: 120\n", f"    cwd: {ext}\n"), encoding="utf-8")
    sp_report.main([str(sp)])
    alterado = capsys.readouterr().out.split("## Alterado\n")[1].split("## Verificado")[0]
    assert "novo.py" in alterado and "alheio.txt" not in alterado


def test_repo_alvo_ignora_worktree_do_proprio_vault(tmp_path):
    import subprocess
    vault = _git_repo(tmp_path / "vault")
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(vault), "worktree", "add", "-q", "-b", "agent/y", str(wt)], check=True)
    assert sp_report.repo_alvo([{"cmd": "a", "cwd": str(vault)}], wt) is None
    assert sp_report.repo_alvo([{"cmd": "a", "cwd": str(wt)}], vault) is None


def _vault_sps(tmp_path, *slugs):
    sp_list = carregar(Path(__file__).with_name("sp-list.py"), "sp_list_t", fresco=True)
    d = tmp_path / "knowledge" / "projects" / "kaizen" / "kaizen" / "demo" / "sp" / "Doing"
    d.mkdir(parents=True)
    for s in slugs:
        (d / f"{s}.md").write_text(f"---\nstatus: Doing\nslug: {s}\nproject: demo\n---\n# SP\n", encoding="utf-8")
    return sp_list


def test_resolver_slug_e_projeto_nas_tres_formas(tmp_path):
    sp_list = _vault_sps(tmp_path, "demo-x-2026-11-01")
    for project in (None, "demo", "kaizen/demo"):
        for ref in ("demo-x-2026-11-01", "demo-x"):
            caminho, slug, raiz = sp_report.resolver(ref, project, [tmp_path], sp_list)
            assert slug == "demo-x-2026-11-01" and caminho.is_file() and raiz == tmp_path, (ref, project)
    caminho, msg, _ = sp_report.resolver("demo-x", "kaizen/outro", [tmp_path], sp_list)
    assert caminho is None and msg.startswith("SP não encontrado")


def test_resolver_slug_sem_data_ambiguo(tmp_path):
    sp_list = _vault_sps(tmp_path, "demo-x-2026-11-01", "demo-x-2026-11-05")
    caminho, msg, _ = sp_report.resolver("demo-x", None, [tmp_path], sp_list)
    assert caminho is None and msg.startswith("SP ambíguo")
