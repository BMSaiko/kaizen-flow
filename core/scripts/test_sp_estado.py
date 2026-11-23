"""Testes de scripts/sp-estado.py (estado de um SP numa só leitura)."""
from pathlib import Path
from sp_carregar import carregar  # noqa: E402

sp_estado = carregar(Path(__file__).with_name("sp-estado.py"), "sp_estado", fresco=True)

SP = """---
status: {st}
slug: {slug}
project: demo
priority: P2
modo: manual
parent: mae
depends_on: [dep-a, dep-b]
gates:
  - cmd: python -I x.py
---
# Super Prompt

## 4. Success criteria (verifiable)
- [x] um
- [ ] dois
- [ ] tres

## 7. Steps (numbered, ordered)
1. Primeiro.
2. Segundo.

## Progresso
- l1
- l2
- l3
- l4
"""


def make(tmp_path, folder, slug, st=None):
    d = tmp_path / "demo" / "sp" / folder
    d.mkdir(parents=True)
    f = d / f"{slug}-2026-10-26.md"
    f.write_text(SP.format(st=st or folder, slug=slug), encoding="utf-8")
    return f


def test_doing_resume_curto(tmp_path):
    make(tmp_path, "Done", "dep-a")
    make(tmp_path, "Doing", "alvo")
    out = sp_estado.estado("alvo", root=tmp_path, git_lines=["master", "M a.py"])
    lines = out.splitlines()
    assert len(lines) <= 30
    assert "Doing" in out and "1/3" in out and "gates: 1" in out
    assert "dep-b" in out and "master" in out and "a.py" in out
    assert "l4" in out and "l1" not in out  # só as últimas linhas do Progresso


def test_todo_por_caminho(tmp_path):
    f = make(tmp_path, "TODO", "alvo")
    out = sp_estado.estado(str(f), root=tmp_path, git_lines=["master"])
    assert "TODO" in out and "Progresso" not in out.split("progresso:")[0]


def test_inexistente(tmp_path):
    out = sp_estado.estado("nada", root=tmp_path, git_lines=["master"])
    assert "não encontrado" in out


def test_limita_ficheiros_git(tmp_path):
    make(tmp_path, "Doing", "alvo")
    out = sp_estado.estado("alvo", root=tmp_path, git_lines=["master"] + [f"M f{i}" for i in range(50)])
    assert len(out.splitlines()) <= 30


def test_aceita_nome_do_ficheiro_com_data(tmp_path):
    make(tmp_path, "Doing", "alvo")  # ficheiro alvo-2026-10-26.md
    for ref in ("alvo-2026-10-26", "alvo-2026-10-26.md"):
        out = sp_estado.estado(ref, root=tmp_path, git_lines=["master"])
        assert out.startswith("alvo · Doing")
    assert "não encontrado" in sp_estado.estado("outro-2026-10-26", root=tmp_path, git_lines=["master"])


def test_spike_incerto_mostra_timebox(tmp_path):
    f = make(tmp_path, "Doing", "alvo")
    f.write_text(f.read_text(encoding="utf-8").replace("modo: manual\n", "modo: manual\nspike: incerto\n"), encoding="utf-8")
    out = sp_estado.estado("alvo", root=tmp_path, git_lines=["master"])
    assert "spike: incerto · max_requests 15" in out
    f.write_text(f.read_text(encoding="utf-8").replace("spike: incerto\n", "spike: incerto\nmax_requests: 8\n"), encoding="utf-8")
    assert "max_requests 8" in sp_estado.estado("alvo", root=tmp_path, git_lines=["master"])


def test_sem_spike_nao_mostra_linha(tmp_path):
    make(tmp_path, "Doing", "alvo")
    assert "spike" not in sp_estado.estado("alvo", root=tmp_path, git_lines=["master"])


def test_avisa_ramo_atras_de_master(tmp_path):
    make(tmp_path, "Doing", "alvo")
    out = sp_estado.estado("alvo", root=tmp_path, git_lines=["agent/x"], atras=3)
    assert "atrás de master" in out and "3 commits" in out and "git merge master" in out


def test_sem_aviso_quando_em_dia(tmp_path):
    make(tmp_path, "Doing", "alvo")
    assert "atrás" not in sp_estado.estado("alvo", root=tmp_path, git_lines=["master"], atras=0)


def test_michi_e_execucao_na_mae(tmp_path):
    make(tmp_path, "Doing", "filho")
    d = tmp_path / "demo" / "sp" / "TODO"
    d.mkdir(parents=True)
    mae_txt = SP.format(st="TODO", slug="mae").replace("parent: mae\n", "kind: program\nmichi_modelo: complexo\n")
    (d / "mae-2026-10-26.md").write_text(mae_txt, encoding="utf-8")
    mae = sp_estado.estado("mae", root=tmp_path, git_lines=["master"])
    filho = sp_estado.estado("filho", root=tmp_path, git_lines=["master"])
    assert "michi: complexo" in mae and "execução: por escolher · perguntar sequencial/paralelo" in mae
    assert "michi: default" in filho and "execução" not in filho
    (d / "mae-2026-10-26.md").write_text(mae_txt.replace("kind: program\n", "kind: program\nexecucao: paralelo\n"), encoding="utf-8")
    assert "execução: paralelo" in sp_estado.estado("mae", root=tmp_path, git_lines=["master"])


def _aninhado(tmp_path, slug, folder="Doing"):
    d = tmp_path / "kaizen" / "demo" / "sp" / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text(SP.format(st=folder, slug=slug), encoding="utf-8")


def test_resolve_projeto_aninhado_e_slug_sem_data(tmp_path):
    _aninhado(tmp_path, "alvo-2026-11-01")
    for project in (None, "demo", "kaizen/demo"):
        for ref in ("alvo-2026-11-01", "alvo"):
            out = sp_estado.estado(ref, root=tmp_path, project=project, git_lines=["master"])
            assert out.startswith("alvo-2026-11-01 · Doing"), (ref, project, out)
    assert "não encontrado" in sp_estado.estado("alvo", root=tmp_path, project="kaizen/outro", git_lines=["master"])


def test_slug_sem_data_ambiguo(tmp_path):
    _aninhado(tmp_path, "alvo-2026-11-01")
    _aninhado(tmp_path, "alvo-2026-11-05", "TODO")
    out = sp_estado.estado("alvo", root=tmp_path, git_lines=["master"])
    assert out.startswith("SP ambíguo") and "alvo-2026-11-01" in out and "alvo-2026-11-05" in out


def test_listar_mostra_orfaos_como_interrompido_ec027(tmp_path):
    import json
    import sp_journal

    sp_journal.inicio(tmp_path, "sp-orfao", "da", "p1")
    fila = tmp_path / "filas"
    texto = sp_estado.listar(str(fila), raiz_sp=str(tmp_path))
    assert "sp-orfao · interrompido · kaizen resume sp-orfao" in texto
    dados = json.loads(sp_estado.listar(str(fila), em_json=True, raiz_sp=str(tmp_path)))
    assert dados["interrompidos"] == [{"slug": "sp-orfao", "estado": "interrompido", "proximo": "kaizen resume sp-orfao"}]
    assert "interrompido" not in sp_estado.listar(str(fila), raiz_sp=str(tmp_path / "vazio"))


def test_listar_mostra_pausa_com_retoma_em(tmp_path):
    import sp_painel_estado as pe
    root = tmp_path / "filas"
    pe.criar_fila("f1", root=root, ordem=["a"])
    pe.registar("f1", "a", root=root, pane="1")
    pe.transitar("a", "a-correr", fila="f1", root=root)
    pe.transitar("a", "bloqueado", msg="EC-016 quota; retoma automática às 2026-11-18T15:00:00", fila="f1", root=root,
                 motivo="EC-016 quota", retoma_em="2026-11-18T15:00:00")
    texto = sp_estado.listar(str(root), raiz_sp=str(tmp_path / "vazio"))
    assert "a · bloqueado · EC-016 quota; retoma automática" in texto and "retoma 2026-11-18T15:00:00" in texto


def test_recusas_do_estado_no_formato_ec(tmp_path, capsys):
    import kf_erros
    assert sp_estado.main(["nao-existe", "done", "--root", str(tmp_path)]) == 1
    lido = kf_erros.ler(capsys.readouterr().err.rstrip("\n"))
    assert lido is not None and lido.ec == "EC-067" and "slug desconhecido" in lido.oque


def _painel_bloqueado(tmp_path):
    import sp_painel_estado as pe
    r = tmp_path / "paineis"
    fid = pe.criar_fila("mae", ordem=["a"], root=r)
    pe.transitar("a", "a-correr", fila=fid, root=r)
    pe.transitar("a", "bloqueado", fila=fid, root=r)
    return pe, fid, r


def test_bloqueado_para_done_recusado_sem_forcar(tmp_path):
    import pytest
    pe, fid, r = _painel_bloqueado(tmp_path)
    with pytest.raises(pe.ErroEstado):
        pe.transitar("a", "done", fila=fid, root=r)
    assert pe.ler(fid, "a", root=r)["estado"] == "bloqueado"


def test_forcar_done_aceita_bloqueado(tmp_path):
    pe, fid, r = _painel_bloqueado(tmp_path)
    sp = pe.transitar("a", "done", fila=fid, root=r, forcar_done=True)
    assert sp["estado"] == "done" and sp["fim"]


def test_forcar_done_nao_abre_outras_transicoes(tmp_path):
    import pytest
    pe, fid, r = _painel_bloqueado(tmp_path)
    with pytest.raises(pe.ErroEstado):
        pe.transitar("a", "pergunta", fila=fid, root=r, forcar_done=True)
