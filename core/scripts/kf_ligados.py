"""Ficheiros do motor ligados ao pacote kaizen-flow (fonte única: `core/scripts` do pacote).

Usado pelo teste de fonte do vault e por `sp-fechar.py`: um SP que altera um destes ficheiros só
fecha com a cópia do pacote igual (`/kaizen-sync`). Sem o pacote no disco, nada é exigido.

Uso: módulo importado por sp-fechar.py e pelo teste de fonte do vault; sem execução direta
rc: n/a
"""
import os
from collections.abc import Iterable
from pathlib import Path


def pacote() -> Path:
    """Raiz do pacote: KAIZEN_FLOW_HOME ou ~/Documents/code/kaizen-flow."""
    return Path(os.environ.get("KAIZEN_FLOW_HOME") or Path.home() / "Documents" / "code" / "kaizen-flow")


def core_dir(pkg: str | Path | None = None) -> Path | None:
    """`core/scripts` do pacote, ou None se não existir."""
    core = Path(pkg or pacote()) / "core" / "scripts"
    return core if core.is_dir() else None


def ligados(core: str | Path) -> list[str]:
    """Nomes dos `*.py` do pacote (os que têm cópia nos scripts do vault)."""
    return sorted(p.name for p in Path(core).glob("*.py"))


def fora_de_sincronia(scripts: str | Path, core: str | Path, nomes: Iterable[str] | None = None) -> list[str]:
    """Nomes (entre `nomes`, por defeito todos os ligados) cuja cópia em `scripts` falta ou difere do pacote."""
    scripts, core = Path(scripts), Path(core)
    alvo = ligados(core) if nomes is None else [n for n in nomes if (core / n).is_file()]
    return [n for n in alvo if not (scripts / n).is_file() or (scripts / n).read_bytes() != (core / n).read_bytes()]


def tocados(caminhos: Iterable[object], core: str | Path) -> list[str]:
    """Nomes ligados ao pacote entre os caminhos `scripts/<nome>.py` do diff."""
    ls = set(ligados(core))
    out: list[str] = []
    for c in caminhos:
        p = Path(str(c).replace("\\", "/"))
        if len(p.parts) == 2 and p.parts[0] == "scripts" and p.name in ls:
            out.append(p.name)
    return sorted(set(out))
