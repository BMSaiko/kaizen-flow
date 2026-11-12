"""Disco partilhado do sp-fila: bloqueio entre processos, escrita atómica e leitura tolerante de JSON. Só stdlib.

Nasceu em `sp_painel_estado.py`; a lógica de `_recuperar` (lock de dono morto) mudou de sítio, não de forma.
`bloqueio(path)` cria `<path>.lock` (pid do dono, O_CREAT|O_EXCL) e a recuperação usa `<lock>.rec`.

Uso: módulo importado por sp_painel_estado, sp_fila_estado, sp_vigia, kf_errlog e painel_backend; sem execução direta
rc: n/a
"""
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

LOCK_VELHO_S = 60  # um bloqueio mais antigo, sem pid legível, é de uma sessão morta


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


def ler_json(path, defeito=None):
    """JSON de `path`; ficheiro em falta, ilegível ou inválido devolve `defeito` (leitura tolerante, nunca levanta)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defeito
