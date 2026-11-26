"""Fake determinístico da CLI `herdr` para testes: `FakeHerdr()` serve de `run` (mesma assinatura que subprocess.run).

Guarda workspaces/tabs/panes/agentes em memória, regista `chamadas` e responde no formato do herdr 0.9.5.
`pane run` com `command claude` cria um agente (estado inicial `agente_estado`, defeito idle); `agent prompt` passa-o a idle
com `completion_seq`+1, ou levanta `agent_blocked` se estiver blocked.

Uso: importado pelos testes (test_herdr_ops.py)
rc: n/a
"""
import json
from types import SimpleNamespace


class FakeHerdr:
    def __init__(self, agente_estado="idle"):
        self.chamadas = []
        self.workspaces = {}  # id -> label
        self.panes = {}  # pane_id -> {workspace_id, tab_id, cwd, label}
        self.agentes = {}  # pane_id -> agent dict
        self.agente_estado = agente_estado
        self._ws = self._tab = self._pane = 0

    def __call__(self, argv, **kw):
        self.chamadas.append(list(argv))
        a = argv[1:]
        try:
            res = self._tratar(a)
            corpo = {"id": "cli:fake", "result": res}
        except KeyError as e:
            corpo = {"id": "cli:fake", "error": {"code": str(e.args[0]), "message": "fake"}}
        rc = 1 if "error" in corpo else 0
        return SimpleNamespace(returncode=rc, stdout=json.dumps(corpo), stderr="")

    def _novo_pane(self, ws, tab, cwd):
        self._pane += 1
        pid = f"{ws}:p{self._pane}"
        self.panes[pid] = {"pane_id": pid, "workspace_id": ws, "tab_id": tab, "cwd": cwd}
        return pid

    def _tratar(self, a):
        g, c = a[0], a[1] if len(a) > 1 else ""
        flag = lambda n: a[a.index(n) + 1] if n in a else None  # noqa: E731
        if (g, c) == ("workspace", "list"):
            return {"workspaces": [{"workspace_id": i, "label": l} for i, l in self.workspaces.items()]}
        if (g, c) == ("workspace", "create"):
            self._ws += 1
            ws, tab = f"w{self._ws}", f"w{self._ws}:t1"
            self.workspaces[ws] = flag("--label")
            return {"workspace": {"workspace_id": ws}, "root_pane": {"pane_id": self._novo_pane(ws, tab, flag("--cwd"))}}
        if (g, c) == ("tab", "create"):
            ws = flag("--workspace") or next(iter(self.workspaces), "w1")
            self._tab += 1
            return {"root_pane": {"pane_id": self._novo_pane(ws, f"{ws}:t{100 + self._tab}", flag("--cwd"))}}
        if (g, c) == ("pane", "split"):
            o = self.panes[a[2]]
            return {"pane": {"pane_id": self._novo_pane(o["workspace_id"], o["tab_id"], flag("--cwd"))}}
        if (g, c) == ("pane", "list"):
            return {"panes": list(self.panes.values())}
        if (g, c) == ("pane", "run"):
            if "command claude" in a[3]:
                self.agentes[a[2]] = {"pane_id": a[2], "agent": "claude", "agent_status": self.agente_estado, "completion_seq": 0}
            return {"type": "ok"}
        if (g, c) in (("pane", "rename"), ("pane", "report-metadata"), ("workspace", "report-metadata"), ("tab", "focus")):
            return {"type": "ok"}
        if (g, c) == ("pane", "close"):
            self.panes.pop(a[2], None)
            self.agentes.pop(a[2], None)
            return {"type": "ok"}
        if (g, c) == ("pane", "read"):
            return {"type": "ok"}
        if (g, c) == ("agent", "list"):
            return {"agents": list(self.agentes.values())}
        if (g, c) == ("agent", "rename"):
            self.agentes[a[2]]["name"] = a[3]
            return {"type": "ok"}
        if (g, c) in (("agent", "prompt"), ("agent", "wait")):
            ag = self.agentes.get(a[2])
            if ag is None:
                raise KeyError("agent_not_found")
            if c == "prompt":
                if ag["agent_status"] == "blocked":
                    raise KeyError("agent_blocked")
                ag["agent_status"] = "idle"
                ag["completion_seq"] += 1
            return {"agent": dict(ag)}
        raise KeyError("comando_desconhecido")
