"""Sp-fila: configuração, execução sem janela e estado partilhado (bloqueio, leitura e escrita atómica)."""
import json
import os
import subprocess
import time
from contextlib import contextmanager
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

_cfg = kaizen_engine.load("kaizen_config")
REPO = Path(__file__).resolve().parent.parent
USER = _cfg.user_name(REPO)
SCRIPTS = Path(__file__).resolve().parent
ESTADO = Path.home() / ".claude" / "sp-fila-estado.json"
RELATORIOS = REPO / "knowledge" / "infra" / "reports" / "sp-fila"
REQ_POR_SP = 50  # unidade de contagem do teto opt-in (--orcamento / orcamento_requests); por defeito sem limite
ORCAMENTO = None  # sem limite de requests
MAX_FALHAS_DEFEITO = 2  # falhas seguidas até parar a fila
MAX_DEFEITO = 5
LOCK_VELHO_S = 60  # um bloqueio mais antigo é de uma sessão morta


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_hidden(*args, **kwargs):
    """subprocess.run sem janela de consola no Windows: o vigia chama wezterm/git a cada ciclo e as janelas piscavam."""
    kwargs.setdefault("creationflags", NO_WINDOW)
    return subprocess.run(*args, **kwargs)


@contextmanager
def bloqueio(path, espera=15.0):
    """Exclusão mútua entre sessões sobre `path`: ficheiro `<path>.lock` criado com O_CREAT|O_EXCL."""
    lock = Path(f"{path}.lock")
    limite_t = time.monotonic() + espera
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except (FileExistsError, PermissionError):  # Windows: PermissionError se o dono está a apagar o .lock
            try:
                if time.time() - lock.stat().st_mtime > LOCK_VELHO_S:
                    lock.unlink(missing_ok=True)
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


def migrar(estado):
    """Formato antigo (`lancado`: um slug) → `sessoes`: {slug: {inicio, ...}} (uma entrada por SP em curso)."""
    antigo = estado.pop("lancado", None)
    estado.setdefault("sessoes", {})
    if antigo:
        estado["sessoes"].setdefault(antigo, {})
    return estado


def ler(path):
    return migrar(json.loads(Path(path).read_text(encoding="utf-8")))


def guardar(path, estado):
    """Escrita atómica: ficheiro temporário + os.replace (um leitor nunca vê JSON a meio)."""
    tmp = Path(f"{path}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    for tentativa in range(500):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: um leitor sem bloqueio (painel, estado-vivo) tem o destino aberto
            if tentativa == 499:
                raise
            time.sleep(0.02)


def atualizar(path, fn):
    """Ler-alterar-escrever o estado sob bloqueio; `fn(estado)` altera-o no sítio."""
    with bloqueio(path):
        estado = ler(path)
        fn(estado)
        guardar(path, estado)
        return estado


