"""Disco partilhado do sp-fila: bloqueio entre processos, escrita atómica e leitura tolerante de JSON. Só stdlib.

Nasceu em `sp_painel_estado.py`; a lógica de `_recuperar` (lock de dono morto) mudou de sítio, não de forma.
`bloqueio(path)` cria `<path>.lock` (pid do dono, O_CREAT|O_EXCL) e a recuperação usa `<lock>.rec`.

Uso: módulo importado por sp_painel_estado, sp_fila_estado, sp_vigia, kf_errlog e painel_backend; sem execução direta
rc: n/a
"""
import json
import os
import threading
import time
from contextlib import contextmanager, suppress
from pathlib import Path

LOCK_VELHO_S = 60  # um bloqueio mais antigo, sem pid legível, é de uma sessão morta
HEARTBEAT_S = 15  # intervalo do heartbeat do lock de SP
HEARTBEAT_VELHO_S = 90  # heartbeat mais antigo = dono preso ou pid reutilizado (órfão)
HEARTBEAT_SEM_PID_S = 1800  # lock sem pid (michi por CLI: cada fase renova) só expira após este silêncio
PID_MAX = 2**31 - 1  # maior pid aceite por `os.kill` (C int) e pelos pids reais de Linux/macOS/Windows


def pid_vivo(pid):
    """True se o processo `pid` existe. Windows: OpenProcess + GetExitCodeProcess (259 = ainda ativo); nunca `os.kill(pid, 0)`, que lá termina o processo."""
    if pid <= 0 or pid > PID_MAX:  # EC-041: pid fora do intervalo do SO (lock adulterado) não existe; `os.kill` daria OverflowError
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
        with suppress(OSError):  # falha: fica para a recuperação por idade
            guarda.unlink(missing_ok=True)


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


def guardar(path, estado, retry_s=None):
    """Escrita atómica: ficheiro temporário + os.replace (um leitor nunca vê JSON a meio).

    `retry_s=None` mantém o retry de 500 x 20 ms; um número limita o retry a esse total em segundos."""
    tmp = Path(f"{path}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    limite = None if retry_s is None else time.monotonic() + retry_s
    for tentativa in range(500):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: um leitor sem bloqueio (painel, vigia) tem o destino aberto
            if tentativa == 499 or (limite is not None and time.monotonic() >= limite):
                raise
            time.sleep(0.02)


def ler_json(path, defeito=None):
    """JSON de `path`; ficheiro em falta, ilegível ou inválido devolve `defeito` (leitura tolerante, nunca levanta)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defeito


# --- lock exclusivo por SP (retoma/órfãos): `<raiz>/.kaizen/estado/<slug>.lock.json` com pid, painel e heartbeat ---

class LockOcupado(Exception):
    """O SP já tem um dono vivo; `dono` é o dict de `dono()` (pid, painel, hb)."""

    def __init__(self, slug, dono):
        self.slug, self.dono = slug, dono
        super().__init__(f"SP {slug} em curso no painel {dono.get('painel') or '?'} (pid {dono.get('pid')})")


def caminho_lock_sp(raiz, slug):
    return Path(raiz) / ".kaizen" / "estado" / f"{slug}.lock.json"


def escrever_lock_sp(raiz, slug, dados):
    p = caminho_lock_sp(raiz, slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    guardar(p, dados, retry_s=2.0)


def dono(raiz, slug, agora=None):
    """Estado do lock do SP: `livre`, `vivo`, `orfao` (pid morto ou heartbeat antigo) ou `corrompido`; mais pid/painel/hb."""
    p = caminho_lock_sp(raiz, slug)
    if not p.exists():
        return {"estado": "livre"}
    d = ler_json(p)
    if not isinstance(d, dict) or not (d.get("pid") is None or isinstance(d.get("pid"), int)) or not isinstance(d.get("hb"), (int, float)):
        return {"estado": "corrompido"}
    agora = time.time() if agora is None else agora
    if d["pid"] is None:  # dono sem processo próprio: só o silêncio do heartbeat o dá por morto
        vivo = agora - d["hb"] <= HEARTBEAT_SEM_PID_S
    else:
        vivo = pid_vivo(d["pid"]) and agora - d["hb"] <= HEARTBEAT_VELHO_S
    return {"estado": "vivo" if vivo else "orfao", "pid": d["pid"], "painel": d.get("painel"), "hb": d["hb"], "ts": d.get("ts")}


class LockSp:
    """Lock de SP em posse deste processo; `heartbeat()` renova, `iniciar_heartbeat()` renova em thread."""

    def __init__(self, raiz, slug, painel, pid=None):
        self.raiz, self.slug, self.painel, self.pid, self.ts = raiz, slug, painel, pid, time.time()
        self._parar = threading.Event()
        self._thread = None

    def heartbeat(self, forcar=False):
        """Renova o lock; se já não for o dono (outro painel o tomou) não escreve e devolve False."""
        if not forcar:
            atual = ler_json(caminho_lock_sp(self.raiz, self.slug))
            if not (isinstance(atual, dict) and atual.get("pid") == self.pid and atual.get("ts") == self.ts):
                return False
        escrever_lock_sp(self.raiz, self.slug, {"pid": self.pid, "painel": self.painel, "ts": self.ts, "hb": time.time()})
        return True

    def iniciar_heartbeat(self, intervalo=HEARTBEAT_S):
        def corre():
            while not self._parar.wait(intervalo):
                with suppress(OSError):
                    self.heartbeat()
        self._thread = threading.Thread(target=corre, daemon=True)
        self._thread.start()

    def parar(self):
        self._parar.set()
        if self._thread:
            self._thread.join(2)


def _quarentena_lock(p):
    carimbo = time.strftime("%Y%m%dT%H%M%S") + f"{time.time_ns() % 10**9:09d}"
    destino = p.with_name(f"{p.name}.corrupt-{carimbo}")
    os.replace(p, destino)
    return destino


def tomar_lock(raiz, slug, painel=None, pid="eu"):
    """Toma o lock do SP ou levanta `LockOcupado` (dono vivo). Órfão é tomado; ilegível vai para `.corrupt-*` (nunca apagado).

    `pid="eu"` = este processo; `None` = dono sem processo próprio (michi por CLI).
    A tomada corre sob `bloqueio` para duas tentativas não se pisarem; o lock em si é lido sem bloqueio (escrita atómica)."""
    p = caminho_lock_sp(raiz, slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    painel = (painel or os.environ.get("HERDR_PANE_ID") or os.environ.get("WEZTERM_PANE") or os.environ.get("TMUX_PANE")
              or f"pid{os.getpid()}")
    with bloqueio(p):
        d = dono(raiz, slug)
        if d["estado"] == "vivo":
            raise LockOcupado(slug, d)
        if d["estado"] == "corrompido":
            _quarentena_lock(p)
        lk = LockSp(raiz, slug, painel, os.getpid() if pid == "eu" else pid)
        lk.heartbeat(forcar=True)
    return lk


def libertar_lock(raiz, slug, pid="eu", painel=None):
    """Apaga o lock se for do `pid` (este processo por defeito; `None` = sem processo); True se apagou.

    Com `painel`, só apaga se o lock for desse painel. Lock sem chave `pid` (ilegível) vai para `.corrupt-*`, nunca é apagado."""
    p = caminho_lock_sp(raiz, slug)
    dono_pid = os.getpid() if pid == "eu" else pid
    if not p.exists():
        return False
    with bloqueio(p):
        atual = ler_json(p)
        if atual is None and not p.exists():
            return False
        if not isinstance(atual, dict) or "pid" not in atual:
            _quarentena_lock(p)
            return False
        if atual.get("pid") == dono_pid and (painel is None or atual.get("painel") == painel):
            p.unlink(missing_ok=True)
            return True
    return False


def renovar_lock(raiz, slug):
    """Renova o heartbeat de um lock vivo sem recriar nem ressuscitar órfãos; chamado a cada evento do journal.

    Só renova se o dono for «vivo» e o pid for do processo atual ou o lock for sem processo (michi por CLI)."""
    p = caminho_lock_sp(raiz, slug)
    if not p.exists():
        return False
    with bloqueio(p):
        if dono(raiz, slug)["estado"] != "vivo":
            return False
        d = ler_json(p)
        if not isinstance(d, dict) or d.get("pid") not in (None, os.getpid()):
            return False
        d["hb"] = time.time()
        escrever_lock_sp(raiz, slug, d)
    return True


@contextmanager
def lock_sp(raiz, slug, painel=None, heartbeat=False):
    """`tomar_lock` como contexto: liberta à saída; `heartbeat=True` renova numa thread."""
    lk = tomar_lock(raiz, slug, painel)
    if heartbeat:
        lk.iniciar_heartbeat()
    try:
        yield lk
    finally:
        lk.parar()
        libertar_lock(raiz, slug)
