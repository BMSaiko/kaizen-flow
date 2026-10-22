"""Lê `kaizen.config.json` na raiz do repo; sem ficheiro ou chave, devolve o defeito.

Chaves: `spRoot` (raiz dos SPs) e `docsRoot` (raiz dos DR/DP), relativas à raiz do repo.
"""
import json
from pathlib import Path

DEFAULT_SP_ROOT = "knowledge/projects/kaizen"
DEFAULT_DOCS_ROOT = "knowledge/projects"
CONFIG_NAME = "kaizen.config.json"


def _read(repo):
    try:
        data = json.loads((Path(repo) / CONFIG_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def sp_root(repo):
    return Path(repo) / _read(repo).get("spRoot", DEFAULT_SP_ROOT)


def docs_root(repo):
    return Path(repo) / _read(repo).get("docsRoot", DEFAULT_DOCS_ROOT)
