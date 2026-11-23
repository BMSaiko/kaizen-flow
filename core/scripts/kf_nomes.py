"""Nomes canónicos de painéis: `heimdall` (principal, no path do Second Brain) e `<papel>-<slug>` para os restantes.

Registo JSON atómico nome→pane em `<estado>/nomes.json` (mesma pasta do estado das filas, `SP_FILA_ROOT`).
Entradas cujo pane já não está vivo são podadas na leitura quando se passa `vivos`. Sem registo, ids opacos
e títulos antigos continuam válidos (`ref_a_pane` devolve a referência tal e qual).

Uso: módulo importado por sp_fila_paineis, handoff_spawn, kf_term_orq e kf_term_ls; sem execução direta
rc: n/a
"""
import contextlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_painel_estado as pe  # noqa: E402

NOME_PRINCIPAL = "heimdall"
PAPEIS = ("sp", "autor", "handoff", "fila", "livre")
MAX_NOME = 48
FICHEIRO = "nomes.json"
ENV_SB = "SB_ROOT"
_VALIDO = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def raiz_sb():
    """Raiz do Second Brain (`SB_ROOT` ou `~/Documents/Second Brain`)."""
    return os.environ.get(ENV_SB) or str(Path.home() / "Documents" / "Second Brain")


def _mesmo_caminho(a, b):
    def norm(p):
        return str(p).replace("\\", "/").rstrip("/").lower()
    return bool(a) and norm(a) == norm(b)


def _limpar(texto):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(texto).lower())).strip("-")


def nome_painel(papel, slug, existentes):
    """`<papel>-<slug>` em minúsculas `[a-z0-9-]`, ≤48; colisão → `-2`, `-3`… (como `titulo_livre`)."""
    if papel not in PAPEIS:
        raise ValueError(f"papel inválido {papel!r}: use {', '.join(PAPEIS)}")
    s = _limpar(slug)
    if not s:
        raise ValueError(f"slug sem caracteres válidos: {slug!r}")
    usados = set(existentes)
    base = f"{papel}-{s}"[:MAX_NOME].rstrip("-")
    if base not in usados:
        return base
    n = 2
    while True:
        suf = f"-{n}"
        cand = base[:MAX_NOME - len(suf)].rstrip("-") + suf
        if cand not in usados:
            return cand
        n += 1


def _caminho(root):
    return pe.raiz(root) / FICHEIRO


def _ler(root):
    p = _caminho(root)
    try:
        dados = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(dados, dict):
            raise ValueError("raiz não é objeto")
        return {k: v for k, v in dados.items() if isinstance(v, dict)}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        print(f"aviso: registo de nomes corrompido ({p}); recriado vazio", file=sys.stderr)
        return {}


def _escrever(dados, root):
    p = _caminho(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, p)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def _podar(dados, vivos):
    if vivos is None:
        return dados, False
    vivos = {str(v) for v in vivos}
    ficam = {n: e for n, e in dados.items() if str(e.get("pane")) in vivos}
    return ficam, len(ficam) != len(dados)


def _lido(vivos, root):
    dados, mudou = _podar(_ler(root), vivos)
    if mudou:
        _escrever(dados, root)
    return dados


def registar(nome, backend, pane, cwd, papel, slug, root=None, raiz_sb=None):
    """Regista `nome`→`pane`. `heimdall` só para o pane cujo cwd é a raiz do Second Brain, e só um."""
    if nome == NOME_PRINCIPAL:
        if not _mesmo_caminho(cwd, raiz_sb or globals()["raiz_sb"]()):
            raise ValueError(f"o nome {NOME_PRINCIPAL} é reservado ao painel do Second Brain")
    elif len(nome) > MAX_NOME or not _VALIDO.match(nome):
        raise ValueError(f"nome inválido {nome!r}: minúsculas [a-z0-9-], ≤{MAX_NOME}")
    dados = _ler(root)
    atual = dados.get(nome)
    if atual and str(atual.get("pane")) != str(pane):
        raise ValueError(f"o nome {nome} já pertence ao painel {atual.get('pane')}" + (
            f" ({NOME_PRINCIPAL} só tem um painel)" if nome == NOME_PRINCIPAL else ""))
    dados[nome] = {"nome": nome, "backend": backend, "pane": str(pane), "cwd": str(cwd), "papel": papel, "slug": slug,
                   "criado": (atual or {}).get("criado") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    _escrever(dados, root)
    return dados[nome]


def resolver(nome, vivos=None, root=None):
    """Entrada do registo para `nome` (None se não existe ou o pane morreu)."""
    return _lido(vivos, root).get(nome)


def remover(nome, root=None):
    """Tira `nome` do registo; True se existia. `heimdall` não se remove."""
    if nome == NOME_PRINCIPAL:
        raise PermissionError(f"o painel {NOME_PRINCIPAL} não se fecha nem se renomeia")
    dados = _ler(root)
    if nome not in dados:
        return False
    del dados[nome]
    _escrever(dados, root)
    return True


def listar(vivos=None, root=None):
    """Entradas do registo por nome, podadas contra `vivos` (ids) quando dado."""
    dados = _lido(vivos, root)
    return [dados[n] for n in sorted(dados)]


def detetar_heimdall(backend, vivos_cwd, root=None, raiz_sb=None):
    """Regista `heimdall` no pane cujo cwd é a raiz do Second Brain (`vivos_cwd` = {id: cwd}); devolve o id ou None."""
    sb = raiz_sb or globals()["raiz_sb"]()
    for pane, cwd in vivos_cwd.items():
        if _mesmo_caminho(cwd, sb):
            atual = _ler(root).get(NOME_PRINCIPAL)
            if atual and str(atual.get("pane")) != str(pane) and str(atual.get("pane")) in {str(p) for p in vivos_cwd}:
                return str(atual["pane"])  # já há um heimdall vivo
            dados = _ler(root)
            dados.pop(NOME_PRINCIPAL, None)
            _escrever(dados, root)
            registar(NOME_PRINCIPAL, backend, pane, cwd, "livre", NOME_PRINCIPAL, root=root, raiz_sb=sb)
            return str(pane)
    return None


def ref_a_pane(ref, vivos=None, root=None):
    """Nome → id do pane (se registado e vivo); caso contrário `ref` tal e qual (id opaco continua válido)."""
    e = resolver(ref, vivos=vivos, root=root)
    return str(e["pane"]) if e else ref


def nome_de_pane(pane, root=None):
    """Nome registado para `pane`, ou None."""
    for e in _ler(root).values():
        if str(e.get("pane")) == str(pane):
            return e.get("nome")
    return None
