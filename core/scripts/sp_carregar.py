"""Helper único de carregamento de scripts por caminho (nomes com hífen não se importam).

Substitui os blocos de `importlib.util.spec_from_file_location` espalhados pelos scripts e testes.

Uso: módulo importado (`from sp_carregar import carregar`); `carregar(caminho, nome=None, registar=True, fresco=False)`
rc: n/a
"""
import importlib.util
import sys
from os import PathLike
from pathlib import Path
from types import ModuleType


def carregar(caminho: str | PathLike[str], nome: str | None = None, *, registar: bool = True, fresco: bool = False) -> ModuleType:
    """Carrega o ficheiro `caminho` como módulo.

    `nome`: nome em `sys.modules` (omissão: o nome do ficheiro com `-` trocado por `_`).
    `registar`: põe o módulo em `sys.modules` antes de o executar (como os scripts faziam).
    `fresco`: volta a executar mesmo que o nome já esteja em `sys.modules`; sem isto, o módulo registado é reutilizado.
    """
    alvo = Path(caminho)
    if not alvo.is_file():
        raise FileNotFoundError(f"script não encontrado: {alvo}")
    nome = nome or alvo.stem.replace("-", "_")
    if registar and not fresco and nome in sys.modules:
        return sys.modules[nome]
    spec = importlib.util.spec_from_file_location(nome, alvo)
    if spec is None or spec.loader is None:
        raise ImportError(f"não é um módulo Python: {alvo}")
    mod = importlib.util.module_from_spec(spec)
    anterior = sys.modules.get(nome)
    if registar:
        sys.modules[nome] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        if registar:
            if anterior is None:
                sys.modules.pop(nome, None)
            else:
                sys.modules[nome] = anterior
        raise
    return mod
