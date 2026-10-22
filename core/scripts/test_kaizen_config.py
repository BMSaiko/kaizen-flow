import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
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
