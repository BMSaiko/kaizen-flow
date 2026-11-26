import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pr_fechar
from test_pr_watch import pr, ok, bad


def repo(tmp_path, **kw):
    (tmp_path / "kaizen.config.json").write_text(json.dumps({"desenvolvimento": {"metodo": "worktree-pr", **kw}}))
    return tmp_path


def run(tmp_path, dados, **kw):
    merges = []
    rc, msg = pr_fechar.fechar(
        "7", repo(tmp_path, **kw), fetch_fn=lambda p, r: dados,
        merge_fn=lambda p, e, r: (merges.append(e) or (0, "")), interval=10)
    return rc, msg, merges


def test_verde_faz_merge_com_estrategia(tmp_path):
    rc, _msg, m = run(tmp_path, pr(checks=[ok()]), merge_estrategia="rebase")
    assert rc == 0 and m == ["rebase"]


def test_checks_vermelhos_corrigiveis_rc13_sem_merge(tmp_path):
    rc, msg, m = run(tmp_path, pr(checks=[bad()]))
    assert rc == 13 and m == [] and "corrigível" in msg and "tentativa 1/3" in msg


def test_vermelho_persistente_bloqueia_sp_com_url(tmp_path, monkeypatch):
    regs = []
    monkeypatch.setattr(pr_fechar, "_bloquear", lambda slug, m: regs.append((slug, m)))
    merges = []
    url = "https://github.com/o/r/pull/7"
    rc, msg = pr_fechar.fechar(url, repo(tmp_path), fetch_fn=lambda p, r: pr(checks=[bad()]),
                               merge_fn=lambda p, e, r: (merges.append(e) or (0, "")), interval=10,
                               sp="s", tentativa=3, max_tentativas=3)
    assert rc == 11 and merges == [] and regs and regs[0][0] == "s" and url in regs[0][1]


def test_corrigido_na_tentativa_seguinte_faz_merge(tmp_path):
    cur = {"d": pr(checks=[bad()])}
    merges = []
    kw = {"fetch_fn": lambda p, r: cur["d"], "merge_fn": lambda p, e, r: (merges.append(e) or (0, "")), "interval": 10}
    assert pr_fechar.fechar("7", repo(tmp_path), tentativa=1, **kw)[0] == 13
    cur["d"] = pr(checks=[ok()])  # correção feita e pushed
    assert pr_fechar.fechar("7", repo(tmp_path), tentativa=2, **kw)[0] == 0 and merges == ["squash"]


def test_gate_local_vermelho_com_ci_verde_nao_faz_merge(tmp_path):
    rc, msg, m = fechar_perfil(tmp_path, lambda r, p: "npm test")
    assert rc == 13 and m == [] and "npm test" in msg


def test_conflito_rc12_bloqueia_logo(tmp_path, monkeypatch):
    regs = []
    monkeypatch.setattr(pr_fechar, "_bloquear", lambda slug, m: regs.append(m))
    rc, _, m = run(tmp_path, pr(mergeable="CONFLICTING", checks=[ok()]), )
    assert rc == 12 and m == []


def test_review_pedida_nao_faz_merge(tmp_path):
    d = pr(review="REVIEW_REQUIRED", checks=[ok()])
    rc = pr_fechar.fechar("7", repo(tmp_path), watch_fn=lambda p, r: 0,
                          fetch_fn=lambda p, r: d, merge_fn=lambda *a: (0, ""))[0]
    assert rc == 11


def test_pr_merge_pergunta_nao_faz_merge(tmp_path):
    rc, _, m = run(tmp_path, pr(checks=[ok()]), pr_merge="pergunta")
    assert rc == 10 and m == []


def test_sem_metodo_rc64(tmp_path):
    (tmp_path / "kaizen.config.json").write_text("{}")
    assert pr_fechar.fechar("7", tmp_path)[0] == 64


def test_gh_merge_falha(tmp_path):
    rc, msg = pr_fechar.fechar("7", repo(tmp_path), fetch_fn=lambda p, r: pr(checks=[ok()]),
                               merge_fn=lambda *a: (1, "boom"), interval=10)
    assert rc == 11 and "boom" in msg


def perfil_repo(tmp_path, **q):
    r = repo(tmp_path)
    cfg = json.loads((r / "kaizen.config.json").read_text())
    cfg["qualidade"] = {"bloqueantes": ["x"], **q}
    (r / "kaizen.config.json").write_text(json.dumps(cfg))
    return r


def fechar_perfil(tmp_path, gates_fn, **kw):
    merges = []
    rc, msg = pr_fechar.fechar("7", perfil_repo(tmp_path, **kw.pop("q", {})), fetch_fn=lambda p, r: pr(checks=[ok()]),
                               merge_fn=lambda p, e, r: (merges.append(e) or (0, "")), interval=10,
                               gates_fn=gates_fn, **kw)
    return rc, msg, merges


def test_gate_bloqueante_vermelho_nao_faz_merge_e_bloqueia_sp(tmp_path, monkeypatch):
    regs = []
    monkeypatch.setattr(pr_fechar, "_bloquear", lambda slug, m: regs.append((slug, m)))
    rc, msg, m = fechar_perfil(tmp_path, lambda r, p: "npm test", sp="meu-sp", tentativa=3)
    assert rc == 11 and m == [] and "npm test" in msg
    assert regs == [("meu-sp", "gate bloqueante vermelho: npm test; PR 7; 3 tentativas esgotadas")]


def test_perfil_verde_exige_pentest_e_review(tmp_path, monkeypatch):
    regs = []
    monkeypatch.setattr(pr_fechar, "_bloquear", lambda slug, m: regs.append(m))
    rc, msg, m = fechar_perfil(tmp_path, lambda r, p: None, sp="s")
    assert rc == 11 and m == [] and "pentest" in regs[0]
    pent, rev = tmp_path / "p.txt", tmp_path / "r.json"
    pent.write_text("sem achados\n")
    rev.write_text(json.dumps({"veredicto": "CORRIGIR"}))
    rc, _, m = fechar_perfil(tmp_path, lambda r, p: None, pentest_relatorio=str(pent), review_estado=str(rev))
    assert rc == 11 and m == [] and "review" in regs[-1]
    rev.write_text(json.dumps({"veredicto": "APROVADO"}))
    rc, _, m = fechar_perfil(tmp_path, lambda r, p: None, pentest_relatorio=str(pent), review_estado=str(rev))
    assert rc == 0 and m == ["squash"]


def test_fases_vazias_so_gates_e_sem_perfil_igual_ao_antigo(tmp_path):
    rc, _, m = fechar_perfil(tmp_path, lambda r, p: None, q={"fases": []})
    assert rc == 0 and m == ["squash"]
    rc, _, m = run(tmp_path, pr(checks=[ok()]))
    assert rc == 0 and m == ["squash"]


def test_bloquear_sem_sp_ou_fora_de_fila_nao_rebenta(capsys):
    pr_fechar._bloquear(None, "m")
    pr_fechar._bloquear("slug-inexistente-xyz", "m")
