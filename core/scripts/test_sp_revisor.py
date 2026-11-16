"""sp-revisor.py: o review corre num painel `revisor` (modelo diferente do executor), só leitura, com semente e estado em ficheiro."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import sp_painel_estado as pe  # noqa: E402
from sp_carregar import carregar  # noqa: E402

sr = carregar(SCRIPTS / "sp-revisor.py", "sp_revisor", registar=False, fresco=True)

SP_TXT = """---
slug: proj-algo-2026-11-11
michi_modelo: default
---
# Super Prompt

## 1. Role
papel

## 3. Objective (single sentence)
Fazer X.

## 4. Success criteria (verifiable)
1. X funciona.

## 5. Constraints / invariants
- só lê.

## 6. Seams
- a.py
"""

MODELOS = {
    "papeis": {
        "revisor": {"model": "claude-fable-5-2", "effort": "low", "fallback": ["claude-opus-5-5"]},
        "michi-exec": {"model": "claude-sonnet-5-5", "effort": "medium"},
        "michi-critico": {"model": "claude-fable-5-2", "effort": "low"},
    },
    "michi_modelo": {"default": "michi-exec", "critico": "michi-critico"},
}


class FakeBackend:
    nome = "fake"
    interativo = True

    def __init__(self, enviar_ok=True):
        self.abertos, self.enviados, self.titulos_postos, self.fechados = [], [], {}, []
        self.enviar_ok = enviar_ok

    def abrir(self, cmd, cwd):
        self.abertos.append((cmd, cwd))
        return "p1"

    def enviar(self, pane, texto):
        self.enviados.append((pane, texto))
        return self.enviar_ok

    def titulo(self, pane, texto):
        self.titulos_postos[pane] = texto
        return True

    def titulos(self):
        return dict(self.titulos_postos)

    def fechar(self, pane):
        self.fechados.append(pane)
        return True


@pytest.fixture
def modelos_json(tmp_path, monkeypatch):
    p = tmp_path / "modelos.json"
    p.write_text(json.dumps(MODELOS), encoding="utf-8")
    monkeypatch.setattr(sr, "MODELOS", p)
    return p


@pytest.fixture
def sp(tmp_path):
    p = tmp_path / "proj-algo-2026-11-11.md"
    p.write_text(SP_TXT, encoding="utf-8")
    return p


def _git(tmp_path, args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd or tmp_path, capture_output=True, text=True, check=True)


def diff_stub(base, cwd):
    return " a.py | 2 +-\n 1 file changed"


# --- executor e comando ---------------------------------------------------


def test_executor_vem_do_michi_modelo_do_sp(sp, modelos_json):
    assert sr.executor(sp, sr.modelos.load(modelos_json)) == "claude-sonnet-5-5"


def test_executor_sem_michi_modelo_usa_default(tmp_path, modelos_json):
    p = tmp_path / "x.md"
    p.write_text("---\nslug: x\n---\n# SP\n", encoding="utf-8")
    assert sr.executor(p, sr.modelos.load(modelos_json)) == "claude-sonnet-5-5"


def test_comando_usa_o_modelo_do_revisor(tmp_path, modelos_json):
    cmd, aviso = sr.comando("claude-sonnet-5-5", tmp_path / "ach.md", modelos_json)
    assert cmd[:5] == ["claude", "--model", "claude-fable-5-2", "--effort", "low"]
    assert aviso is None


def test_comando_e_so_leitura_exceto_o_ficheiro_de_achados(tmp_path, modelos_json):
    ach = tmp_path / "ach.md"
    cmd, _ = sr.comando("claude-sonnet-5-5", ach, modelos_json)
    txt = " ".join(cmd)
    assert "--allowedTools" in cmd and "--disallowedTools" in cmd
    assert f"Edit({ach.resolve()})" in txt and "Write(" not in txt  # só Edit(path) casa com Write
    permitidas = cmd[cmd.index("--allowedTools") + 1 : cmd.index("--disallowedTools")]
    edicoes = [t for t in permitidas if t.startswith("Edit")]
    assert edicoes == [f"Edit({ach.resolve()})"]
    assert not any(t.startswith(("Bash(git commit", "Bash(git add")) or t == "Bash" for t in permitidas)


def test_comando_mesmo_modelo_do_executor_escolhe_o_seguinte_e_avisa(tmp_path, modelos_json):
    cmd, aviso = sr.comando("claude-fable-5-2", tmp_path / "ach.md", modelos_json)
    assert cmd[2] == "claude-opus-5-5"
    assert aviso and "claude-fable-5-2" in aviso and "claude-opus-5-5" in aviso


def test_comando_cadeia_esgotada_mantem_o_principal_e_avisa(tmp_path, monkeypatch):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"papeis": {"revisor": {"model": "claude-fable-5-2", "effort": "low"}}}), encoding="utf-8")
    cmd, aviso = sr.comando("claude-fable-5-2", tmp_path / "ach.md", p)
    assert cmd[2] == "claude-fable-5-2" and aviso and "não independente" in aviso


# --- semente ----------------------------------------------------------------


def test_semente_tem_seccoes_diff_checklist_e_formato(sp, tmp_path):
    t = sr.semente(sp, "master", tmp_path, diff=diff_stub, checklist_tipo="codigo")
    assert "Fazer X." in t and "X funciona." in t and "só lê." in t
    assert "## 1. Role" not in t and "## 6. Seams" not in t
    assert "a.py | 2 +-" in t
    assert "- [ ] testes cobrem" in t
    assert "[bloqueante|menor] ficheiro:linha descrição | verificar:" in t


def test_semente_re_review_so_leva_os_ficheiros_indicados(sp, tmp_path):
    t = sr.semente(sp, "master", tmp_path, diff=diff_stub, rever_so=["a.py", "b.py"])
    assert "Rever só: a.py, b.py" in t


def test_semente_pede_leitura_so_sem_corrigir(sp, tmp_path):
    t = sr.semente(sp, "master", tmp_path, diff=diff_stub).lower()
    assert "só lês" in t or "só lê" in t
    assert "nunca corrijas" in t or "não corrijas" in t


def test_prompt_numa_linha_com_consumo_achados_e_estado(sp, tmp_path):
    s, ach = tmp_path / "s.md", tmp_path / "ach.md"
    t = sr.prompt(sp, s, ach)
    assert "\n" not in t
    assert f'sp-autor.py --consume "{s}"' in t
    assert str(ach) in t
    assert "sp-estado.py revisor-proj-algo-2026-11-11 done" in t
    assert "Agent" not in t


# --- lançar -------------------------------------------------------------------


def test_lancar_abre_painel_revisor_e_regista(sp, tmp_path, modelos_json):
    b = FakeBackend()
    root = tmp_path / "estado"
    res = sr.lancar(sp, "master", tmp_path / "ach.md", b, cwd=tmp_path, estado_root=root, diff=diff_stub, sleep=lambda s: None)
    assert res["estado"] == "a-correr"
    cmd, cwd = b.abertos[0]
    assert cmd[2] == "claude-fable-5-2" and Path(cwd) == tmp_path
    assert b.titulos_postos["p1"] == "revisor proj-algo-2026-11-11"
    k = "revisor-proj-algo-2026-11-11"
    e = pe.ler(pe.procurar(k, root=root), k, root=root)
    assert e["estado"] == "a-correr" and e["modelo"] == "claude-fable-5-2"


def test_lancar_sem_vaga_fica_pendente_e_nao_abre(sp, tmp_path, modelos_json):
    root = tmp_path / "estado"
    f = pe.criar_fila("outra", root=root)
    for i in range(pe.MAX_PARALELO):
        pe.registar(f, f"s{i}", root=root)
        assert pe.reclamar_vaga(f"s{i}", fila=f, root=root)
    b = FakeBackend()
    res = sr.lancar(sp, "master", tmp_path / "ach.md", b, cwd=tmp_path, estado_root=root, diff=diff_stub, sleep=lambda s: None)
    assert res["estado"] == "pendente" and b.abertos == []


def test_lancar_apaga_achados_antigos_antes_de_abrir(sp, tmp_path, modelos_json):
    ach = tmp_path / "ach.md"
    ach.write_text("[bloqueante] velho:1 x | verificar: y\n", encoding="utf-8")
    sr.lancar(sp, "master", ach, FakeBackend(), cwd=tmp_path, estado_root=tmp_path / "e", diff=diff_stub, sleep=lambda s: None)
    assert not ach.exists()


# --- esperar ------------------------------------------------------------------


def _estado(tmp_path, estado):
    root = tmp_path / "estado"
    f = pe.criar_fila("revisor", root=root)
    pe.registar(f, "revisor-x", root=root)
    assert pe.reclamar_vaga("revisor-x", fila=f, root=root)
    if estado != "a-correr":
        pe.transitar("revisor-x", estado, fila=f, root=root)
    return root


def test_esperar_done_rc0(tmp_path):
    root = _estado(tmp_path, "done")
    assert sr.esperar("x", timeout=5, estado_root=root, sleep=lambda s: None) == 0


def test_esperar_bloqueado_rc1(tmp_path):
    root = _estado(tmp_path, "bloqueado")
    assert sr.esperar("x", timeout=5, estado_root=root, sleep=lambda s: None) == 1


def test_esperar_timeout_rc_proprio(tmp_path):
    root = _estado(tmp_path, "a-correr")
    relogio = iter(range(0, 1000, 10))
    rc = sr.esperar("x", timeout=30, estado_root=root, sleep=lambda s: None, agora=lambda: next(relogio))
    assert rc == sr.RC_TIMEOUT and rc not in (0, 1, 2)


# --- inline -------------------------------------------------------------------


def test_inline_imprime_semente_e_marca_review_nao_independente(sp, tmp_path, capsys, modelos_json):
    rc = sr.main(["--sp", str(sp), "--base", "master", "--achados", str(tmp_path / "a.md"), "--inline", "--cwd", str(tmp_path)],
                 diff=diff_stub)
    out = capsys.readouterr().out
    assert rc == 0 and "review não independente" in out and "Fazer X." in out


def test_simples_cai_em_inline(tmp_path, capsys, modelos_json):
    p = tmp_path / "s.md"
    p.write_text(SP_TXT.replace("michi_modelo: default", "michi_modelo: simples"), encoding="utf-8")
    assert sr.deve_inline(p) is True


def test_default_nao_e_inline(sp):
    assert sr.deve_inline(sp) is False


# --- CLI ----------------------------------------------------------------------


def test_cli_dry_run_mostra_o_plano(sp, tmp_path, modelos_json, capsys):
    rc = sr.main(["--sp", str(sp), "--base", "master", "--achados", str(tmp_path / "a.md"), "--dry-run",
                  "--modelos", str(modelos_json), "--cwd", str(tmp_path)], diff=diff_stub)
    out = capsys.readouterr().out
    assert rc == 0 and "revisor proj-algo-2026-11-11" in out and "claude-fable-5-2" in out


def test_cli_help_corre():
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "sp-revisor.py"), "--help"], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and "--achados" in r.stdout and "--esperar" in r.stdout and "--inline" in r.stdout


def test_cwd_externo_prompt_e_tools_usam_caminhos_absolutos_do_vault(sp, tmp_path, modelos_json, capsys):
    """Painel com --cwd num repo externo: `scripts/...` relativo não existe lá e `python` sem regra fica à espera."""
    externo = tmp_path / "repo-externo"
    externo.mkdir()
    ach = tmp_path / "a.md"
    rc = sr.main(["--sp", str(sp), "--base", "main", "--achados", str(ach), "--dry-run",
                  "--modelos", str(modelos_json), "--cwd", str(externo)], diff=diff_stub)
    out = capsys.readouterr().out
    autor, estado = (SCRIPTS / "sp-autor.py").as_posix(), (SCRIPTS / "sp-estado.py").as_posix()
    assert rc == 0
    assert f"python -I {autor} --consume" in out and f"python -I {estado} revisor-" in out
    assert "python -I scripts/" not in out
    cmd, _ = sr.comando("claude-sonnet-5-5", ach, modelos_json)
    permitidas = cmd[cmd.index("--allowedTools") + 1 : cmd.index("--disallowedTools")]
    pythons = [t for t in permitidas if t.startswith("Bash(python")]
    assert pythons == [f"Bash(python -I {autor}:*)", f"Bash(python -I {estado}:*)"]
    assert "Bash(python:*)" not in permitidas and "Bash(python -I:*)" not in permitidas


def test_py_poe_aspas_em_caminho_com_espacos(tmp_path):
    assert sr._py("sp-autor.py", "C:/Meu Vault/scripts") == 'python -I "C:/Meu Vault/scripts/sp-autor.py"'
    assert sr._py("sp-autor.py", "C:/vault/scripts") == "python -I C:/vault/scripts/sp-autor.py"


@pytest.mark.parametrize("anterior", ["done", "falhou", "bloqueado"])
def test_lancar_segunda_iteracao_reabre_depois_de_terminar(sp, tmp_path, modelos_json, anterior):
    """Re-review: o estado da iteração anterior não pode impedir o painel novo nem dar um `done` falso ao --esperar."""
    root = tmp_path / "estado"
    k = "revisor-proj-algo-2026-11-11"
    sr.lancar(sp, "master", tmp_path / "ach.md", FakeBackend(), cwd=tmp_path, estado_root=root, diff=diff_stub, sleep=lambda s: None)
    pe.transitar(k, anterior, msg="iteração 1", root=root)
    b = FakeBackend()
    res = sr.lancar(sp, "master", tmp_path / "ach.md", b, cwd=tmp_path, estado_root=root, diff=diff_stub, sleep=lambda s: None)
    assert res["estado"] == "a-correr" and len(b.abertos) == 1
    assert pe.ler(pe.procurar(k, root=root), k, root=root)["estado"] == "a-correr"
