"""Sp-fila com painéis: estado em disco por fila e por SP (escrita atómica, teto global de painéis, migração do estado antigo).

Disposição: `<raiz>/<fila-id>/fila.json` (programa, modo, limites, ordem) e `<raiz>/<fila-id>/<slug>.json`
(estado, modelo, worktree, pane, inicio, fim, msg). A raiz é `~/.claude/sp-fila`, a variável `SP_FILA_ROOT`
ou o argumento `root`. Todas as escritas correm sob um bloqueio global (`<raiz>/estado.lock`, O_CREAT|O_EXCL),
por isso a contagem do teto e a ocupação da vaga são um só passo. Só stdlib.

Uso: módulo importado por sp-estado.py e sp_fila_estado.py; sem execução direta
rc: n/a
"""
import os
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sp_disco import LOCK_VELHO_S, _lock_obsoleto, _pid_do_lock, _recuperar, bloqueio, guardar, ler_json, pid_vivo  # noqa: E402,F401
from sp_estado_base import (ESTADOS, ILEGIVEL, ErroEstado, SemVaga, _ler_json, _ler_sp, _nome, _slug, _ts,  # noqa: E402,F401
                            fila_id, CAMPOS, FINAIS, NAO_SP, _campos, _dirs, _ficheiros_sp, _procurar, _sp_novo)

MAX_PARALELO = 3  # teto global de painéis ativos, somando todas as filas
ENV_ROOT = "SP_FILA_ROOT"
ATIVOS = frozenset({"a-correr", "pergunta"})  # ocupam vaga
TRANSICOES = {
    "pendente": {"a-correr", "bloqueado", "falhou"},
    "a-correr": {"pergunta", "done", "bloqueado", "falhou"},
    "pergunta": {"a-correr", "done", "bloqueado", "falhou"},
    "bloqueado": {"a-correr", "pendente", "falhou"},
    "falhou": {"pendente"},
    "done": {"bloqueado"},  # só o vigia: done que não pode integrar (SP manual, gates, conflito)
}
MODOS = ("sequencial", "paralelo")


# --- nomes, raiz e leitura ---

def raiz(root=None):
    """Pasta do estado: argumento, variável `SP_FILA_ROOT` ou `~/.claude/sp-fila`."""
    return Path(root or os.environ.get(ENV_ROOT) or Path.home() / ".claude" / "sp-fila")


def _ativos(r):
    """SPs que ocupam vaga em todas as filas; um JSON ilegível conta como ocupado (na dúvida não se abre mais um painel)."""
    n = 0
    for d in _dirs(r):
        for p in _ficheiros_sp(d):
            try:
                n += _ler_sp(p)["estado"] in ATIVOS
            except FileNotFoundError:
                pass
            except ErroEstado:
                n += 1
    return n


@contextmanager
def _exclusivo(root):
    r = raiz(root)
    r.mkdir(parents=True, exist_ok=True)
    with bloqueio(r / "estado"):
        yield r


# --- API ---

def criar_fila(programa=None, modo="paralelo", limites=None, ordem=(), root=None, agora=None):
    """Cria `<fila-id>/fila.json` e um `<slug>.json` em `pendente` por SP da ordem; devolve o fila-id."""
    if modo not in MODOS:
        raise ErroEstado(f"modo inválido: {modo!r} (válidos: {', '.join(MODOS)})")
    ordem = [_slug(s) for s in ordem]
    base = fila_id(programa, agora)
    with _exclusivo(root) as r:
        fid, n = base, 1
        while (r / fid).exists():
            if programa:
                raise ErroEstado(f"fila já existe: {fid}")
            n += 1
            fid = f"{base}-{n}"
        d = r / fid
        d.mkdir()
        for slug in ordem:
            guardar(d / f"{slug}.json", _sp_novo(fid, slug, agora))
        guardar(d / "fila.json", {"fila": fid, "programa": programa, "modo": modo, "limites": dict(limites or {}),
                                  "ordem": ordem, "criada": _ts(agora)})
    return fid


def registar(fila, slug, root=None, agora=None, **campos):
    """Cria o SP na fila (em `pendente`) ou atualiza-lhe `modelo`/`worktree`/`pane`, sem mexer no estado."""
    _nome(fila, "fila")
    _slug(slug)
    campos = _campos(campos)
    with _exclusivo(root) as r:
        d = r / fila
        try:
            dados_fila = _ler_json(d / "fila.json")
        except FileNotFoundError:
            raise ErroEstado(f"fila desconhecida: {fila}") from None
        p = d / f"{slug}.json"
        try:
            sp = _ler_sp(p)
        except FileNotFoundError:
            sp = _sp_novo(fila, slug, agora)
        sp.update(campos)
        sp["atualizado"] = _ts(agora)
        guardar(p, sp)
        if slug not in dados_fila.setdefault("ordem", []):
            dados_fila["ordem"].append(slug)
            guardar(d / "fila.json", dados_fila)
    return sp


def ler(fila, slug=None, root=None):
    """Com `slug`: o estado desse SP. Sem ele: `{"fila": {...}, "sps": {slug: {...}}}` pela ordem da fila."""
    d = raiz(root) / _nome(fila, "fila")
    if slug is not None:
        try:
            return _ler_sp(d / f"{_slug(slug)}.json")
        except FileNotFoundError:
            raise ErroEstado(f"slug desconhecido: {slug} (fila {fila})") from None
    try:
        dados = _ler_json(d / "fila.json")
    except FileNotFoundError:
        raise ErroEstado(f"fila desconhecida: {fila}") from None
    sps = {p.stem: _ler_sp(p) for p in _ficheiros_sp(d)}
    ordem = [s for s in dados.get("ordem", []) if s in sps] + [s for s in sps if s not in dados.get("ordem", [])]
    return {"fila": dados, "sps": {s: sps[s] for s in ordem}}


def procurar(slug, root=None):
    """Fila que regista o slug; em várias, a que ainda não o acabou e, entre essas, a mais recente."""
    return _procurar(raiz(root), _slug(slug))


def vagas_livres(root=None):
    """Vagas por ocupar: `MAX_PARALELO` menos os SPs `a-correr` e `pergunta` de todas as filas."""
    return max(0, MAX_PARALELO - _ativos(raiz(root)))


def transitar(slug, estado, msg=None, fila=None, root=None, agora=None, **campos):
    """Muda o estado do SP (na fila dada ou na que o regista). Inválido = `ErroEstado` sem escrever.

    Entrar num estado ativo a partir de um que não ocupa vaga respeita o teto global (`SemVaga`)."""
    _slug(slug)
    if estado not in ESTADOS:
        raise ErroEstado(f"estado inválido: {estado!r} (válidos: {', '.join(ESTADOS)})")
    campos = _campos(campos)
    if fila is not None:
        _nome(fila, "fila")
    if not raiz(root).is_dir():
        raise ErroEstado(f"slug desconhecido: {slug} (nenhuma fila o regista)")
    with _exclusivo(root) as r:
        fid = fila or _procurar(r, slug)
        p = r / fid / f"{slug}.json"
        try:
            sp = _ler_sp(p)
        except FileNotFoundError:
            raise ErroEstado(f"slug desconhecido: {slug} (fila {fid})") from None
        atual = sp["estado"]
        if estado != atual and estado not in TRANSICOES[atual]:
            raise ErroEstado(f"transição inválida: {slug} {atual} → {estado}")
        if estado in ATIVOS and atual not in ATIVOS and _ativos(r) >= MAX_PARALELO:
            raise SemVaga(f"sem vaga: {MAX_PARALELO} painéis ativos no total das filas; {slug} fica em {atual}")
        agora_ts = _ts(agora)
        sp.update(campos)
        if msg is not None or estado != atual:
            sp["msg"] = msg
        if estado == "pendente":
            sp["inicio"] = None
        elif estado == "a-correr" and not sp.get("inicio"):
            sp["inicio"] = agora_ts
        sp["fim"] = agora_ts if estado in FINAIS else None
        sp["estado"] = estado
        sp["atualizado"] = agora_ts
        guardar(p, sp)
    return sp


def reclamar_vaga(slug, fila=None, root=None, agora=None, **campos):
    """Ocupa uma vaga pondo o SP em `a-correr` (com `modelo`/`worktree`/`pane`); False se o teto está atingido.

    Contar e ocupar acontecem sob o mesmo bloqueio O_CREAT|O_EXCL: dois processos nunca ficam com a mesma vaga."""
    try:
        transitar(slug, "a-correr", fila=fila, root=root, agora=agora, **campos)
    except SemVaga:
        return False
    return True


def filas(root=None):
    """Todas as filas com os seus SPs, tolerante a JSON ilegível (para listar e vigiar sem rebentar)."""
    out = []
    for d in _dirs(raiz(root)):
        try:
            dados = dict(_ler_json(d / "fila.json"))
        except (ErroEstado, FileNotFoundError):
            dados = {"erro": f"fila.json {ILEGIVEL}"}
        dados["fila"] = d.name
        sps = {}
        for p in _ficheiros_sp(d):
            try:
                sps[p.stem] = _ler_sp(p)
            except FileNotFoundError:
                continue
            except ErroEstado:
                sps[p.stem] = {"slug": p.stem, "fila": d.name, "estado": ILEGIVEL}
        ordem = [s for s in dados.get("ordem") or [] if s in sps]
        dados["sps"] = [sps[s] for s in ordem + [s for s in sps if s not in ordem]]
        out.append(dados)
    return out


def remover_fila(fila, root=None):
    """Apaga `<fila-id>/` (fila abandonada com `sp-fila.py --parar`): as vagas dos seus SPs ficam livres. True se existia."""
    fid = _nome(fila, "fila")
    with _exclusivo(root) as r:
        d = r / fid
        if not (d / "fila.json").is_file():
            return False
        shutil.rmtree(d)
    return True


def filas_ativas(root=None):
    """Filas com pelo menos um SP por acabar (qualquer estado que não `done` nem `falhou`)."""
    return [f for f in filas(root) if any(sp["estado"] not in FINAIS for sp in f["sps"])]


def migrar_antigo(path=None, root=None, agora=None):
    """Converte o `~/.claude/sp-fila-estado.json` numa fila (lógica em `sp_estado_migracao`); fila-id ou None se não há ficheiro."""
    import sp_estado_migracao
    return sp_estado_migracao.migrar_antigo(path, root=root, agora=agora)
