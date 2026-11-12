"""Backends de painéis do modo paralelo (sp-fila `--concorrencia`, `sp-handoff --spawn`).

Interface única (`Backend`): `abrir(cmd, cwd) -> id`, `estado(id)`, `fechar(id)`; a fila e o handoff só falam com ela.
Três backends: `wezterm`, `tmux` (painéis interativos) e `background` (processo com log em ficheiro, sem terminal gráfico).
`escolher` decide por `painelBackend` do `kaizen.config.json` ou por deteção; sem backend utilizável devolve None e
`falta` explica o que falta (a fila cai para o modo sequencial).

Uso: módulo importado por sp_fila_*.py e sp-handoff.py; sem execução direta
rc: n/a
"""
import abc
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sp_disco import ler_json  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ESTADO_DIR = Path.home() / ".claude" / "sp-fila-paineis"
NOMES = ("wezterm", "tmux", "background")
SEM_COR = ("NO_COLOR", "FORCE_COLOR")  # variáveis que os painéis do --spawn não devem herdar
LOG_LINHAS = 80 # `ecra` do backend background: cauda do log


class BackendError(Exception):
    pass


_GRUPO = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
_FLAGS = {
    "janela": NO_WINDOW,                                              # sem consola
    "grupo": NO_WINDOW | _GRUPO,                                      # sem consola, grupo próprio (DETACHED faria cada filho abrir consola)
    "destacado": NO_WINDOW | _GRUPO | getattr(subprocess, "DETACHED_PROCESS", 0),  # sobrevive à sessão (vigia)
}


def run_hidden(*args, **kwargs):
    """Único sítio que corre `subprocess.run` sem abrir janela de consola no Windows."""
    kwargs.setdefault("creationflags", NO_WINDOW)
    return subprocess.run(*args, **kwargs)


def enviar_prompt(backend, pane, texto, run, sleep):
    """Único envio de um prompt a um painel: WezTerm/tmux esperam o prompt `❯` e enviam com Enter confirmado; os outros pela `enviar`."""
    if backend.nome in ("wezterm", "tmux"):
        import handoff_spawn  # tarde: só para painéis reais
        handoff_spawn._wait_prompt(backend.nome, pane, run, sleep)
        handoff_spawn._send_line(backend.nome, pane, texto, run, sleep)
    elif not backend.enviar(pane, texto):
        raise RuntimeError(f"painel {pane}: o envio do prompt falhou")


def popen_sem_janela(argv, modo="janela", run=None, **kwargs):
    """Único sítio que lança `Popen` sem janela; `modo`: `janela`, `grupo` ou `destacado`; `run` substitui o Popen (testes)."""
    return (run or subprocess.Popen)(argv, creationflags=_FLAGS[modo], **kwargs)


class Backend(abc.ABC):
    """Contrato: abrir um comando num painel, saber se continua vivo e fechá-lo.

    `interativo`: o painel mostra um terminal onde se pode escrever (wezterm, tmux); o background corre o comando direto.
    """
    nome = ""
    interativo = True

    @abc.abstractmethod
    def abrir(self, cmd, cwd):
        """Corre `cmd` (lista de argumentos) em `cwd` num painel novo e devolve o id (str)."""

    @abc.abstractmethod
    def listar(self):
        """{id: cwd ou None} dos painéis vivos."""

    @abc.abstractmethod
    def fechar(self, id):
        """Fecha o painel; True se existia, False se já não existia (nunca é erro)."""

    @abc.abstractmethod
    def ecra(self, id):
        """Texto visível do painel (ou a cauda do log); '' se não existe."""

    def enviar(self, id, texto):
        """Escreve `texto` e Enter no painel; True se enviou. Defeito: False (backend sem terminal onde escrever)."""
        return False

    def estado(self, id):
        """'vivo' ou 'morto'."""
        return "vivo" if str(id) in self.listar() else "morto"

    def titulo(self, id, texto):
        """Põe `texto` no título do separador do painel; True se pôs. Defeito: False (backend sem separadores)."""
        return False

    def titulos(self):
        """{id: título} dos painéis com título posto. Defeito: {}."""
        return {}


class _Multiplexer(Backend):
    def __init__(self, run=run_hidden):
        self.run = run

    def _out(self, argv):
        return self.run(argv, check=True, capture_output=True, text=True, encoding="utf-8").stdout


class WeztermBackend(_Multiplexer):
    nome = "wezterm"

    def abrir(self, cmd, cwd):
        # o painel herda o ambiente do cli: tirar o NO_COLOR/FORCE_COLOR das ferramentas do Claude Code, senão abre sem cor
        env = {k: v for k, v in os.environ.items() if k not in SEM_COR}
        pane = self.run(["wezterm", "cli", "spawn", "--cwd", str(cwd), "--", *cmd], check=True, capture_output=True,
                        text=True, encoding="utf-8", env=env).stdout.strip()
        origem = os.environ.get("WEZTERM_PANE")
        if origem:  # o spawn foca o painel novo; devolver o foco ao painel que lançou a fila
            self.run(["wezterm", "cli", "activate-pane", "--pane-id", origem], capture_output=True, text=True, encoding="utf-8")
        return pane

    def _lista(self):
        try:
            return json.loads(self.run(["wezterm", "cli", "list", "--format", "json"], capture_output=True, text=True, encoding="utf-8").stdout)
        except (OSError, ValueError, subprocess.SubprocessError):
            return []

    def listar(self):
        return {str(p["pane_id"]): p.get("cwd") for p in self._lista()}

    def titulo(self, id, texto):
        self.run(["wezterm", "cli", "set-tab-title", "--pane-id", str(id), texto], capture_output=True, text=True, encoding="utf-8")
        return True

    def titulos(self):
        return {str(p["pane_id"]): p["tab_title"] for p in self._lista() if p.get("tab_title")}

    def fechar(self, id):
        if str(id) not in self.listar():
            return False
        self.run(["wezterm", "cli", "kill-pane", "--pane-id", str(id)], capture_output=True, text=True)
        return True

    def ecra(self, id):
        return self.run(["wezterm", "cli", "get-text", "--pane-id", str(id)], capture_output=True, text=True, encoding="utf-8").stdout

    def enviar(self, id, texto):
        if str(id) not in self.listar():
            return False
        for parte in (texto, chr(13)):
            self.run(["wezterm", "cli", "send-text", "--pane-id", str(id), "--no-paste", "--", parte], capture_output=True, text=True, encoding="utf-8")
        return True


class TmuxBackend(_Multiplexer):
    nome = "tmux"

    def abrir(self, cmd, cwd):
        return self._out(["tmux", "split-window", "-d", "-P", "-F", "#{pane_id}", "-c", str(cwd), *cmd]).strip()

    def listar(self):
        try:
            saida = self.run(["tmux", "list-panes", "-a", "-F", "#{pane_id}\t#{pane_current_path}"], capture_output=True, text=True, encoding="utf-8").stdout
        except (OSError, subprocess.SubprocessError):
            return {}
        painéis = {}
        for linha in (saida or "").splitlines():
            id_, _, cwd = linha.partition("\t")
            if id_:
                painéis[id_] = cwd or None
        return painéis

    def fechar(self, id):
        if str(id) not in self.listar():
            return False
        self.run(["tmux", "kill-pane", "-t", str(id)], capture_output=True, text=True)
        return True

    def enviar(self, id, texto):
        if str(id) not in self.listar():
            return False
        self.run(["tmux", "send-keys", "-t", str(id), "-l", "--", texto], capture_output=True, text=True, encoding="utf-8")
        self.run(["tmux", "send-keys", "-t", str(id), "Enter"], capture_output=True, text=True, encoding="utf-8")
        return True

    def ecra(self, id):
        try:
            return self.run(["tmux", "capture-pane", "-p", "-t", str(id)], capture_output=True, text=True, encoding="utf-8").stdout
        except (OSError, subprocess.SubprocessError):
            return ""


def _arranque_sistema():
    """Instante (epoch) em que o sistema arrancou, ou None se não der para saber."""
    try:
        if os.name == "nt":
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.GetTickCount64.restype = ctypes.c_ulonglong
            return time.time() - k32.GetTickCount64() / 1000
        if sys.platform == "darwin":
            saida = run_hidden(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=5).stdout
            return float(saida.split("sec =")[1].split(",")[0])  # "{ sec = 1699999999, usec = 0 } ..."
        return time.time() - float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError, AttributeError, subprocess.SubprocessError):
        return None


def _pid_vivo(pid):
    """True se o processo `pid` existe e não terminou."""
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = ctypes.c_void_p
        handle = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            codigo = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(codigo))) and codigo.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class BackgroundBackend(Backend):
    """Processo destacado com saída em `<dir>/<pid>.log` e registo `<dir>/<pid>.json` {pid, cwd, log}; o id é o PID."""
    nome = "background"
    interativo = False

    def __init__(self, estado_dir=None, popen=subprocess.Popen):
        self.dir = Path(estado_dir or ESTADO_DIR)
        self.popen = popen
        self._filhos = {}

    def abrir(self, cmd, cwd):
        if not Path(cwd).is_dir():
            raise BackendError(f"cwd inexistente: {cwd}")
        self.dir.mkdir(parents=True, exist_ok=True)
        self._limpar()
        provisorio = self.dir / f"novo-{os.getpid()}-{time.time_ns()}.log"
        extra = {} if os.name == "nt" else {"start_new_session": True}
        erro = None
        with open(provisorio, "ab") as log:
            try:
                proc = popen_sem_janela([str(c) for c in cmd], "grupo", run=self.popen, cwd=str(cwd), stdin=subprocess.DEVNULL,
                                        stdout=log, stderr=subprocess.STDOUT, close_fds=True, **extra)
            except OSError as e:
                erro = e
        if erro is not None:  # fora do `with`: no Windows o ficheiro só se apaga depois de fechado
            provisorio.unlink(missing_ok=True)
            raise BackendError(f"não consegui lançar {cmd[0]!r}: {erro}") from erro
        id_ = str(proc.pid)
        log_final = self.dir / f"{id_}.log"
        try:
            os.replace(provisorio, log_final)  # no Windows o `with` já fechou o ficheiro; o filho mantém o seu handle
        except OSError:
            log_final = provisorio
        (self.dir / f"{id_}.json").write_text(json.dumps({"pid": proc.pid, "cwd": str(cwd), "log": str(log_final), "inicio": time.time()}), encoding="utf-8")
        self._filhos[id_] = proc
        return id_

    def _registo(self, id):
        try:
            return ler_json(self.dir / f"{int(id)}.json")
        except ValueError:  # id que não é inteiro
            return None

    def _limpar(self, dias=2):
        """Apaga registos e logs de processos mortos há mais de `dias` dias."""
        limite = time.time() - dias * 86400
        for f in self.dir.glob("*.json"):
            try:
                if f.stat().st_mtime < limite and not self._vivo(f.stem):
                    reg = self._registo(f.stem) or {}
                    Path(reg.get("log", f.with_suffix(".log"))).unlink(missing_ok=True)
                    f.unlink(missing_ok=True)
            except (OSError, ValueError):
                continue

    def _vivo(self, id):
        filho = self._filhos.get(str(id))
        if filho is not None:
            return filho.poll() is None  # também recolhe o zombie
        reg = self._registo(id)
        arranque = _arranque_sistema()
        if reg and arranque and reg.get("inicio", 0) < arranque:
            return False  # registo anterior ao arranque: o PID pode ser de outro processo
        return _pid_vivo(id)

    def listar(self):
        vivos = {}
        for f in self.dir.glob("*.json") if self.dir.is_dir() else []:
            reg = self._registo(f.stem)
            if reg and self._vivo(reg["pid"]):
                vivos[str(reg["pid"])] = reg.get("cwd")
        return vivos

    def estado(self, id):
        return "vivo" if self._registo(id) and self._vivo(id) else "morto"

    def fechar(self, id):
        if self.estado(id) != "vivo":
            return False
        pid = int(id)
        if os.name == "nt":
            run_hidden(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except OSError:
                os.kill(pid, signal.SIGTERM)
        filho = self._filhos.get(str(id))
        if filho is not None:
            try:
                filho.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        return True

    def ecra(self, id):
        reg = self._registo(id)
        if not reg:
            return ""
        try:
            texto = Path(reg["log"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(texto.splitlines()[-LOG_LINHAS:])


def _disponivel(nome, env, which, fixo=False):
    """True se o backend `nome` pode ser usado: o executável existe e, na deteção automática, o agente corre nele.

    Com `fixo` (nome pedido na config) basta o executável; o background não precisa de nenhum."""
    if nome == "background":
        return True
    variavel = {"wezterm": "WEZTERM_PANE", "tmux": "TMUX_PANE"}[nome]
    return which(nome) is not None and (fixo or bool(env.get(variavel)))


def por_nome(nome, run=run_hidden, estado_dir=None):
    """Instancia o backend `nome` (sem verificar o ambiente)."""
    if nome == "wezterm":
        return WeztermBackend(run)
    if nome == "tmux":
        return TmuxBackend(run)
    if nome == "background":
        return BackgroundBackend(estado_dir)
    raise BackendError(f"backend desconhecido: {nome!r} (válidos: {', '.join(NOMES)})")


def escolher(config="auto", env=None, which=shutil.which, run=run_hidden, estado_dir=None):
    """Backend a usar ou None.

    `config` vem de `painelBackend`: um nome fixo manda (None se estiver indisponível); `auto` deteta o multiplexer
    onde o agente corre (WezTerm, depois tmux). O background nunca é automático: tem de ser pedido na config.
    """
    env = os.environ if env is None else env
    if config in NOMES:
        return por_nome(config, run, estado_dir) if _disponivel(config, env, which, fixo=True) else None
    for nome in ("wezterm", "tmux"):
        if _disponivel(nome, env, which):
            return por_nome(nome, run, estado_dir)
    return None


def falta(config="auto", env=None, which=shutil.which):
    """Mensagem de uma linha: o que falta para haver backend (para o aviso do fallback sequencial)."""
    env = os.environ if env is None else env
    if config in ("wezterm", "tmux"):
        return f"painelBackend={config} mas o executável `{config}` não está no PATH"
    return ("sem backend de painéis: correr dentro do WezTerm ou de uma sessão tmux, ou pôr "
            '`"painelBackend": "background"` no kaizen.config.json (processos sem terminal gráfico)')
