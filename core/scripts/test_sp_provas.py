"""Testes de sp-provas.py: montar, validar, diagrama SVG, fecho bloqueado e corpo do PR."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from sp_carregar import carregar
from conftest import executar_cli as run

SCRIPTS = Path(__file__).resolve().parent
provas = carregar(SCRIPTS / "sp-provas.py")
pr_corpo = carregar(SCRIPTS / "pr_corpo.py")
PROJECT = "demo"
SLUG = "demo-prova-2026-11-13"

SP = """---
status: Doing
updated: 2026-11-13T00:00:00Z
slug: {slug}
date: {data}
project: demo
priority: P3
{extra}gates:
  - cmd: python -c "print(1)"
---
# SP

## 3. Objective (single sentence)
Fazer a coisa certa.

## 4. Success criteria (verifiable)
1. [x] primeiro feito
2. segundo por fazer

## Decisões modo auto
- escolhi A em vez de B

## Prova de done
Correu o gate e passou.
Segunda linha de prova.
"""


def preparar(tmp_path, data="2026-11-13", extra="", slug=SLUG):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    sp_dir = tmp_path / "vault" / PROJECT / "sp" / "Doing"
    sp_dir.mkdir(parents=True)
    (sp_dir / f"{slug}.md").write_text(SP.format(slug=slug, data=data, extra=extra), encoding="utf-8")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "novo.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "README.md").write_text("r\n", encoding="utf-8")
    return repo, tmp_path / "vault"


def sp_obj(vault, slug=SLUG):
    sp_list = provas.sp_list
    return next(s for s in sp_list.collect(str(vault), include_done=True) if s.slug == slug)


def test_montar_campos_fixos(tmp_path):
    repo, vault = preparar(tmp_path)
    d = provas.montar(sp_obj(vault), cwd=repo, gates_resultados=[{"cmd": "x", "rc": 0, "tail": "ok"}])
    assert set(provas.CAMPOS) <= set(d)
    assert d["objetivo"] == "Fazer a coisa certa."
    assert d["criterios"] == {"cumpridos": ["primeiro feito"], "por_cumprir": ["segundo por fazer"]}
    assert d["decisoes_auto"] == ["escolhi A em vez de B"]
    assert {"path": "scripts/novo.py", "estado": "N"} in d["ficheiros"]
    assert len(d["feito"]) <= 5 and len(d["experimentar"]) <= 3


def test_validar_campos_em_falta():
    assert "campo em falta: reverter" in provas.validar({c: [] for c in provas.CAMPOS if c != "reverter"})


def pacote_valido(**mud):
    d = {"objetivo": "o", "feito": ["a"], "ficheiros": [], "gates": [], "criterios": {"cumpridos": [], "por_cumprir": []},
         "decisoes_auto": [], "experimentar": ["cmd"], "reverter": ["git revert --no-edit abc"], "pr": "",
         "imagens": [{"ficheiro": "d.svg", "legenda": "l", "tipo": "diagrama"}]}
    d.update(mud)
    return d


def test_validar_regras():
    assert provas.validar(pacote_valido()) == []
    assert any("5 linhas" in p for p in provas.validar(pacote_valido(feito=list("abcdef"))))
    assert any("perigoso" in p for p in provas.validar(pacote_valido(reverter=["git reset --hard HEAD~1"])))
    assert any("`depois`" in p for p in provas.validar(pacote_valido(), ui=True))
    assert provas.validar(pacote_valido(imagens=[{"ficheiro": "a.png", "legenda": "l", "tipo": "depois"}]), ui=True) == []
    assert any("diagrama ou terminal" in p for p in provas.validar(pacote_valido(imagens=[])))
    assert any("proibido" in p for p in provas.validar(pacote_valido(imagens=[{"ficheiro": ".env", "legenda": "l", "tipo": "diagrama"}])))
    assert any("segredo" in p for p in provas.validar(pacote_valido(feito=["token = ghp_abcdefghijklmnop"])))


def test_diagrama_svg_agrupa_por_pasta():
    svg = provas.diagrama_svg([{"path": "scripts/a.py", "estado": "N"}, {"path": "scripts/b.py", "estado": "M"},
                               {"path": "docs/c.md", "estado": "D"}])
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "scripts" in svg and "docs" in svg and "3 ficheiros" in svg
    assert "<script" not in provas.diagrama_svg([{"path": "<script>x</script>/a", "estado": "N"}])


def test_limpar_corta_segredos():
    assert "ghp_" not in provas.limpar("ok\nTOKEN=ghp_abcdefghijklmnopqrst\nfim")


def test_gravar_preserva_imagens_manuais(tmp_path):
    repo, vault = preparar(tmp_path)
    sp = sp_obj(vault)
    img = tmp_path / "ecra.png"
    img.write_bytes(b"\x89PNG\r\n")
    provas.gravar(sp, cwd=repo)
    provas.anexar(sp, img, "depois", "ecrã")
    pasta, d = provas.gravar(sp, cwd=repo, gates_resultados=[{"cmd": "x", "rc": 0, "tail": "ok"}])
    tipos = [i["tipo"] for i in d["imagens"]]
    assert "depois" in tipos and "diagrama" in tipos and "terminal" in tipos
    assert (pasta / "diagrama.svg").is_file() and (pasta / "gates.svg").is_file()
    assert provas.validar(d, ui=True, pasta=pasta) == []


def test_anexar_recusa_proibidos(tmp_path):
    repo, vault = preparar(tmp_path)
    segredo = tmp_path / "id_rsa.png"
    segredo.write_bytes(b"x")
    with pytest.raises(provas.ProvasError):
        provas.anexar(sp_obj(vault), segredo, "depois", "x")


def test_cli_validar(tmp_path):
    f = tmp_path / "provas.json"
    f.write_text(json.dumps({"objetivo": "x"}), encoding="utf-8")
    rc, out, _ = run("sp-provas.py", "--validar", str(f))
    assert rc == 1 and "campo em falta" in out


def fechar(vault, repo, slug=SLUG, *extra):
    return run("sp-fechar.py", "--root", str(vault), "--project", PROJECT, slug, "--sem-budget", "--commit-dir", str(repo), *extra)


def test_fecho_gera_pacote_e_fica_registado(tmp_path):
    repo, vault = preparar(tmp_path, extra="ui: nao\n")
    sp_text = (vault / PROJECT / "sp" / "Doing" / f"{SLUG}.md")
    sp_text.write_text(sp_text.read_text(encoding="utf-8") + "\n## Reflect\nReflect fase: ok\n", encoding="utf-8")
    rc, out, err = fechar(vault, repo)
    assert rc == 0, out + err
    pacote = vault / PROJECT / "sp" / "proofs" / SLUG / "provas.json"
    assert pacote.is_file()
    assert json.loads(pacote.read_text(encoding="utf-8"))["gates"][0]["rc"] == 0


def test_fecho_ui_sem_imagem_bloqueia(tmp_path):
    repo, vault = preparar(tmp_path, extra="ui: sim\n")
    f = vault / PROJECT / "sp" / "Doing" / f"{SLUG}.md"
    f.write_text(f.read_text(encoding="utf-8") + "\n## Reflect\nReflect fase: ok\n", encoding="utf-8")
    rc, out, err = fechar(vault, repo)
    assert rc == 1 and "depois" in out + err
    assert f.is_file()


def test_fecho_sem_prova_regista_dispensa(tmp_path):
    repo, vault = preparar(tmp_path, extra="ui: sim\n")
    rc, out, err = fechar(vault, repo, SLUG, "--sem-prova", "sem ecrã")
    assert rc == 0, out + err
    assert "sem ecrã" in (vault / PROJECT / "sp" / "Done" / f"{SLUG}.md").read_text(encoding="utf-8")


def test_sp_antigo_fecha_como_antes(tmp_path):
    repo, vault = preparar(tmp_path, data="2026-11-01", slug="demo-antigo-2026-11-01", extra="ui: sim\n")
    f = vault / PROJECT / "sp" / "Doing" / "demo-antigo-2026-11-01.md"
    f.write_text(f.read_text(encoding="utf-8") + "\n## Reflect\nReflect fase: ok\n", encoding="utf-8")
    rc, out, err = fechar(vault, repo, "demo-antigo-2026-11-01")
    assert rc == 0, out + err
    assert not (vault / PROJECT / "sp" / "proofs" / "demo-antigo-2026-11-01").exists()


def test_corpo_pr_com_validar_reverter_e_imagens(tmp_path):
    pasta = tmp_path / "proofs" / SLUG
    pasta.mkdir(parents=True)
    (pasta / "provas.json").write_text(json.dumps(pacote_valido()), encoding="utf-8")
    extra = pr_corpo.bloco_provas(pasta, "https://github.com/o/r/blob/abc123")
    assert "## Como validar" in extra and "## Como reverter" in extra
    assert "![l](https://github.com/o/r/blob/abc123/d.svg?raw=true)" in extra
    assert "git reset" not in extra
