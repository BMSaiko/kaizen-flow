"""Helper único de carregamento de scripts por caminho (nomes com hífen não se importam).

Substitui os blocos de `importlib.util.spec_from_file_location` espalhados pelos scripts e testes.

Uso: módulo importado (`from sp_carregar import carregar`); `carregar(caminho, nome=None, registar=True, fresco=False)`
rc: n/a
"""
import importlib.util
import sys
from pathlib import Path


def carregar(caminho, nome=None, *, registar=True, fresco=False):
    """Carrega o ficheiro `caminho` como módulo.

    `nome`: nome em `sys.modules` (omissão: o nome do ficheiro com `-` trocado por `_`).
    `registar`: põe o módulo em `sys.modules` antes de o executar (como os scripts faziam).
    `fresco`: volta a executar mesmo que o nome já esteja em `sys.modules`; sem isto, o módulo registado é reutilizado.
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        raise FileNotFoundError(f"script não encontrado: {caminho}")
    nome = nome or caminho.stem.replace("-", "_")
    if registar and not fresco and nome in sys.modules:
        return sys.modules[nome]
    spec = importlib.util.spec_from_file_location(nome, caminho)
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
