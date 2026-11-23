"""Testes da reação do vigia a bloqueios recuperáveis (contexto, autorização coberta) e dos seus limites."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import sp_vigia  # noqa: E402
import sp_vigia_reacao as r  # noqa: E402
import test_sp_vigia as base  # noqa: E402

SP_TEXTO = """---
slug: x
restricoes: repo kaizen-flow so; AUTORIZADO: worktree e branch agent/<slug>, PR para main com CI verde; nunca matar paineis; nunca tag/publish
---
# SP

## Decisões
- Vigia sem LLM
"""


class Backend(base.Backend):
    def __init__(self, ecras=None, envio=True):
        super().__init__()
        self.ecras, self.enviados, self.envio = ecras or {}, [], envio

    def ecra(self, pane):
        return self.ecras.get(pane, "")

    def enviar(self, pane, texto):
        self.enviados.append((pane, texto))
        return self.envio


class Ctx(base.Ctx):
    def __init__(self, sps, texto=SP_TEXTO, handoff_ok=True, **kw):
        super().__init__(sps, backend=kw.pop("backend", None) or Backend(), **kw)
        self.texto, self.handoff_ok, self.reportes, self.handoffs = texto, handoff_ok, [], []

    def texto_sp(self, sp):
        return self.texto

    def registar_reacao(self, sp, linha):
        self.reportes.append((sp["slug"], linha))

    def retomar_contexto(self, sp):
        self.handoffs.append(sp["slug"])
        return self.handoff_ok


def _tick(ctx, mem=None, n=1):
    mem = mem if mem is not None else sp_vigia.memoria_nova()
    for _ in range(n):
        sp_vigia.passo(ctx, mem)
    return mem


def test_causa_por_regras():
    assert r.causa("contexto") == "contexto"
    assert r.causa("falta autorização para criar worktree no kaizen-flow") == "autorizacao"
    assert r.causa("restrição do SP impede isto") == "restricao"
    assert r.causa("precisa de git push --force") == "irreversivel"
    assert r.causa("gates vermelhos") is None


def test_coberta_so_com_clausula_explicita():
    assert r.coberta(SP_TEXTO, "criar worktree no kaizen-flow")
    assert r.coberta(SP_TEXTO, "criar worktree e abrir PR")
    assert r.coberta(SP_TEXTO, "fazer merge") is None  # não coberto
    assert r.coberta(SP_TEXTO, "nada reconhecível") is None
    assert r.coberta(SP_TEXTO.replace("worktree e branch", "branch"), "criar worktree") is None


def test_contexto_faz_handoff_no_mesmo_painel_e_volta_a_correr():
    ctx = Ctx({"a": {"estado": "bloqueado", "msg": "contexto"}})
    mem = _tick(ctx)
    assert ctx.handoffs == ["a"]
    assert ctx.sps["a"]["estado"] == "a-correr"
    assert "seguinte" not in base.nomes(ctx) and ctx.backend.fechados == []  # painel e vaga mantêm-se
    assert any("contexto → handoff" in l for _, l in ctx.reportes) and any("handoff" in l for l in ctx.logs)
    assert mem["reacoes"]["a"] == 1


def test_autorizacao_coberta_responde_e_volta_a_correr():
    ctx = Ctx({"a": {"estado": "bloqueado", "msg": "falta autorização para criar worktree no kaizen-flow"}})
    _tick(ctx)
    assert ctx.sps["a"]["estado"] == "a-correr"
    assert ctx.backend.enviados and ctx.backend.enviados[0][0] == "p-a" and "Autorizado pelo SP" in ctx.backend.enviados[0][1]
    assert ctx.reportes and "coberta pelo SP" in ctx.reportes[0][1]


def test_autorizacao_nao_coberta_so_avisa_uma_vez():
    ctx = Ctx({"a": {"estado": "bloqueado", "msg": "falta autorização para fazer merge"}})
    _tick(ctx, n=3)
    assert ctx.backend.enviados == [] and ctx.sps["a"]["estado"] == "bloqueado"
    assert sum(1 for l in ctx.logs if l.startswith("aviso bloqueado")) == 1


def test_pergunta_com_autorizacao_no_ecra_e_coberta():
    be = Backend(ecras={"p-a": "Preciso de autorização para criar a worktree\n❯ "})
    ctx = Ctx({"a": {"estado": "pergunta", "msg": "agente bloqueado (herdr)"}}, backend=be)
    _tick(ctx)
    assert ctx.sps["a"]["estado"] == "a-correr" and be.enviados



def test_irreversivel_nunca_e_respondido():
    for msg in ("precisa de git push --force; autorização para worktree", "autorização para npm publish", "ler o .env: autorização"):
        ctx = Ctx({"a": {"estado": "bloqueado", "msg": msg}})
        _tick(ctx, n=2)
        assert ctx.backend.enviados == [] and ctx.handoffs == [] and ctx.sps["a"]["estado"] == "bloqueado"


def test_terceira_ocorrencia_escala_ao_bms_sem_reagir():
    ctx = Ctx({"a": {"estado": "bloqueado", "msg": "contexto"}})
    mem = sp_vigia.memoria_nova()
    for _ in range(3):
        ctx.sps["a"].update(estado="bloqueado", msg="contexto")
        sp_vigia.passo(ctx, mem)
    assert ctx.handoffs == ["a", "a"]  # 2 reações, a 3.ª escala
    assert ctx.sps["a"]["estado"] == "bloqueado"
    assert sum("escalado ao BMS" in l for _, l in ctx.reportes) == 1
    sp_vigia.passo(ctx, mem)
    assert sum("escalado ao BMS" in l for _, l in ctx.reportes) == 1


def test_handoff_falhado_volta_a_bloqueado_e_conta():
    ctx = Ctx({"a": {"estado": "bloqueado", "msg": "contexto"}}, handoff_ok=False)
    mem = _tick(ctx)
    assert ctx.sps["a"]["estado"] == "bloqueado" and mem["reacoes"]["a"] == 1


def test_envio_falhado_volta_a_bloqueado():
    be = Backend(envio=False)
    ctx = Ctx({"a": {"estado": "bloqueado", "msg": "falta autorização para criar worktree"}}, backend=be)
    _tick(ctx)
    assert ctx.sps["a"]["estado"] == "bloqueado"


def test_pausa_quota_nao_passa_pela_reacao():
    ctx = Ctx({"a": {"estado": "bloqueado", "msg": "EC-016 quota", "motivo": "EC-016 quota"}})
    _tick(ctx)
    assert ctx.handoffs == [] and ctx.backend.enviados == []


def test_painel_morto_nao_reage():
    ctx = Ctx({"a": {"estado": "bloqueado", "msg": "contexto"}})
    ctx.backend.mortos.add("p-a")
    _tick(ctx)
    assert ctx.handoffs == []


def test_memoria_antiga_sem_reacoes_continua_a_funcionar(tmp_path):
    p = tmp_path / "vigia.json"
    p.write_text('{"avisos": {}, "tratados": []}', encoding="utf-8")
    assert "reacoes" not in sp_vigia.ler_memoria(p)
    ctx = Ctx({"a": {"estado": "bloqueado", "msg": "contexto"}})
    assert _tick(ctx, sp_vigia.ler_memoria(p))["reacoes"] == {"a": 1}
