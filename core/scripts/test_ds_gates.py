"""Testes de ds-lint.py e ds-verify.py (gates de design para SPs `ui: sim`).

Uso: python -m pytest scripts/test_ds_gates.py -q
rc: o do pytest
"""
import json
import struct
import zlib
from pathlib import Path

import pytest
from sp_carregar import carregar

AQUI = Path(__file__).resolve().parent
ds_lint = carregar(AQUI / "ds-lint.py")
ds_verify = carregar(AQUI / "ds-verify.py")
sp_gates = carregar(AQUI / "sp-gates.py", "sp_gates", fresco=True)


def _png(w, h, cor):
    """PNG RGB 8-bit sem interlace, cor única (stdlib)."""
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d))
    raw = b"".join(b"\x00" + bytes(cor) * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


# --- ds-lint -----------------------------------------------------------------

def _proj(tmp_path, css):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.css").write_text(css, encoding="utf-8")
    return tmp_path


def test_lint_literal_de_cor_rc1_com_ficheiro_linha(tmp_path, capsys):
    p = _proj(tmp_path, ".a {\n  color: #ff0000;\n}\n")
    assert ds_lint.main(["--dir", str(p)]) == 1
    assert "src/app.css:2" in capsys.readouterr().out.replace("\\", "/")


def test_lint_token_aceite_rc0(tmp_path):
    p = _proj(tmp_path, ".a { color: var(--color-primary); padding: var(--space-4); margin: 0; }\n")
    assert ds_lint.main(["--dir", str(p)]) == 0


@pytest.mark.parametrize("linha", [
    "background: rgb(1, 2, 3);",
    "background: hsl(10 20% 30%);",
    "padding: 13px;",
    "gap: 1.5rem;",
    "font-size: 17px;",
    "font-family: Arial, sans-serif;",
])
def test_lint_deteta_literais(tmp_path, linha):
    p = _proj(tmp_path, f".a {{ {linha} }}\n")
    assert ds_lint.main(["--dir", str(p)]) == 1


def test_lint_tsx_e_html_inline(tmp_path):
    (tmp_path / "a.tsx").write_text('const x = <div style={{ color: "#abc" }} />;\n', encoding="utf-8")
    (tmp_path / "b.html").write_text('<p style="margin: 8px">x</p>\n', encoding="utf-8")
    achados = ds_lint.lint(tmp_path)
    assert {a[0] for a in achados} == {"a.tsx", "b.html"}


def test_lint_ignora_tokens_node_modules_e_marca_ignore(tmp_path):
    (tmp_path / "design").mkdir()
    (tmp_path / "design" / "tokens.css").write_text(":root { --c: #fff; }\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.css").write_text("a { color: #fff }\n", encoding="utf-8")
    (tmp_path / "ok.css").write_text("a { color: #fff } /* ds-lint-ignore */\n", encoding="utf-8")
    assert ds_lint.main(["--dir", str(tmp_path)]) == 0


def test_lint_corrigido_para_token_passa(tmp_path):
    p = _proj(tmp_path, ".a { color: #ff0000; }\n")
    assert ds_lint.main(["--dir", str(p)]) == 1
    (p / "src" / "app.css").write_text(".a { color: var(--color-danger); }\n", encoding="utf-8")
    assert ds_lint.main(["--dir", str(p)]) == 0


# --- ds-verify ---------------------------------------------------------------

CFG = {"design": {"startCmd": "npm run dev", "url": "http://localhost:5173", "rotas": ["/", "/sobre"]}}


def _repo(tmp_path, cfg=CFG):
    (tmp_path / "kaizen.config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return tmp_path


def _fake(shots=None, violacoes=(), sem_browser=False):
    def runner(cfg, repo, destino, breakpoints):
        if sem_browser:
            return {"semBrowser": True}
        out = []
        for rota in cfg["rotas"]:
            for nome in breakpoints:
                f = Path(destino) / f"{ds_verify.slug(rota)}-{nome}.png"
                f.write_bytes((shots or {}).get((rota, nome), _png(4, 4, (255, 255, 255))))
                out.append({"rota": rota, "bp": nome, "ficheiro": str(f)})
        return {"violacoes": list(violacoes), "screenshots": out}
    return runner


def test_verify_sem_baseline_falha_e_atualizar_cria(tmp_path, capsys):
    r = _repo(tmp_path)
    assert ds_verify.main(["--dir", str(r)], runner=_fake()) == 1
    assert "sem baseline" in capsys.readouterr().out
    assert ds_verify.main(["--dir", str(r), "--atualizar-baselines"], runner=_fake()) == 0
    assert len(list((r / "design" / "baselines").glob("*.png"))) == 6  # 2 rotas x 3 breakpoints
    assert ds_verify.main(["--dir", str(r)], runner=_fake()) == 0


def test_verify_diff_acima_do_limiar_rc1(tmp_path, capsys):
    r = _repo(tmp_path)
    ds_verify.main(["--dir", str(r), "--atualizar-baselines"], runner=_fake())
    mudado = {("/", "md"): _png(4, 4, (0, 0, 0))}
    assert ds_verify.main(["--dir", str(r)], runner=_fake(shots=mudado)) == 1
    assert "diff" in capsys.readouterr().out


def test_verify_violacao_serias_e_criticas_rc1_menores_nao(tmp_path):
    r = _repo(tmp_path)
    ds_verify.main(["--dir", str(r), "--atualizar-baselines"], runner=_fake())
    grave = [{"rota": "/", "id": "color-contrast", "impact": "serious", "nodes": 2}]
    leve = [{"rota": "/", "id": "region", "impact": "minor", "nodes": 1}]
    assert ds_verify.main(["--dir", str(r)], runner=_fake(violacoes=grave)) == 1
    assert ds_verify.main(["--dir", str(r)], runner=_fake(violacoes=leve)) == 0


def test_verify_sem_browser_rc3_nunca_verde(tmp_path, capsys):
    r = _repo(tmp_path)
    assert ds_verify.main(["--dir", str(r)], runner=_fake(sem_browser=True)) == 3
    assert "aviso" in capsys.readouterr().err


def test_verify_sem_config_rc2(tmp_path):
    assert ds_verify.main(["--dir", str(tmp_path)], runner=_fake()) == 2


def test_verify_regista_relatorio_e_baseline_no_sp(tmp_path):
    r = _repo(tmp_path)
    sp = tmp_path / "sp.md"
    sp.write_text("# sp\n", encoding="utf-8")
    ds_verify.main(["--dir", str(r), "--atualizar-baselines", "--sp", str(sp)], runner=_fake())
    assert "baselines atualizadas" in sp.read_text(encoding="utf-8")
    rel = json.loads((r / "design" / "relatorio.json").read_text(encoding="utf-8"))
    assert rel["ok"] is True and len(rel["screenshots"]) == 6


def test_png_diff_tamanhos_diferentes_e_rgba():
    a, b = _png(2, 2, (1, 2, 3)), _png(3, 2, (1, 2, 3))
    assert ds_verify.diff_png(a, a) == 0.0
    assert ds_verify.diff_png(a, b) == 1.0


# --- perfil: só com ui: sim ----------------------------------------------------

def test_perfil_ui_injeta_gates_de_design_so_com_ui_sim(tmp_path):
    base = [{"cmd": "npm test", "cwd": ".", "timeout": 300, "inputs": []}]
    perfil = {"bloqueantes": [], "consultivos": [], "fases": []}
    sem = sp_gates.juntar_perfil(base, perfil, tmp_path, ui=False)
    com = sp_gates.juntar_perfil(base, perfil, tmp_path, ui=True)
    assert [g["cmd"] for g in sem] == ["npm test"]
    cmds = [g["cmd"] for g in com]
    assert any("ds-lint" in c for c in cmds) and any("ds-verify" in c for c in cmds)
    assert next(g for g in com if "ds-lint" in g["cmd"])["modo"] == "bloqueante"


def test_ui_sp_le_frontmatter():
    assert sp_gates.sp_ui("---\nui: sim\n---\n# x") is True
    assert sp_gates.sp_ui("---\nstatus: Doing\n---\n# x\nui: sim") is False
