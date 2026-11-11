"""Testes de scripts/sp_fila_paineis.py: um painel por SP elegível (modelo do SP, teto global, título, prompt, recusas)."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import sp_fila_paineis as fp
import sp_painel_estado as pe
from sp_fila_testlib import PainelFalso, make_sp


def _modelos(tmp_path):
    f = tmp_path / "modelos.json"
    f.write_text(json.dumps({"papeis": {
        "michi-exec": {"model": "claude-sonnet-5-5", "effort": "low"},
        "michi-complexo": {"model": "claude-opus-5-5", "effort": "low"},
        "michi-leve": {"model": "claude-haiku-5-5", "effort": "low"},
    }}), encoding="utf-8")
    return f


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "MODELOS", _modelos(tmp_path))
    estado_root = tmp_path / "estado"
    monkeypatch.setenv(pe.ENV_ROOT, str(estado_root))
    return SimpleNamespace(root=tmp_path / "sps", estado=estado_root)


def _alvo(root, slug, nivel=None, project="p"):
    path = make_sp(root, slug, extra={"michi_modelo": nivel} if nivel else None, project=project)
    return SimpleNamespace(slug=slug, path=path, project=project)


def _run(calls, master=True, ensure_rc=0, move_rc=0):
    """`run` falso: `ensure` imprime `/wt/sb-<slug>`, `ls-tree` lista o SP se `master`, `sp-move` devolve `move_rc`."""
    def run(argv, **kw):
        calls.append((list(map(str, argv)), kw.get("cwd")))
        flat = " ".join(map(str, argv))
        rc, out, err = 0, "", ""
        if "ensure" in argv:
            rc, out, err = ensure_rc, f"/wt/sb-{argv[-1]}\n" if ensure_rc == 0 else "", "worktree já existe" if ensure_rc else ""
        elif "ls-tree" in argv:
            out = f"{argv[-1]}\n" if master else ""
        elif "sp-move.py" in flat:
            rc, err = move_rc, "sp-move falhou" if move_rc else ""
        return SimpleNamespace(returncode=rc, stdout=out, stderr=err)
    return run


def _lancar(alvos, fila, backend, run, verificar_master=False):
    return fp.lancar(alvos, fila, backend=backend, run=run, sleep=lambda s: None, verificar_master=verificar_master)


def test_modelo_vem_do_michi_modelo_de_cada_sp(ambiente):
    fila = fp.garantir_fila({"programa": None})
    b = PainelFalso()
    alvos = [_alvo(ambiente.root, "a", "complexo"), _alvo(ambiente.root, "b")]
    res = _lancar(alvos, fila, b, _run([]))
    assert [r["estado"] for r in res] == ["a-correr", "a-correr"]
    cmds = {Path(cwd).name: cmd for cmd, cwd in b.abertos}
    assert cmds["sb-a"] == ["claude", "--model", "claude-opus-5-5", "--effort", "low"]
    assert cmds["sb-b"] == ["claude", "--model", "claude-sonnet-5-5", "--effort", "low"]
    sa = pe.ler(fila, "a")
    assert sa["estado"] == "a-correr" and sa["modelo"] == "claude-opus-5-5" and sa["worktree"] == "/wt/sb-a" and sa["pane"]
    assert pe.ler(fila, "b")["modelo"] == "claude-sonnet-5-5"


def test_painel_abre_na_worktree_com_o_michi_do_sp(ambiente):
    fila = fp.garantir_fila({"programa": None})
    b = PainelFalso()
    calls = []
    _lancar([_alvo(ambiente.root, "a")], fila, b, _run(calls))
    (cmd, cwd), = b.abertos
    assert Path(cwd) == Path("/wt/sb-a")
    (pane, texto), = b.enviados
    assert texto.startswith("/michi --auto a ") and "\n" not in texto
    ordem = [c[0] for c in calls]
    i_ensure = next(i for i, a in enumerate(ordem) if "ensure" in a)
    i_move = next(i for i, a in enumerate(ordem) if any(x.endswith("sp-move.py") for x in a))
    assert i_ensure < i_move
    move, cwd_move = calls[i_move]
    assert Path(cwd_move) == Path("/wt/sb-a") and Path(move[2]) == Path("/wt/sb-a") / "scripts" / "sp-move.py" and move[-1] == "doing"


def test_sem_vaga_fica_pendente_e_nada_abre(ambiente):
    outra = fp.garantir_fila({"programa": "outra"})
    for s in ("x", "y", "z"):
        pe.registar(outra, s)
        assert pe.reclamar_vaga(s, outra)
    fila = fp.garantir_fila({"programa": None})
    b = PainelFalso()
    calls = []
    res = _lancar([_alvo(ambiente.root, "a")], fila, b, _run(calls))
    assert res[0]["estado"] == "pendente" and pe.ler(fila, "a")["estado"] == "pendente"
    assert b.abertos == [] and not any("ensure" in c[0] for c in calls)


def test_duas_filas_nunca_passam_de_3_paineis(ambiente):
    f1 = fp.garantir_fila({"programa": "p1"})
    f2 = fp.garantir_fila({"programa": "p2"})
    b = PainelFalso()
    r1 = _lancar([_alvo(ambiente.root, s) for s in ("a", "b")], f1, b, _run([]))
    r2 = _lancar([_alvo(ambiente.root, s) for s in ("c", "d")], f2, b, _run([]))
    assert [r["estado"] for r in r1 + r2] == ["a-correr", "a-correr", "a-correr", "pendente"]
    assert len(b.abertos) == 3 and pe.vagas_livres() == 0


def test_titulo_do_separador_e_o_slug_com_sufixo_se_duplicado(ambiente):
    fila = fp.garantir_fila({"programa": None})
    b = PainelFalso(titulos={"99": "a"})
    res = _lancar([_alvo(ambiente.root, "a")], fila, b, _run([]))
    assert res[0]["titulo"] == "a-2" and list(b.titulos_postos.values()) == ["a-2"]
    assert fp.titulo_livre("a", ["a", "a-2"]) == "a-3" and fp.titulo_livre("b", ["a"]) == "b"


def test_prompt_manda_sp_estado_no_fim_e_proibe_atalhos():
    p = fp.prompt_painel("meu-sp", "/wt/sb-meu-sp")
    assert p.startswith("/michi --auto meu-sp ") and "\n" not in p
    assert "python -I scripts/sp-estado.py meu-sp" in p and "--msg" in p
    for proibido in ("--sem-budget", "--sem-testes", "merge", "/kaizen-sync"):
        assert proibido in p
    assert "/wt/sb-meu-sp" in p and "nunca" in p.lower()


def test_sp_fora_de_master_e_recusado_antes_de_abrir(ambiente):
    fila = fp.garantir_fila({"programa": None})
    b = PainelFalso()
    calls = []
    res = _lancar([_alvo(ambiente.root, "a")], fila, b, _run(calls, master=False), verificar_master=True)
    assert res[0]["estado"] == "falhou" and "commitar" in res[0]["msg"] and "a.md" in res[0]["msg"] and "master" in res[0]["msg"]
    assert b.abertos == [] and not any("ensure" in c[0] for c in calls)
    assert pe.ler(fila, "a")["estado"] == "falhou" and pe.vagas_livres() == 3


def test_sp_em_master_passa_a_verificacao(ambiente):
    fila = fp.garantir_fila({"programa": None})
    b = PainelFalso()
    calls = []
    res = _lancar([_alvo(ambiente.root, "a")], fila, b, _run(calls, master=True), verificar_master=True)
    assert res[0]["estado"] == "a-correr"
    ls = next(c for c in calls if "ls-tree" in c[0])
    assert "master" in ls[0] and ls[0][-1] == "a.md"


def test_falha_ao_abrir_liberta_vaga_e_marca_falhou(ambiente):
    fila = fp.garantir_fila({"programa": None})
    b = PainelFalso(falha_abrir="wezterm: sem janela")
    calls = []
    res = _lancar([_alvo(ambiente.root, "a")], fila, b, _run(calls))
    sp = pe.ler(fila, "a")
    assert res[0]["estado"] == "falhou" and sp["estado"] == "falhou" and "sem janela" in sp["msg"]
    assert pe.vagas_livres() == 3 and sp["worktree"] == "/wt/sb-a"
    assert not any("remove" in c[0] or "clean" in c[0] for c in calls)  # worktree intacta


def test_falha_no_ensure_marca_falhou_sem_abrir(ambiente):
    fila = fp.garantir_fila({"programa": None})
    b = PainelFalso()
    res = _lancar([_alvo(ambiente.root, "a")], fila, b, _run([], ensure_rc=1))
    assert res[0]["estado"] == "falhou" and "worktree já existe" in res[0]["msg"]
    assert b.abertos == [] and pe.vagas_livres() == 3


def test_falha_no_envio_fecha_o_painel(ambiente):
    fila = fp.garantir_fila({"programa": None})
    b = PainelFalso(falha_enviar=True)
    res = _lancar([_alvo(ambiente.root, "a")], fila, b, _run([]))
    assert res[0]["estado"] == "falhou" and b.fechados == [b.abertos_ids[0]] and pe.vagas_livres() == 3


def test_resultado_nao_expoe_pane(ambiente):
    fila = fp.garantir_fila({"programa": None})
    res = _lancar([_alvo(ambiente.root, "a")], fila, PainelFalso(), _run([]))
    assert "pane" not in res[0] and set(res[0]) >= {"slug", "estado", "modelo", "worktree", "titulo"}


def test_backend_nao_interativo_leva_o_prompt_no_comando(ambiente):
    fila = fp.garantir_fila({"programa": None})
    b = PainelFalso(interativo=False)
    _lancar([_alvo(ambiente.root, "a")], fila, b, _run([]))
    (cmd, _), = b.abertos
    assert cmd[:2] == ["claude", "--model"] and cmd[-1].startswith("/michi --auto a ") and b.enviados == []


def test_garantir_fila_reusa_a_do_programa(ambiente):
    assert fp.garantir_fila({"programa": "mae"}) == "mae" == fp.garantir_fila({"programa": "mae"})


def test_plano_dry_run_sem_efeitos(ambiente):
    alvos = [_alvo(ambiente.root, "a", "complexo"), _alvo(ambiente.root, "b")]
    plano = fp.plano_dry_run(alvos)
    assert [(p["slug"], p["modelo"]) for p in plano] == [("a", "claude-opus-5-5"), ("b", "claude-sonnet-5-5")]
    assert plano[0]["worktree"].replace("\\", "/").endswith("code-wt/sb-a")
    assert not ambiente.estado.exists()
    linhas = fp.render_dry_run(plano)
    assert "a · claude-opus-5-5 · " in linhas and "pane" not in linhas


def test_worktree_prevista_parte_do_checkout_principal_mesmo_dentro_de_uma_worktree(tmp_path):
    principal = tmp_path / "Documents" / "Second-Brain"
    (principal / ".git" / "worktrees" / "sb-x").mkdir(parents=True)
    wt = tmp_path / "Documents" / "code-wt" / "sb-x"
    wt.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {principal / '.git' / 'worktrees' / 'sb-x'}\n", encoding="utf-8")
    esperado = str(tmp_path / "Documents" / "code-wt" / "sb-a")
    assert fp.worktree_prevista("a", repo=wt) == esperado == fp.worktree_prevista("a", repo=principal)


def test_plano_dry_run_respeita_o_teto_e_marca_o_resto_pendente(ambiente):
    alvos = [_alvo(ambiente.root, s) for s in ("a", "b", "c")]
    plano = fp.plano_dry_run(alvos, maximo=2)
    assert [p["slug"] for p in plano] == ["a", "b", "c"]
    assert [p.get("pendente", False) for p in plano] == [False, False, True]
    linhas = fp.render_dry_run(plano).splitlines()
    assert linhas[2] == "c · pendente (sem vaga)" and "pendente" not in linhas[0]
