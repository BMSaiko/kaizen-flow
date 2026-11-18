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
    rc, msg, m = run(tmp_path, pr(checks=[ok()]), merge_estrategia="rebase")
    assert rc == 0 and m == ["rebase"]


def test_checks_vermelhos_bloqueiam(tmp_path):
    rc, _, m = run(tmp_path, pr(checks=[bad()]))
    assert rc == 11 and m == []


def test_conflito_rc12(tmp_path):
    rc, _, m = run(tmp_path, pr(mergeable="CONFLICTING", checks=[ok()]))
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
