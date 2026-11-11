"""Sp-fila com painéis: estado em disco por fila e por SP (escrita atómica, teto global de painéis, migração do estado antigo).

Disposição: `<raiz>/<fila-id>/fila.json` (programa, modo, limites, ordem) e `<raiz>/<fila-id>/<slug>.json`
(estado, modelo, worktree, pane, inicio, fim, msg). A raiz é `~/.claude/sp-fila`, a variável `SP_FILA_ROOT`
ou o argumento `root`. Todas as escritas correm sob um bloqueio global (`<raiz>/estado.lock`, O_CREAT|O_EXCL),
por isso a contagem do teto e a ocupação da vaga são um só passo. Só stdlib.

Uso: módulo importado por sp-estado.py e sp_fila_estado.py; sem execução direta
rc: n/a
"""
import json
import os
import re
import shutil
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

MAX_PARALELO = 3  # teto global de painéis ativos, somando todas as filas
ENV_ROOT = "SP_FILA_ROOT"
ESTADOS = ("pendente", "a-correr", "pergunta", "done", "bloqueado", "falhou")
ATIVOS = frozenset({"a-correr", "pergunta"})  # ocupam vaga
FINAIS = frozenset({"done", "falhou"})
TRANSICOES = {
    "pendente": {"a-correr", "bloqueado", "falhou"},
    "a-correr": {"pergunta", "done", "bloqueado", "falhou"},
    "pergunta": {"a-correr", "done", "bloqueado", "falhou"},
    "bloqueado": {"a-correr", "pendente", "falhou"},
    "falhou": {"pendente"},
    "done": {"bloqueado"},  # só o vigia: done que não pode integrar (SP manual, gates, conflito)
}
MODOS = ("sequencial", "paralelo")
CAMPOS = ("modelo", "worktree", "pane")
ILEGIVEL = "ilegível"
LOCK_VELHO_S = 60  # um bloqueio mais antigo, sem pid legível, é de uma sessão morta
_NOME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,149}$")
_DISPOSITIVO = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\.|$)", re.IGNORECASE)
_LIMITES_ANTIGOS = ("max", "ate", "horas", "usd", "orcamento", "max_falhas", "concorrencia")


class ErroEstado(Exception):
    """Pedido recusado sem escrever (nome inválido, slug desconhecido, transição inválida, JSON ilegível)."""


class SemVaga(ErroEstado):
    """O teto global de painéis ativos está atingido."""


# --- primitivas partilhadas com sp_fila_estado (bloqueio e escrita atómica) ---

def pid_vivo(pid):
    """True se o processo `pid` existe. Windows: OpenProcess + GetExitCodeProcess (259 = ainda ativo); nunca `os.kill(pid, 0)`, que lá termina o processo."""
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except OSError:  # PermissionError: existe, é de outro utilizador
            return True
        return True
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED: existe; qualquer outro erro (87 = pid inválido): não existe
    try:
        codigo = wintypes.DWORD()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(codigo))) and codigo.value == 259  # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def _lock_obsoleto(lock):
    """Com pid legível manda o pid (dono morto = obsoleto, vivo = nunca); sem ele (formato antigo, escrita a meio) manda a idade."""
    try:
        pid = int(lock.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return time.time() - lock.stat().st_mtime > LOCK_VELHO_S
    return not pid_vivo(pid)


def _pid_do_lock(lock):
    try:
        return int(lock.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _recuperar(lock):
    """Apaga o lock de um dono morto; True se apagou.

    Entre ler o pid e saber que morreu, o dono pode ter largado o lock e outro processo criado um novo: apagar aí
    tirava o bloqueio a um dono vivo. Por isso a recuperação corre uma de cada vez (`<lock>.rec`, O_CREAT|O_EXCL)
    e só apaga se o lock ainda tem o mesmo pid morto (um lock com pid morto já ninguém larga nem recria)."""
    if not _lock_obsoleto(lock):
        return False
    guarda = Path(f"{lock}.rec")
    try:
        os.close(os.open(guarda, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except (FileExistsError, PermissionError):
        try:
            if time.time() - guarda.stat().st_mtime > LOCK_VELHO_S:  # recuperação que morreu a meio
                guarda.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    try:
        pid = _pid_do_lock(lock)
        if pid is None:
            morto = time.time() - lock.stat().st_mtime > LOCK_VELHO_S
        else:
            morto = not pid_vivo(pid) and _pid_do_lock(lock) == pid
        if morto:
            lock.unlink(missing_ok=True)
        return morto
    finally:
        try:
            guarda.unlink(missing_ok=True)
        except OSError:  # fica para a recuperação por idade
            pass


@contextmanager
def bloqueio(path, espera=15.0):
    """Exclusão mútua entre processos sobre `path`: ficheiro `<path>.lock` (guarda o pid do dono) criado com O_CREAT|O_EXCL.

    Recupera o lock de um dono morto de imediato e o de mtime > LOCK_VELHO_S (sem pid legível)."""
    lock = Path(f"{path}.lock")
    limite_t = time.monotonic() + espera
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            break
        except (FileExistsError, PermissionError):  # Windows: PermissionError se o dono está a apagar o .lock
            try:
                if _recuperar(lock):
                    continue
            except OSError:
                pass
            if time.monotonic() > limite_t:
                raise TimeoutError(f"estado bloqueado há demasiado tempo: {lock}")
            time.sleep(0.02)
    try:
        yield
    finally:
        for tentativa in range(100):
            try:
                lock.unlink(missing_ok=True)
                break
            except PermissionError:  # Windows: antivírus/indexador seguram o .lock; largar sem o apagar bloquearia os outros
                if tentativa == 99:
                    raise
                time.sleep(0.02)


def guardar(path, estado):
    """Escrita atómica: ficheiro temporário + os.replace (um leitor nunca vê JSON a meio)."""
    tmp = Path(f"{path}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    for tentativa in range(500):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: um leitor sem bloqueio (painel, vigia) tem o destino aberto
            if tentativa == 499:
                raise
            time.sleep(0.02)


# --- nomes, raiz e leitura ---

def raiz(root=None):
    """Pasta do estado: argumento, variável `SP_FILA_ROOT` ou `~/.claude/sp-fila`."""
    return Path(root or os.environ.get(ENV_ROOT) or Path.home() / ".claude" / "sp-fila")


def _nome(valor, que):
    """Um nome (fila ou slug) vira nome de ficheiro: só letras, dígitos, `.`, `_` e `-`, sem `..`."""
    if not isinstance(valor, str) or not _NOME.match(valor) or ".." in valor or valor.endswith("."):
        raise ErroEstado(f"{que} inválido: {valor!r}")
    if _DISPOSITIVO.match(valor):  # Windows: `NUL.json` é o dispositivo, não um ficheiro
        raise ErroEstado(f"{que} inválido: {valor!r} (nome reservado no Windows)")
    return valor


def _slug(valor):
    if _nome(valor, "slug").lower() == "fila":
        raise ErroEstado(f"slug inválido: {valor!r} (reservado)")
    return valor


def fila_id(programa=None, agora=None):
    """Id da fila: o slug da mãe (programa) ou `fila-AAAAMMDD-HHMMSS` na fila sem programa."""
    if programa:
        return _nome(programa, "programa")
    return "fila-" + (agora or datetime.now()).strftime("%Y%m%d-%H%M%S")


def _ts(agora=None):
    return (agora or datetime.now()).isoformat(timespec="seconds")


def _ler_json(path):
    try:
        dados = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as e:
        raise ErroEstado(f"estado {ILEGIVEL}: {path} ({e})") from e
    if not isinstance(dados, dict):
        raise ErroEstado(f"estado {ILEGIVEL}: {path} (não é um objeto JSON)")
    return dados


def _ler_sp(path):
    dados = _ler_json(path)
    if dados.get("estado") not in ESTADOS:
        raise ErroEstado(f"estado {ILEGIVEL}: {path} (estado {dados.get('estado')!r})")
    return dados


def _dirs(r):
    """Pastas de fila dentro da raiz, por ordem de nome."""
    if not r.is_dir():
        return []
    return sorted((d for d in r.iterdir() if d.is_dir() and (d / "fila.json").is_file()), key=lambda d: d.name)


def _ficheiros_sp(d):
    return sorted((p for p in d.glob("*.json") if p.name.lower() not in NAO_SP), key=lambda p: p.name)


NAO_SP = {"fila.json", "vigia.json"}  # a memória do vigia vive na pasta da fila e não é estado de SP


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


def _sp_novo(fid, slug, agora=None):
    return {"slug": slug, "fila": fid, "estado": "pendente", "modelo": None, "worktree": None, "pane": None,
            "inicio": None, "fim": None, "msg": None, "atualizado": _ts(agora)}


def _campos(campos):
    estranhos = sorted(set(campos) - set(CAMPOS))
    if estranhos:
        raise ErroEstado(f"campo desconhecido: {', '.join(estranhos)} (válidos: {', '.join(CAMPOS)})")
    return {k: (None if v is None else str(v)) for k, v in campos.items()}


def _procurar(r, slug):
    candidatas = []
    for d in _dirs(r):
        p = d / f"{slug}.json"
        if not p.is_file():
            continue
        try:
            acabado = _ler_sp(p)["estado"] in FINAIS
        except (ErroEstado, FileNotFoundError):
            acabado = False
        try:
            criada = str(_ler_json(d / "fila.json").get("criada") or "")
        except (ErroEstado, FileNotFoundError):
            criada = ""
        candidatas.append((not acabado, criada, d.name))
    if not candidatas:
        raise ErroEstado(f"slug desconhecido: {slug} (nenhuma fila o regista)")
    return max(candidatas)[2]


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
    """Converte o `~/.claude/sp-fila-estado.json` (estado único) numa fila; devolve o fila-id ou None se não há ficheiro.

    O ficheiro antigo fica onde está (a série `sp-handoff --launch` ainda o usa). Recusa com `ErroEstado`:
    JSON ilegível, formato desconhecido, nomes inválidos, fila já migrada ou sessões que rebentam o teto."""
    path = Path(path) if path else Path.home() / ".claude" / "sp-fila-estado.json"
    try:
        bruto = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as e:
        raise ErroEstado(f"estado antigo {ILEGIVEL}: {path} ({e})") from e
    try:
        antigo = json.loads(bruto)
    except ValueError as e:
        raise ErroEstado(f"estado antigo {ILEGIVEL}: {path} ({e}); corrigir ou apagar à mão") from e
    if not isinstance(antigo, dict) or not ({"sessoes", "lancado"} & set(antigo)):
        raise ErroEstado(f"estado antigo em formato desconhecido: {path} (sem `sessoes` nem `lancado`)")
    sessoes = antigo.get("sessoes") or {}
    if not isinstance(sessoes, dict):
        raise ErroEstado(f"estado antigo em formato desconhecido: {path} (`sessoes` não é um objeto)")
    sessoes = {s: (v if isinstance(v, dict) else {}) for s, v in sessoes.items()}
    listas = {}
    for campo in ("feitos", "falhados"):
        valor = antigo.get(campo) or []
        if not isinstance(valor, list) or not all(isinstance(s, str) for s in valor):
            raise ErroEstado(f"estado antigo em formato desconhecido: {path} (`{campo}` não é uma lista de slugs)")
        listas[campo] = valor
    lancado = antigo.get("lancado")
    if lancado:
        if not isinstance(lancado, str):
            raise ErroEstado(f"estado antigo em formato desconhecido: {path} (`lancado` não é um slug)")
        sessoes.setdefault(lancado, {})
    try:
        modo = "paralelo" if int(antigo.get("concorrencia") or 1) > 1 else "sequencial"
    except (TypeError, ValueError):
        raise ErroEstado(f"estado antigo em formato desconhecido: {path} (`concorrencia` não é um número)") from None
    feitos = [s for s in dict.fromkeys(listas["feitos"]) if s not in sessoes]
    falhados = [s for s in dict.fromkeys(listas["falhados"]) if s not in sessoes and s not in feitos]
    for s in [*sessoes, *feitos, *falhados]:
        _slug(s)
    try:
        criada = datetime.fromisoformat(str(antigo.get("inicio")))
    except ValueError:
        criada = agora or datetime.now()
    programa = antigo.get("programa") or None
    fid = fila_id(programa, criada)
    with _exclusivo(root) as r:
        d = r / fid
        if d.exists():
            raise ErroEstado(f"estado antigo já migrado: a fila {fid} existe")
        if sessoes and _ativos(r) + len(sessoes) > MAX_PARALELO:
            raise ErroEstado(f"migração recusada: {len(sessoes)} sessões em curso passam o teto de {MAX_PARALELO} painéis")
        d.mkdir()
        agora_ts = _ts(agora)
        for slug, estado in [*((s, "done") for s in feitos), *((s, "falhou") for s in falhados), *((s, "a-correr") for s in sessoes)]:
            sp = _sp_novo(fid, slug, agora)
            info = sessoes.get(slug, {})
            sp.update(estado=estado, msg="migrado de sp-fila-estado.json",
                      worktree=info.get("worktree"), pane=None if info.get("painel") is None else str(info["painel"]),
                      inicio=info.get("inicio") if estado == "a-correr" else None,
                      fim=agora_ts if estado in FINAIS else None)
            guardar(d / f"{slug}.json", sp)
        guardar(d / "fila.json", {"fila": fid, "programa": programa,
                                  "modo": modo,
                                  "limites": {k: antigo[k] for k in _LIMITES_ANTIGOS if antigo.get(k) is not None},
                                  "ordem": [*feitos, *falhados, *sessoes], "criada": criada.isoformat(timespec="seconds"),
                                  "migrada_de": str(path)})
    return fid
