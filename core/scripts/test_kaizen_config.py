import json
from pathlib import Path
from sp_carregar import carregar  # noqa: E402

HERE = Path(__file__).resolve().parent


def load(name, file):
    mod = carregar(HERE / file, name, fresco=True)
    return mod


cfg = load("kaizen_config", "kaizen_config.py")


def test_defaults_without_config(tmp_path):
    assert cfg.sp_root(tmp_path) == tmp_path / "knowledge/projects/kaizen"
    assert cfg.docs_root(tmp_path) == tmp_path / "knowledge/projects"


def test_alternative_root(tmp_path):
    (tmp_path / "kaizen.config.json").write_text(json.dumps({"spRoot": "work/sps", "docsRoot": "work/docs"}))
    assert cfg.sp_root(tmp_path) == tmp_path / "work/sps"
    assert cfg.docs_root(tmp_path) == tmp_path / "work/docs"


def test_partial_and_invalid_config(tmp_path):
    (tmp_path / "kaizen.config.json").write_text(json.dumps({"spRoot": "x"}))
    assert cfg.docs_root(tmp_path) == tmp_path / "knowledge/projects"
    (tmp_path / "kaizen.config.json").write_text("{not json")
    assert cfg.sp_root(tmp_path) == tmp_path / "knowledge/projects/kaizen"


def test_scripts_use_config_root(tmp_path, monkeypatch):
    sp_list = load("sp_list_t", "sp-list.py")
    doc_list = load("doc_list_t", "doc-list.py")
    assert sp_list.default_root(tmp_path) == tmp_path / "knowledge/projects/kaizen"
    (tmp_path / "kaizen.config.json").write_text(json.dumps({"spRoot": "a/b", "docsRoot": "a/c"}))
    assert sp_list.default_root(tmp_path) == tmp_path / "a/b"
    assert doc_list.default_root(tmp_path) == tmp_path / "a/c"


def _dev(tmp_path, **kw):
    (tmp_path / "kaizen.config.json").write_text(json.dumps({"desenvolvimento": kw}))


def test_desenvolvimento_defaults_por_metodo(tmp_path):
    assert cfg.desenvolvimento(tmp_path) is None
    _dev(tmp_path, metodo="worktree-pr")
    d = cfg.desenvolvimento(tmp_path)
    assert (d["commit"], d["push"], d["pr"]) == ("auto", "auto", "auto")
    assert d["pr_vigia"] is True and d["pr_merge"] == "auto-se-verde"
    assert d["ramo_principal"] == "main" and d["merge_estrategia"] == "squash"
    _dev(tmp_path, metodo="worktree-merge")
    d = cfg.desenvolvimento(tmp_path)
    assert (d["commit"], d["push"], d["pr"]) == ("auto", "nunca", "nunca")
    _dev(tmp_path, metodo="direto")
    d = cfg.desenvolvimento(tmp_path)
    assert (d["commit"], d["push"], d["pr"]) == ("pergunta",) * 3


def test_desenvolvimento_invalido_ou_sobreposto(tmp_path):
    _dev(tmp_path, metodo="x")
    assert cfg.desenvolvimento(tmp_path) is None
    _dev(tmp_path, metodo="worktree-pr", push="lixo", pr="pergunta", merge_estrategia="rebase")
    d = cfg.desenvolvimento(tmp_path)
    assert d["push"] == "auto" and d["pr"] == "pergunta" and d["merge_estrategia"] == "rebase"


def test_guarda_ramo_principal(tmp_path):
    _dev(tmp_path, metodo="worktree-pr")
    assert cfg.metodo_autorizacoes(tmp_path, "agent/x") == {"commit": "auto", "push": "auto", "pr": "auto"}
    assert cfg.metodo_autorizacoes(tmp_path, "main") == {"commit": "pergunta", "push": "pergunta", "pr": "pergunta"}
    assert cfg.metodo_autorizacoes(tmp_path, "master")["commit"] == "pergunta"
    assert cfg.metodo_autorizacoes(tmp_path, "") ["push"] == "pergunta"
    (tmp_path / "kaizen.config.json").write_text("{}")
    assert cfg.metodo_autorizacoes(tmp_path, "agent/x") is None


def test_herdr_defeitos_e_valores(tmp_path):
    import kaizen_config as kc
    assert kc.herdr(tmp_path) == {"maxPanesPorTab": 2, "workspacePorProjeto": True}
    (tmp_path / "kaizen.config.json").write_text('{"herdr": {"maxPanesPorTab": 3, "workspacePorProjeto": false}}', encoding="utf-8")
    assert kc.herdr(tmp_path) == {"maxPanesPorTab": 3, "workspacePorProjeto": False}
    (tmp_path / "kaizen.config.json").write_text('{"herdr": {"maxPanesPorTab": 0, "workspacePorProjeto": "x"}}', encoding="utf-8")
    assert kc.herdr(tmp_path) == {"maxPanesPorTab": 2, "workspacePorProjeto": True}
