"""Fixtures partilhadas dos testes de core/scripts."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def _cwd_isolado(monkeypatch, tmp_path_factory):
    """Fora de worktree de agente `sp-move` ignora claims: os testes nunca tocam em `.git/sb-claims` real."""
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))
