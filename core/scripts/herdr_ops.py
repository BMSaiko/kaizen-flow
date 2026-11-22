"""Único sítio que fala com a CLI `herdr` (0.9.5): abrir painéis, lançar agente, enviar prompt, ler estado, esperar, renomear, fechar, metadata.

Contrato fixado no spike F1 (`docs/herdr-agent-spike.md`): respostas `{"id","result"}` ou `{"id","error":{"code","message"}}`.
`HerdrBackend` (painel_backend) delega aqui; os testes usam `herdr_fake.FakeHerdr` no lugar de `run`.
O claude lança-se por `pane run "cd <cwd> && command claude ..."` (e não `agent start`, que ignora o cwd com a função `claude()` do bashrc).

Uso: módulo importado por painel_backend.py; sem execução direta
rc: n/a
"""
import json
import os
import shlex
import subprocess
import time
from pathlib import Path

ESTADOS = ("idle", "working", "blocked", "done", "unknown")


class HerdrErro(Exception):
    """Erro devolvido pelo herdr (`code` do JSON) ou resposta vazia."""

    def __init__(self, code, mensagem=""):
        super().__init__(f"{code}: {mensagem}" if mensagem else code)
        self.code = code


def _run_defeito(*args, **kwargs):
    return subprocess.run(*args, **kwargs)


class HerdrOps:
    def __init__(self, run=_run_defeito, sleep=time.sleep):
        self.run = run
        self.sleep = sleep

    # --- base ---------------------------------------------------------------------------------------------
    def _exec(self, argv):
        return self.run(["herdr", *argv], capture_output=True, text=True, encoding="utf-8")

    def json(self, argv):
        """`result` do JSON do herdr ({} se o servidor não responde ou devolve erro)."""
        try:
            d = json.loads(self._exec(argv).stdout or "{}")
        except (OSError, ValueError, subprocess.SubprocessError):
            return {}
        return d.get("result") or {}

    def json_estrito(self, argv):
        """Como `json`, mas levanta HerdrErro com o `code` do herdr (agent_blocked, agent_not_found, timeout...)."""
        try:
            r = self._exec(argv)
        except (OSError, subprocess.SubprocessError) as e:
            raise HerdrErro("sem_herdr", str(e)) from e
        for texto in (r.stdout, getattr(r, "stderr", "")):
            try:
                d = json.loads(texto or "")
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("error"):
                raise HerdrErro(d["error"].get("code", "erro"), d["error"].get("message", ""))
            if isinstance(d, dict) and "result" in d:
                return d["result"] or {}
        raise HerdrErro("resposta_vazia", (getattr(r, "stderr", "") or "").strip())

    def out(self, argv):
        r = self._exec(argv)
        if getattr(r, "returncode", 0) != 0:
            raise OSError(f"herdr {' '.join(argv[:2])} rc={r.returncode}: {(getattr(r, 'stderr', '') or '').strip()}")
        return r.stdout

    # --- painéis, workspaces e tabs ---------------------------------------------------------------------
    def paineis(self):
        return self.json(["pane", "list"]).get("panes") or []

    def panes_da_tab(self, origem):
        """(nº de panes na tab do pane `origem`, workspace) ou (None, None) se a origem não aparece em `pane list`."""
        paineis = self.paineis()
        o = next((p for p in paineis if p.get("pane_id") == origem), None)
        if not o or not o.get("tab_id"):
            return None, None
        return sum(1 for p in paineis if p.get("tab_id") == o["tab_id"]), o.get("workspace_id")

    @staticmethod
    def repo_do_projeto(projeto):
        """Repo de código do `projeto`: `<SB_CODE_ROOT, defeito ~/Documents/code>/<projeto>` se for um diretório; senão None."""
        if not projeto or "/" in projeto or projeto.startswith("."):
            return None
        raiz = Path(os.environ.get("SB_CODE_ROOT", "").strip() or "~/Documents/code").expanduser() / projeto
        return str(raiz) if raiz.is_dir() else None

    @staticmethod
    def raiz_repo(cwd):
        """Raiz do repo principal de `cwd` (uma worktree resolve para o checkout principal); None fora de um repo."""
        try:
            r = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                               capture_output=True, text=True, encoding="utf-8", timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        comum = (r.stdout or "").strip()
        if r.returncode != 0 or not comum:
            return None
        return os.path.dirname(comum.rstrip("/")) if os.path.basename(comum.rstrip("/")) == ".git" else comum

    def workspace_para(self, cwd, projeto=None):
        """(workspace_id, root_pane ou None) do projeto: reutiliza o workspace com label = nome do repo ou cria-o."""
        raiz = self.repo_do_projeto(projeto) or self.raiz_repo(cwd) or str(cwd)
        nome = os.path.basename(raiz.rstrip("/")) or raiz
        ws = next((w.get("workspace_id") for w in self.json(["workspace", "list"]).get("workspaces") or []
                   if w.get("label") == nome and w.get("workspace_id")), None)
        if ws:
            return ws, None
        res = self.json(["workspace", "create", "--cwd", raiz, "--label", nome, "--no-focus"])
        return (res.get("workspace") or {}).get("workspace_id"), (res.get("root_pane") or {}).get("pane_id")

    def painel_novo(self, cwd, projeto=None, max_panes=2, workspace_por_projeto=True, origem=None):
        """Id de um painel novo (workspace do projeto, split ou tab); None se o herdr não devolveu id. Não corre comando."""
        n, ws_origem = self.panes_da_tab(origem) if origem else (None, None)
        ws, pane = self.workspace_para(cwd, projeto) if workspace_por_projeto else (None, None)
        if pane:
            return pane
        if n is not None and n < max_panes and (ws is None or ws == ws_origem):
            res = self.json(["pane", "split", origem, "--direction", "right", "--cwd", str(cwd), "--no-focus"])
            return (res.get("pane") or {}).get("pane_id")
        ws = ws or ws_origem
        res = self.json(["tab", "create", *(["--workspace", ws] if ws else []), "--cwd", str(cwd), "--no-focus"])
        return (res.get("root_pane") or {}).get("pane_id")

    def correr(self, pane, cmd):
        """`exec <cmd>` no painel (fecha quando o comando acaba, como no tmux split-window)."""
        self.out(["pane", "run", pane, "exec " + shlex.join(str(c) for c in cmd)])

    def lancar_agente(self, pane, cwd, cmd=("claude",)):
        """Lança o agente no painel com cwd certo: `cd <cwd> && command claude ...` (contorna a função claude() do bashrc)."""
        self.out(["pane", "run", pane, f"cd {shlex.quote(str(cwd))} && command {shlex.join(str(c) for c in cmd)}"])

    def renomear(self, pane, texto):
        self._exec(["pane", "rename", str(pane), texto])

    def renomear_agente(self, pane, nome):
        self._exec(["agent", "rename", str(pane), nome])

    def metadata(self, pane, fonte, titulo):
        """Metadata só de apresentação (título); sem efeito no estado."""
        self._exec(["pane", "report-metadata", "--source", fonte, "--title", titulo, str(pane)])

    def workspace_do_pane(self, pane):
        """workspace_id do painel (None se não aparece em `pane list`)."""
        return next((p.get("workspace_id") for p in self.paineis() if p.get("pane_id") == str(pane)), None)

    def workspace_metadata(self, workspace, fonte, texto):
        """Metadata do workspace (`workspace report-metadata`, token `fila`): só apresentação, nunca estado."""
        self._exec(["workspace", "report-metadata", "--source", fonte, "--token", f"fila={texto}", str(workspace)])

    def foco_tab(self, tab):
        self._exec(["tab", "focus", tab])

    def fechar(self, pane):
        self._exec(["pane", "close", str(pane)])

    def ecra(self, pane):
        try:
            return self._exec(["pane", "read", str(pane), "--source", "visible"]).stdout
        except (OSError, subprocess.SubprocessError):
            return ""

    # --- agente ---------------------------------------------------------------------------------------------
    def agentes(self):
        """{pane_id: agent} do `agent list` ({} se o herdr não responde)."""
        return {a["pane_id"]: a for a in self.json(["agent", "list"]).get("agents") or [] if a.get("pane_id")}

    def estado(self, pane):
        """`agent_status` do agente no painel (idle/working/blocked/done/unknown); 'unknown' se não detetado."""
        a = self.agentes().get(str(pane))
        return (a or {}).get("agent_status") or "unknown"

    def esperar(self, alvo, ate=None, timeout_ms=None):
        """`agent wait`: devolve o agent no estado pedido (defeito idle/done/blocked); HerdrErro(timeout...) se não."""
        argv = ["agent", "wait", str(alvo)]
        for s in ate or ():
            argv += ["--until", s]
        if timeout_ms:
            argv += ["--timeout", str(timeout_ms)]
        return self.json_estrito(argv).get("agent") or {}

    def prompt(self, alvo, texto, esperar=False, ate=None, timeout_ms=None):
        """`agent prompt`: envia o texto; com `esperar` bloqueia até ao estado (HerdrErro agent_blocked/agent_prompt_stalled/timeout)."""
        argv = ["agent", "prompt", str(alvo), texto]
        if esperar:
            argv.append("--wait")
        for s in ate or ():
            argv += ["--until", s]
        if timeout_ms:
            argv += ["--timeout", str(timeout_ms)]
        return self.json_estrito(argv).get("agent") or {}
