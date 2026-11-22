"""sp-autor.py: o SP é preenchido num painel `sp-autor` (modelo do papel), com semente efémera e estado em ficheiro."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import sp_painel_estado as pe  # noqa: E402
from sp_carregar import carregar  # noqa: E402

sa = carregar(SCRIPTS / "sp-autor.py", "sp_autor", registar=False, fresco=True)


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
    p.write_text(json.dumps({"papeis": {"sp-autor": {"model": "claude-teste-1", "effort": "low"}}}), encoding="utf-8")
    monkeypatch.setattr(sa, "MODELOS", p)
    return p


@pytest.fixture
def sp_vazio(tmp_path):
    p = tmp_path / "proj-algo-2026-11-11.md"
    p.write_text("---\nslug: proj-algo-2026-11-11\n---\n# Super Prompt\n", encoding="utf-8")
    return p


def _semente(tmp_path, texto="decisões do grill"):
    s = tmp_path / "semente.md"
    s.write_text(texto, encoding="utf-8")
    return s


def test_comando_usa_o_modelo_do_papel(modelos_json):
    assert sa.comando() == ["claude", "--model", "claude-teste-1", "--effort", "low"]


def test_titulo_e_chave():
    assert sa.titulo("x-2026") == "sp-autor x-2026"
    assert sa.chave("x-2026") == "sp-autor-x-2026"


def test_prompt_numa_linha_com_consumo_e_estado(sp_vazio, tmp_path):
    s = _semente(tmp_path)
    t = sa.prompt(sp_vazio, s)
    assert "\n" not in t
    assert f'sp-autor.py --consume "{s}"' in t
    assert "sp-estado.py sp-autor-proj-algo-2026-11-11 done" in t
    assert str(sp_vazio) in t
    assert "Agent" not in t


def test_lancar_abre_painel_titulo_envia_e_regista(modelos_json, sp_vazio, tmp_path):
    b = FakeBackend()
    root = tmp_path / "estado"
    res = sa.lancar(sp_vazio, _semente(tmp_path), b, cwd=tmp_path, estado_root=root, sleep=lambda s: None)
    assert res["estado"] == "a-correr"
    cmd, cwd = b.abertos[0]
    assert cmd[:3] == ["claude", "--model", "claude-teste-1"] and Path(cwd) == tmp_path
    assert b.titulos_postos["p1"] == "sp-autor proj-algo-2026-11-11"
    assert "sp-autor.py --consume" in b.enviados[0][1]
    k = "sp-autor-proj-algo-2026-11-11"
    sp = pe.ler(pe.procurar(k, root=root), k, root=root)
    assert sp["estado"] == "a-correr" and sp["pane"] == "p1" and sp["modelo"] == "claude-teste-1"


def test_lancar_conta_para_o_teto_global(modelos_json, sp_vazio, tmp_path):
    root = tmp_path / "estado"
    f = pe.criar_fila("outra", root=root)
    for i in range(pe.MAX_PARALELO):
        pe.registar(f, f"s{i}", root=root)
        assert pe.reclamar_vaga(f"s{i}", fila=f, root=root)
    b = FakeBackend()
    res = sa.lancar(sp_vazio, _semente(tmp_path), b, cwd=tmp_path, estado_root=root, sleep=lambda s: None)
    assert res["estado"] == "pendente" and b.abertos == []


def test_lancar_falha_no_envio_fecha_o_painel_e_liberta(modelos_json, sp_vazio, tmp_path):
    b = FakeBackend(enviar_ok=False)
    root = tmp_path / "estado"
    res = sa.lancar(sp_vazio, _semente(tmp_path), b, cwd=tmp_path, estado_root=root, sleep=lambda s: None)
    assert res["estado"] == "falhou" and b.fechados == ["p1"]
    assert pe.vagas_livres(root=root) == pe.MAX_PARALELO


def test_semente_inexistente_falha_antes_de_abrir(modelos_json, sp_vazio, tmp_path):
    b = FakeBackend()
    with pytest.raises(sa.SpAutorErro):
        sa.lancar(sp_vazio, tmp_path / "nao.md", b, cwd=tmp_path, estado_root=tmp_path / "e", sleep=lambda s: None)
    assert b.abertos == []


def test_consume_imprime_e_apaga(tmp_path):
    s = _semente(tmp_path, "olá semente")
    vistos = []
    sa.consume(s, out=vistos.append)
    assert vistos == ["olá semente"] and not s.exists()


def test_consume_falha_ao_imprimir_mantem_o_ficheiro(tmp_path):
    s = _semente(tmp_path)

    def rebenta(_):
        raise OSError("sem stdout")

    with pytest.raises(OSError):
        sa.consume(s, out=rebenta)
    assert s.exists()


def test_cli_dry_run_mostra_o_plano(modelos_json, sp_vazio, tmp_path, monkeypatch, capsys):
    rc = sa.main(["--sp", str(sp_vazio), "--semente", str(_semente(tmp_path)), "--dry-run", "--modelos", str(modelos_json)])
    out = capsys.readouterr().out
    assert rc == 0 and "sp-autor proj-algo-2026-11-11" in out and "claude-teste-1" in out


def test_cli_help_corre():
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "sp-autor.py"), "--help"], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and "--semente" in r.stdout


# --- aviso ao painel de origem ---------------------------------------------------------------

SLUG = "proj-algo-2026-11-11"
K = f"sp-autor-{SLUG}"


@pytest.fixture(autouse=True)
def _origem_livre(monkeypatch, tmp_path):
    monkeypatch.setattr(sa, "_livre", lambda b, p: True)
    monkeypatch.setenv("AVISOS_DIR", str(tmp_path / "avisos"))


def _estado(root):
    return pe.ler(pe.procurar(K, root=root), K, root=root)


def test_lancar_grava_a_origem_pelo_titulo(modelos_json, sp_vazio, tmp_path):
    b = FakeBackend()
    b.titulos_postos["7"] = "michi proj"
    root = tmp_path / "estado"
    sa.lancar(sp_vazio, _semente(tmp_path), b, cwd=tmp_path, estado_root=root, sleep=lambda s: None, origem=("michi proj", "7"))
    st = _estado(root)
    assert st["origem_titulo"] == "michi proj" and st["origem_pane"] == "7"


def test_origem_atual_le_o_ambiente(modelos_json):
    b = FakeBackend()
    b.titulos_postos["7"] = "michi proj"
    assert sa.origem_atual(b, env={"WEZTERM_PANE": "7"}) == ("michi proj", "7")
    assert sa.origem_atual(b, env={"TMUX_PANE": "7"}) == ("michi proj", "7")
    assert sa.origem_atual(b, env={}) == (None, None)
    assert sa.origem_atual(b, env={"WEZTERM_PANE": "9"}) == (None, "9")  # sem título


def test_lancar_sem_origem_grava_null_e_nao_falha(modelos_json, sp_vazio, tmp_path, monkeypatch):
    monkeypatch.delenv("WEZTERM_PANE", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    root = tmp_path / "estado"
    res = sa.lancar(sp_vazio, _semente(tmp_path), FakeBackend(), cwd=tmp_path, estado_root=root, sleep=lambda s: None)
    assert res["estado"] == "a-correr"
    assert _estado(root)["origem_titulo"] is None


def _lancado(modelos_json, sp_vazio, tmp_path, origem=("michi proj", "7")):
    b = FakeBackend()
    b.titulos_postos["7"] = "michi proj"
    root = tmp_path / "estado"
    sa.lancar(sp_vazio, _semente(tmp_path), b, cwd=tmp_path, estado_root=root, sleep=lambda s: None, origem=origem)
    b.enviados.clear()
    return b, root


def test_avisar_envia_uma_linha_ao_painel_certo(modelos_json, sp_vazio, tmp_path):
    b, root = _lancado(modelos_json, sp_vazio, tmp_path)
    assert sa.avisar(SLUG, b, sp=sp_vazio, estado_root=root) == "enviado"
    (pane, texto), = b.enviados
    assert pane == "7" and "\n" not in texto
    assert texto == (f"[sp-autor] SP {SLUG} preenchido: {sp_vazio}. Próximo: sp-resumo.py {SLUG} e aprovação (super-prompt §Gerar 3-5).")
    assert _estado(root)["aviso"] == "enviado"


def test_avisar_resolve_pelo_titulo_se_o_pane_mudou(modelos_json, sp_vazio, tmp_path):
    b, root = _lancado(modelos_json, sp_vazio, tmp_path)
    del b.titulos_postos["7"]
    b.titulos_postos["12"] = "michi proj"  # a origem foi movida para outro pane-id
    assert sa.avisar(SLUG, b, sp=sp_vazio, estado_root=root) == "enviado"
    assert b.enviados[0][0] == "12"


def test_avisar_pane_reaproveitado_com_outro_titulo_nao_envia(modelos_json, sp_vazio, tmp_path):
    b, root = _lancado(modelos_json, sp_vazio, tmp_path)
    b.titulos_postos["7"] = "outra coisa"
    assert sa.avisar(SLUG, b, sp=sp_vazio, estado_root=root) == "origem-ausente"
    assert b.enviados == []
    assert "origem ausente" in _estado(root)["aviso"]


def test_avisar_sem_origem_titulo_nao_envia(modelos_json, sp_vazio, tmp_path):
    b, root = _lancado(modelos_json, sp_vazio, tmp_path, origem=(None, None))
    assert sa.avisar(SLUG, b, estado_root=root) == "origem-ausente"
    assert b.enviados == [] and "origem ausente" in _estado(root)["aviso"]


def test_avisar_painel_morto_nao_envia(modelos_json, sp_vazio, tmp_path):
    b, root = _lancado(modelos_json, sp_vazio, tmp_path)
    del b.titulos_postos["7"]
    assert sa.avisar(SLUG, b, estado_root=root) == "origem-ausente" and b.enviados == []


def test_avisar_nunca_envia_ao_proprio_painel(modelos_json, sp_vazio, tmp_path):
    b, root = _lancado(modelos_json, sp_vazio, tmp_path, origem=("sp-autor " + SLUG, "p1"))
    assert sa.avisar(SLUG, b, sp=sp_vazio, estado_root=root) == "origem-ausente" and b.enviados == []


def test_prompt_manda_avisar_antes_do_done(sp_vazio, tmp_path):
    t = sa.prompt(sp_vazio, _semente(tmp_path))
    assert f"--avisar {SLUG}" in t and t.index("--avisar") < t.index("sp-estado.py")


def test_cli_dry_run_mostra_o_avisar(modelos_json, sp_vazio, tmp_path, capsys):
    rc = sa.main(["--sp", str(sp_vazio), "--semente", str(_semente(tmp_path)), "--dry-run", "--modelos", str(modelos_json)])
    assert rc == 0 and "--avisar" in capsys.readouterr().out


def test_cli_avisar_rc0_mesmo_sem_estado(tmp_path, monkeypatch):
    monkeypatch.setattr(sa.pe, "raiz", lambda root=None: tmp_path / "vazio")
    assert sa.main(["--avisar", "nao-existe", "--backend", "wezterm"]) == 0


def test_prompt_fecha_pelo_backend_e_nao_pelo_wezterm(sp_vazio):
    t = sa.prompt(sp_vazio, Path("s.md"))
    assert "sp-autor.py --fechar proj-algo-2026-11-11" in t and "kill-pane" not in t


def test_fechar_usa_o_pane_do_estado(modelos_json, sp_vazio, tmp_path):
    b, root = FakeBackend(), tmp_path / "estado"
    sa.lancar(sp_vazio, _semente(tmp_path), b, cwd=tmp_path, estado_root=root, sleep=lambda s: None)
    assert sa.fechar("proj-algo-2026-11-11", b, estado_root=root, env={}) == "p1"
    assert b.fechados == ["p1"]


def test_fechar_sem_estado_nao_fecha_nada(tmp_path, monkeypatch):
    b = FakeBackend()
    monkeypatch.setattr(sa.painel_backend, "painel_atual", lambda env=None: ("herdr", "w3:pX"))
    assert sa.fechar("nao-existe", b, estado_root=tmp_path / "e") is None
    assert b.fechados == []


def test_fechar_sem_estado_com_atual_fecha_o_atual(tmp_path, monkeypatch):
    b = FakeBackend()
    monkeypatch.setattr(sa.painel_backend, "painel_atual", lambda env=None: ("herdr", "w3:pX"))
    assert sa.fechar("nao-existe", b, estado_root=tmp_path / "e", atual=True) == "w3:pX"
    assert b.fechados == ["w3:pX"]


def test_main_fechar_passa_atual(monkeypatch, capsys):
    visto = {}
    monkeypatch.setattr(sa.painel_backend, "escolher_por_config", lambda b: FakeBackend())
    monkeypatch.setattr(sa, "fechar", lambda *a, **k: visto.update(k) or "ok")
    sa.main(["--fechar", "x", "--atual"])
    assert visto.get("atual") is True
    sa.main(["--fechar", "x"])
    assert visto.get("atual") is False


def test_prompts_fecham_com_atual():
    p = sa.prompt("sp/x.md", None)
    assert "--fechar x --atual" in p


def test_ec_022_prompt_nao_submetido_mantem_a_semente_e_permite_relancar(modelos_json, sp_vazio, tmp_path):
    """EC-022: o painel falha antes de ler a semente (`falhou`): a semente fica e o relançamento passa."""
    root = tmp_path / "estado"
    s = _semente(tmp_path, "decisões por ler")
    falha = sa.lancar(sp_vazio, s, FakeBackend(enviar_ok=False), cwd=tmp_path, estado_root=root, sleep=lambda x: None)
    assert falha["estado"] == "falhou"
    assert s.read_text(encoding="utf-8") == "decisões por ler"
    ok = FakeBackend()
    res = sa.lancar(sp_vazio, s, ok, cwd=tmp_path, estado_root=root, sleep=lambda x: None)
    assert res["estado"] == "a-correr" and len(ok.abertos) == 1
    assert any(str(s) in texto for _, texto in ok.enviados)


def test_main_fechar_nao_rebenta_com_import_local(monkeypatch, capsys):
    """Regressão: `import painel_backend` dentro de main tornava o nome local e o --fechar dava UnboundLocalError."""
    monkeypatch.setattr(sa.painel_backend, "escolher_por_config", lambda b: FakeBackend())
    monkeypatch.setattr(sa, "fechar", lambda *a, **k: "ok")
    assert sa.main(["--fechar", "x-2026-11-22", "--papel", "revisor"]) in (0, None)
    assert "fechar · ok" in capsys.readouterr().out


def test_avisar_origem_ocupada_vai_para_a_caixa(modelos_json, sp_vazio, tmp_path, monkeypatch):
    b, root = _lancado(modelos_json, sp_vazio, tmp_path)
    monkeypatch.setattr(sa, "_livre", lambda b, p: False)
    assert sa.avisar(SLUG, b, sp=sp_vazio, estado_root=root) == "caixa"
    assert b.enviados == [] and _estado(root)["aviso"] == "caixa"
    (m,) = sa.avisos_caixa.recolher("7")
    assert SLUG in m and sa.avisos_caixa.recolher("7") == []


def test_livre_le_o_ecra():
    assert sa.avisos_caixa.livre("❯ \n  Opus · ctx")
    assert not sa.avisos_caixa.livre("✽ Spelunking… esc to interrupt")
    assert not sa.avisos_caixa.livre("Enter to select · Esc to cancel")
    assert not sa.avisos_caixa.livre("")


def test_fechar_sem_aviso_avisa_a_origem(modelos_json, sp_vazio, tmp_path):
    b, root = _lancado(modelos_json, sp_vazio, tmp_path)
    sa.fechar(SLUG, b, estado_root=root)
    assert _estado(root)["aviso"] == "enviado" and b.enviados[0][0] == "7"


def test_fechar_com_aviso_nao_repete(modelos_json, sp_vazio, tmp_path):
    b, root = _lancado(modelos_json, sp_vazio, tmp_path)
    sa.avisar(SLUG, b, sp=sp_vazio, estado_root=root)
    b.enviados.clear()
    sa.fechar(SLUG, b, estado_root=root)
    assert b.enviados == []
