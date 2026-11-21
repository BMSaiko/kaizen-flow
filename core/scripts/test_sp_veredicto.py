"""sp_veredicto.py: ação ligada a cada veredicto (ajustar, redirecionar, ok com merge, arranque, espera, cadeia)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import sp_veredicto as sv  # noqa: E402
from sp_carregar import carregar  # noqa: E402

sr = carregar(SCRIPTS / "sp-rever.py", "sp_rever", registar=False, fresco=True)

ORIGINAL = ("---\nstatus: Done\nslug: proj-algo-2026-11-13\ndate: 2026-11-13\nupdated: 2026-11-13T19:00:00Z\n"
            "project: proj\npriority: P1\nmodo: auto\nmichi_modelo: complexo\ncommit: auto\npush: auto\npr: auto\nmerge: nunca\n"
            "gates:\n  - cmd: python -m pytest x -q\n  - cmd: python -I scripts/context-budget.py\n---\n# SP\n")
NOVO = "---\nstatus: TODO\nslug: {s}\norigem: veredicto:proj-algo-2026-11-13\n---\n# SP\n\n## Decisões\n- a\n"


@pytest.fixture
def raiz(tmp_path):
    r = tmp_path / "proj"
    (r / "proj" / "sp" / "Done").mkdir(parents=True)
    (r / "proj" / "sp" / "TODO").mkdir(parents=True)
    (r / "proj" / "sp" / "Done" / "proj-algo-2026-11-13.md").write_text(ORIGINAL, encoding="utf-8")
    return r


class FakeRun:
    """Simula sp-new.py (cria o ficheiro), gh e sp-validate."""

    def __init__(self, raiz, gh=None, validar_rc=0):
        self.raiz, self.chamadas, self.gh, self.validar_rc = raiz, [], gh or {}, validar_rc

    def __call__(self, cmd, **kw):
        self.chamadas.append(list(cmd))
        out = ""
        if "sp-new.py" in " ".join(map(str, cmd)):
            slug = cmd[cmd.index("--slug") + 1] + "-2026-11-14"
            p = self.raiz / "proj" / "sp" / "TODO" / f"{slug}.md"
            p.write_text(NOVO.format(s=slug), encoding="utf-8")
            out = str(p) + "\n"
        elif cmd[0] == "gh" and cmd[1:3] == ["pr", "view"]:
            out = json.dumps(self.gh)
        return subprocess.CompletedProcess(cmd, self.validar_rc if "sp-validate.py" in " ".join(map(str, cmd)) else 0, out, "")

    def com(self, trecho):
        return [c for c in self.chamadas if trecho in " ".join(map(str, c))]


def test_frase_vazia_nao_cria_nada(raiz, tmp_path):
    run = FakeRun(raiz)
    with pytest.raises(sv.VeredictoErro):
        sv.criar_ajuste("proj-algo-2026-11-13", "   ", raiz, {}, run=run, semente_dir=tmp_path)
    assert run.chamadas == [] and list((raiz / "proj" / "sp" / "TODO").iterdir()) == []


def test_criar_ajuste_herda_autorizacoes_e_gates_e_fica_em_todo(raiz, tmp_path):
    run = FakeRun(raiz)
    r = sv.criar_ajuste("proj-algo-2026-11-13", "corrige o X", raiz, {}, run=run, semente_dir=tmp_path)
    cmd = run.com("sp-new.py")[0]
    assert cmd[cmd.index("--slug") + 1] == "proj-algo-ajuste-1"
    assert cmd[cmd.index("--origem") + 1] == "veredicto:proj-algo-2026-11-13"
    for k, v in (("--project", "proj"), ("--priority", "P1"), ("--modo", "auto"), ("--michi", "complexo"),
                 ("--commit", "auto"), ("--push", "auto"), ("--pr", "auto"), ("--merge", "nunca")):
        assert cmd[cmd.index(k) + 1] == v
    assert [cmd[i + 1] for i, c in enumerate(cmd) if c == "--gate"] == ["python -m pytest x -q", "python -I scripts/context-budget.py"]
    assert "corrige o X" not in " ".join(cmd), "a frase nunca viaja na linha de comando"
    assert r["acao"] == "em-todo" and r["ajuste"] == "proj-algo-ajuste-1-2026-11-14"
    sp = Path(r["sp"]).read_text(encoding="utf-8")
    assert "corrige o X" in sp.split("## Decisões")[1]
    assert "corrige o X" in Path(r["semente"]).read_text(encoding="utf-8")


def test_ajuste_nao_lanca_painel_sem_arrancar(raiz, tmp_path):
    chamadas = []
    sv.criar_ajuste("proj-algo-2026-11-13", "f", raiz, {}, run=FakeRun(raiz), semente_dir=tmp_path,
                    lancar=lambda sp, semente: chamadas.append(sp) or {"estado": "a-correr"})
    assert len(chamadas) == 1, "só o painel sp-autor que preenche; nunca o michi"


def test_cadeia_numera_e_sugere_redirecionar(raiz, tmp_path):
    todo = raiz / "proj" / "sp" / "TODO"
    assert sv.cadeia("proj-algo-2026-11-13", raiz) == 0
    (todo / "proj-algo-ajuste-1-2026-11-14.md").write_text("x", encoding="utf-8")
    (todo / "proj-algo-ajuste-2-2026-11-14.md").write_text("x", encoding="utf-8")
    assert sv.cadeia("proj-algo-ajuste-2-2026-11-14", raiz) == 2  # ajuste de ajuste conta na mesma cadeia
    run = FakeRun(raiz)
    sv.criar_ajuste("proj-algo-ajuste-2-2026-11-14", "f", raiz, {}, run=run, semente_dir=tmp_path)
    cmd = run.com("sp-new.py")[0]
    assert cmd[cmd.index("--slug") + 1] == "proj-algo-ajuste-3"


def _info():
    return {"acao": "em-todo", "ajuste": "x-ajuste-1-2026-11-14", "sp": "x.md"}


def test_arrancar_lanca_michi(raiz):
    lancados = []
    r = sv.arrancar_ajuste(_info(), validar=lambda sp: (True, ""), vagas=lambda: 2,
                           spawn=lambda slugs: lancados.append(slugs) or [{"slug": slugs[0], "ok": True}])
    assert r["acao"] == "a-correr" and lancados == [["x-ajuste-1-2026-11-14"]]


def test_arrancar_sem_vaga_fica_em_espera_e_retoma(raiz):
    lancados = []
    r = sv.arrancar_ajuste(_info(), validar=lambda sp: (True, ""), vagas=lambda: 0, spawn=lancados.append)
    assert r["acao"] == "em-espera" and lancados == []
    dados = {"a": {"estado": "ajustar", "acao": "em-espera", "ajuste": "x", "sp": "x.md"},
             "b": {"estado": "ok", "acao": "fechado"}}
    vagas = iter([1, 0])
    upd = sv.retomar_em_espera(dados, arrancar=lambda e: {"acao": "a-correr"}, vagas=lambda: next(vagas))
    assert upd == {"a": {"acao": "a-correr"}}


def test_arrancar_validacao_falha(raiz):
    r = sv.arrancar_ajuste(_info(), validar=lambda sp: (False, "faltam secções"), vagas=lambda: 2, spawn=lambda s: 1 / 0)
    assert r["acao"] == "falhou" and "faltam secções" in r["motivo"]


def test_arrancar_spawn_falha(raiz):
    r = sv.arrancar_ajuste(_info(), validar=lambda sp: (True, ""), vagas=lambda: 2,
                           spawn=lambda s: [{"slug": s[0], "ok": False, "erro": "sem painel"}])
    assert r["acao"] == "falhou" and "sem painel" in r["motivo"]


class FakeBackend:
    nome, interativo = "fake", True


def test_redirecionar_abre_grill_com_foco(raiz, tmp_path):
    chamadas = []

    def lancar(sp, semente, **kw):
        chamadas.append((sp, semente, kw))
        return {"estado": "a-correr"}

    prov = {"reverter": ["git revert abc"], "pr": "https://github.com/o/r/pull/1"}
    r = sv.abrir_redirecionar("proj-algo-2026-11-13", "muda de rumo", raiz, prov, semente_dir=tmp_path, lancar=lancar)
    assert r["acao"] == "a-correr"
    sp, semente, kw = chamadas[0]
    assert kw["rotulo"] == "grill" and kw["foco"] is True and callable(kw["prompt_fn"])
    txt = Path(semente).read_text(encoding="utf-8")
    assert "muda de rumo" in txt and "git revert abc" in txt
    p = kw["prompt_fn"](sp, semente)
    assert "\n" not in p and "/grill-me" in p and "--consume" in p and "muda de rumo" not in p


def test_redirecionar_frase_vazia(raiz, tmp_path):
    with pytest.raises(sv.VeredictoErro):
        sv.abrir_redirecionar("proj-algo-2026-11-13", "", raiz, {}, semente_dir=tmp_path, lancar=lambda *a, **k: 1 / 0)


def test_redirecionar_sem_vaga(raiz, tmp_path):
    r = sv.abrir_redirecionar("proj-algo-2026-11-13", "f", raiz, {}, semente_dir=tmp_path,
                              lancar=lambda *a, **k: {"estado": "pendente", "msg": "sem vaga"})
    assert r["acao"] == "em-espera"


def _gh(estado="OPEN", checks=("SUCCESS",)):
    return {"state": estado, "statusCheckRollup": [{"status": "COMPLETED", "conclusion": c} for c in checks]}


PR = {"pr": "https://github.com/o/r/pull/1"}


def test_merge_verde(raiz):
    run = FakeRun(raiz, gh=_gh())
    r = sv.merge_pr_se_verde(PR, run=run)
    assert r["merge"] == "feito"
    m = run.com("merge")[0]
    assert m[:3] == ["gh", "pr", "merge"] and "--merge" in m and "--admin" not in m and "--force" not in m


@pytest.mark.parametrize("gh", [_gh(checks=("SUCCESS", "FAILURE")), _gh(checks=()), _gh(estado="MERGED"), _gh(estado="CLOSED")])
def test_merge_recusado(raiz, gh):
    run = FakeRun(raiz, gh=gh)
    r = sv.merge_pr_se_verde(PR, run=run)
    assert r["merge"] != "feito" and r["motivo"] and run.com("pr merge") == []


def test_merge_sem_pr(raiz):
    run = FakeRun(raiz)
    assert sv.merge_pr_se_verde({}, run=run)["merge"] == "sem-pr" and run.chamadas == []


# ----------------------------------------------------------------- integração com sp-rever


def _entrada(estado, slug):
    return sr._ler_estado(estado)[slug]


@pytest.fixture
def ctx(raiz, tmp_path):
    estado = tmp_path / "sp-revisao.json"
    return {"raiz": raiz, "estado": estado, "run": FakeRun(raiz), "semente_dir": tmp_path,
            "lancar": lambda *a, **k: {"estado": "a-correr"}}


def test_aplicar_ajustar_grava_acao_e_e_idempotente(ctx):
    slug = "proj-algo-2026-11-13"
    r = sr.aplicar_veredicto(slug, "ajustar", "corrige", ctx["estado"], ctx["raiz"], **{k: ctx[k] for k in ("run", "semente_dir", "lancar")})
    e = _entrada(ctx["estado"], slug)
    assert e["estado"] == "ajustar" and e["acao"] == "em-todo" and e["ajuste"] and r["acao"] == "em-todo"
    n = len(ctx["run"].com("sp-new.py"))
    sr.aplicar_veredicto(slug, "ajustar", "corrige", ctx["estado"], ctx["raiz"], **{k: ctx[k] for k in ("run", "semente_dir", "lancar")})
    assert len(ctx["run"].com("sp-new.py")) == n == 1


def test_aplicar_ajustar_frase_vazia_nao_grava(ctx):
    with pytest.raises(sv.VeredictoErro):
        sr.aplicar_veredicto("proj-algo-2026-11-13", "ajustar", "", ctx["estado"], ctx["raiz"], run=ctx["run"], semente_dir=ctx["semente_dir"])
    assert sr._ler_estado(ctx["estado"]) == {} and ctx["run"].chamadas == []


def test_aplicar_ok_faz_merge_so_com_merge_nunca_e_pr(ctx, raiz):
    slug = "proj-algo-2026-11-13"
    pack = raiz / "proj" / "sp" / "proofs" / slug
    pack.mkdir(parents=True)
    (pack / "provas.json").write_text(json.dumps(PR), encoding="utf-8")
    ctx["run"].gh = _gh()
    sr.aplicar_veredicto(slug, "ok", "", ctx["estado"], raiz, run=ctx["run"])
    e = _entrada(ctx["estado"], slug)
    assert e["estado"] == "ok" and e["acao"] == "fechado" and e["merge"] == "feito"


def test_aplicar_ok_checks_vermelhos_regista_motivo(ctx, raiz):
    slug = "proj-algo-2026-11-13"
    pack = raiz / "proj" / "sp" / "proofs" / slug
    pack.mkdir(parents=True)
    (pack / "provas.json").write_text(json.dumps(PR), encoding="utf-8")
    ctx["run"].gh = _gh(checks=("FAILURE",))
    sr.aplicar_veredicto(slug, "ok", "", ctx["estado"], raiz, run=ctx["run"])
    e = _entrada(ctx["estado"], slug)
    assert e["estado"] == "ok" and e["merge"] != "feito" and e["motivo"]


def test_aplicar_falhou_permite_repetir(ctx):
    slug = "proj-algo-2026-11-13"
    sr.gravar_veredicto(slug, "ajustar", "f", ctx["estado"], ctx["raiz"])
    d = sr._ler_estado(ctx["estado"])
    d[slug].update(acao="falhou", ajuste="velho")
    sr._escrever_estado(ctx["estado"], d)
    sr.aplicar_veredicto(slug, "ajustar", "f", ctx["estado"], ctx["raiz"], **{k: ctx[k] for k in ("run", "semente_dir", "lancar")})
    assert len(ctx["run"].com("sp-new.py")) == 1


def test_aplicar_arrancar_sem_vaga_fica_em_espera(ctx):
    slug = "proj-algo-2026-11-13"
    sr.aplicar_veredicto(slug, "ajustar", "f", ctx["estado"], ctx["raiz"], arrancar=True, vagas=lambda: 0,
                         validar=lambda sp: (True, ""), spawn=lambda s: 1 / 0, **{k: ctx[k] for k in ("run", "semente_dir", "lancar")})
    assert _entrada(ctx["estado"], slug)["acao"] == "em-espera"


def test_cli_frase_vazia_rc_64(tmp_path, capsys):
    rc = sr.main(["--veredicto", "proj-algo-2026-11-13", "ajustar", "", "--estado", str(tmp_path / "e.json"), "--root", str(tmp_path)])
    assert rc == 64 and not (tmp_path / "e.json").exists()
