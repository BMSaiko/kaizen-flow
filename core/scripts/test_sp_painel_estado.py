"""Testes de scripts/sp_painel_estado.py e da escrita/listagem de scripts/sp-estado.py (estado por fila e por SP)."""
import importlib.util
import json
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import pytest

import sp_painel_estado as pe

SCRIPTS = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("sp_estado_cli", SCRIPTS / "sp-estado.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

T0 = datetime(2026, 11, 11, 10, 0, 0)


def _duas_filas(root, n=3):
    a = pe.criar_fila(programa="prog-a", ordem=[f"a{i}" for i in range(n)], root=root, agora=T0)
    b = pe.criar_fila(programa="prog-b", ordem=[f"b{i}" for i in range(n)], root=root, agora=T0)
    return a, b


def _bytes(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


# --- filas e ficheiros ---

def test_fila_id_vem_do_programa_ou_da_data_hora():
    assert pe.fila_id("kaizenflow-fila-paineis-2026-11-11") == "kaizenflow-fila-paineis-2026-11-11"
    assert pe.fila_id(None, T0) == "fila-20261111-100000"


def test_criar_fila_escreve_fila_json_e_um_json_por_sp(tmp_path):
    fid = pe.criar_fila(programa="prog-a", modo="sequencial", limites={"max": 5}, ordem=["x", "y"], root=tmp_path, agora=T0)
    fila = json.loads((tmp_path / fid / "fila.json").read_text(encoding="utf-8"))
    assert (fila["programa"], fila["modo"], fila["limites"], fila["ordem"]) == ("prog-a", "sequencial", {"max": 5}, ["x", "y"])
    sp = json.loads((tmp_path / fid / "x.json").read_text(encoding="utf-8"))
    assert sp["estado"] == "pendente"
    assert {"estado", "modelo", "worktree", "pane", "inicio", "fim", "msg"} <= set(sp)
    assert not list(tmp_path.rglob("*.tmp")) and not list(tmp_path.rglob("*.lock"))


def test_duas_filas_isoladas(tmp_path):
    a, b = _duas_filas(tmp_path)
    pe.registar(a, "a0", modelo="claude-opus-5-5", worktree="C:/wt/a0", pane="7", root=tmp_path)
    pe.transitar("a0", "a-correr", root=tmp_path, agora=T0)
    antes_b = {k: v for k, v in _bytes(tmp_path).items() if k.startswith(b)}
    pe.transitar("a0", "done", msg="feito", root=tmp_path, agora=T0)
    assert {k: v for k, v in _bytes(tmp_path).items() if k.startswith(b)} == antes_b
    assert pe.ler(a, "a0", root=tmp_path)["estado"] == "done"
    assert all(sp["estado"] == "pendente" for sp in pe.ler(b, root=tmp_path)["sps"].values())
    assert pe.procurar("b1", root=tmp_path) == b and pe.procurar("a1", root=tmp_path) == a


def test_fila_de_programa_repetida_e_recusada_e_sem_programa_ganha_sufixo(tmp_path):
    pe.criar_fila(programa="prog-a", root=tmp_path, agora=T0)
    with pytest.raises(pe.ErroEstado, match="já existe"):
        pe.criar_fila(programa="prog-a", root=tmp_path, agora=T0)
    um = pe.criar_fila(root=tmp_path, agora=T0)
    dois = pe.criar_fila(root=tmp_path, agora=T0)
    assert um == "fila-20261111-100000" and dois != um and dois.startswith(um)


def test_registar_guarda_campos_sem_mexer_no_estado_e_acrescenta_a_ordem(tmp_path):
    fid = pe.criar_fila(programa="prog-a", ordem=["x"], root=tmp_path, agora=T0)
    pe.transitar("x", "a-correr", root=tmp_path, agora=T0)
    pe.registar(fid, "x", modelo="m", worktree="w", pane="3", root=tmp_path)
    pe.registar(fid, "novo", modelo="m2", root=tmp_path)
    sp = pe.ler(fid, "x", root=tmp_path)
    assert (sp["estado"], sp["modelo"], sp["worktree"], sp["pane"]) == ("a-correr", "m", "w", "3")
    assert pe.ler(fid, root=tmp_path)["fila"]["ordem"] == ["x", "novo"]
    assert pe.ler(fid, "novo", root=tmp_path)["estado"] == "pendente"
    with pytest.raises(pe.ErroEstado, match="campo"):
        pe.registar(fid, "x", estado="done", root=tmp_path)


@pytest.mark.parametrize("mau", ["..", "../fora", "a/b", "a\\b", "", ".oculto", "fila", "FILA", "x" * 200, "a b",
                                 "NUL", "con", "COM1", "lpt9.velho", "aux"])
def test_nomes_que_saem_da_pasta_sao_recusados(tmp_path, mau):
    fid = pe.criar_fila(programa="prog-a", root=tmp_path, agora=T0)
    with pytest.raises(pe.ErroEstado, match="inválido"):
        pe.registar(fid, mau, root=tmp_path)
    if mau.lower() != "fila":
        with pytest.raises(pe.ErroEstado, match="inválido"):
            pe.criar_fila(programa=mau, root=tmp_path, agora=T0) if mau else pe.ler(mau, root=tmp_path)
    assert not (tmp_path.parent / "fora").exists()


def test_raiz_vem_do_argumento_do_ambiente_ou_da_home(tmp_path, monkeypatch):
    monkeypatch.setenv(pe.ENV_ROOT, str(tmp_path / "env"))
    assert pe.raiz() == tmp_path / "env" and pe.raiz(tmp_path / "arg") == tmp_path / "arg"
    monkeypatch.delenv(pe.ENV_ROOT)
    assert pe.raiz() == Path.home() / ".claude" / "sp-fila"


# --- transições ---

def test_estados_validos():
    assert set(pe.ESTADOS) == {"pendente", "a-correr", "pergunta", "done", "bloqueado", "falhou"}


def test_percurso_normal_marca_inicio_e_fim(tmp_path):
    fid = pe.criar_fila(programa="prog-a", ordem=["x"], root=tmp_path, agora=T0)
    pe.transitar("x", "a-correr", root=tmp_path, agora=T0)
    pe.transitar("x", "pergunta", msg="sequencial ou paralelo?", root=tmp_path, agora=T0)
    assert pe.ler(fid, "x", root=tmp_path)["msg"] == "sequencial ou paralelo?"
    pe.transitar("x", "a-correr", root=tmp_path, agora=T0)
    sp = pe.ler(fid, "x", root=tmp_path)
    assert sp["msg"] is None and sp["fim"] is None
    pe.transitar("x", "done", msg="ok", root=tmp_path, agora=datetime(2026, 11, 11, 11, 0, 0))
    sp = pe.ler(fid, "x", root=tmp_path)
    assert (sp["estado"], sp["inicio"], sp["fim"], sp["msg"]) == ("done", "2026-11-11T10:00:00", "2026-11-11T11:00:00", "ok")


@pytest.mark.parametrize("percurso, invalido", [
    ([], "done"),
    ([], "pergunta"),
    (["a-correr", "done"], "a-correr"),
    (["a-correr", "done"], "pendente"),
    (["a-correr", "falhou"], "done"),
    (["a-correr", "bloqueado"], "done"),
    (["a-correr"], "pendente"),
    ([], "inventado"),
])
def test_transicao_invalida_nao_escreve(tmp_path, percurso, invalido):
    pe.criar_fila(programa="prog-a", ordem=["x"], root=tmp_path, agora=T0)
    for e in percurso:
        pe.transitar("x", e, root=tmp_path, agora=T0)
    antes = _bytes(tmp_path)
    with pytest.raises(pe.ErroEstado, match="inválid"):
        pe.transitar("x", invalido, msg="não devia ficar", root=tmp_path, agora=T0)
    assert _bytes(tmp_path) == antes


def test_bloqueado_e_falhado_podem_ser_relancados(tmp_path):
    fid = pe.criar_fila(programa="prog-a", ordem=["x"], root=tmp_path, agora=T0)
    for e in ("a-correr", "bloqueado", "a-correr", "falhou", "pendente", "a-correr"):
        pe.transitar("x", e, root=tmp_path, agora=T0)
    assert pe.ler(fid, "x", root=tmp_path)["estado"] == "a-correr"


def test_slug_desconhecido(tmp_path):
    _duas_filas(tmp_path)
    antes = _bytes(tmp_path)
    with pytest.raises(pe.ErroEstado, match="desconhecido"):
        pe.transitar("nao-existe", "a-correr", root=tmp_path)
    with pytest.raises(pe.ErroEstado, match="desconhecido"):
        pe.procurar("nao-existe", root=tmp_path / "vazio")
    with pytest.raises(pe.ErroEstado, match="desconhecid"):
        pe.transitar("a0", "a-correr", fila="outra-fila", root=tmp_path)
    assert _bytes(tmp_path) == antes


def test_slug_em_duas_filas_escolhe_a_que_nao_acabou(tmp_path):
    velha = pe.criar_fila(programa="velha", ordem=["x"], root=tmp_path, agora=T0)
    pe.transitar("x", "a-correr", root=tmp_path, agora=T0)
    pe.transitar("x", "falhou", root=tmp_path, agora=T0)
    nova = pe.criar_fila(programa="nova", ordem=["x"], root=tmp_path, agora=datetime(2026, 11, 11, 12, 0, 0))
    assert pe.procurar("x", root=tmp_path) == nova
    pe.transitar("x", "a-correr", root=tmp_path, agora=T0)
    assert pe.ler(nova, "x", root=tmp_path)["estado"] == "a-correr" and pe.ler(velha, "x", root=tmp_path)["estado"] == "falhou"


# --- teto global e corrida ---

def test_teto_global_soma_todas_as_filas(tmp_path):
    _duas_filas(tmp_path)
    assert pe.MAX_PARALELO == 3 and pe.vagas_livres(root=tmp_path) == 3
    assert pe.reclamar_vaga("a0", root=tmp_path) and pe.reclamar_vaga("b0", root=tmp_path)
    assert pe.vagas_livres(root=tmp_path) == 1
    assert pe.reclamar_vaga("a1", pane="9", worktree="w", root=tmp_path)
    assert pe.vagas_livres(root=tmp_path) == 0
    antes = _bytes(tmp_path)
    assert pe.reclamar_vaga("b1", pane="10", root=tmp_path) is False
    with pytest.raises(pe.ErroEstado, match="vaga"):
        pe.transitar("b1", "a-correr", root=tmp_path)
    assert _bytes(tmp_path) == antes
    pe.transitar("a0", "pergunta", root=tmp_path)  # pergunta continua a ocupar a vaga
    assert pe.vagas_livres(root=tmp_path) == 0 and pe.reclamar_vaga("b1", root=tmp_path) is False
    pe.transitar("a0", "a-correr", root=tmp_path)  # voltar de pergunta não precisa de vaga nova
    pe.transitar("b0", "bloqueado", root=tmp_path)
    assert pe.vagas_livres(root=tmp_path) == 1 and pe.reclamar_vaga("b1", root=tmp_path)
    assert pe.vagas_livres(root=tmp_path) == 0
    assert pe.ler("prog-a", "a1", root=tmp_path)["pane"] == "9"


def test_vagas_livres_sem_raiz_e_o_teto(tmp_path):
    assert pe.vagas_livres(root=tmp_path / "nada") == pe.MAX_PARALELO


def test_reclamar_vaga_de_estado_final_e_invalido(tmp_path):
    pe.criar_fila(programa="prog-a", ordem=["x"], root=tmp_path, agora=T0)
    pe.transitar("x", "a-correr", root=tmp_path)
    pe.transitar("x", "done", root=tmp_path)
    with pytest.raises(pe.ErroEstado, match="inválida"):
        pe.reclamar_vaga("x", root=tmp_path)


def test_corrida_de_claims_entre_threads(tmp_path):
    _duas_filas(tmp_path, n=6)
    slugs = [f"{p}{i}" for p in "ab" for i in range(6)]
    ganhos, erros = [], []

    def tenta(slug):
        try:
            if pe.reclamar_vaga(slug, root=tmp_path):
                ganhos.append(slug)
        except Exception as e:  # noqa: BLE001
            erros.append(e)

    ts = [threading.Thread(target=tenta, args=(s,)) for s in slugs]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not erros and len(ganhos) == 3 and pe.vagas_livres(root=tmp_path) == 0
    ativos = [sp["slug"] for f in pe.filas(root=tmp_path) for sp in f["sps"] if sp["estado"] == "a-correr"]
    assert sorted(ativos) == sorted(ganhos)


def test_corrida_de_claims_entre_processos(tmp_path):
    _duas_filas(tmp_path, n=4)
    codigo = ("import sys; sys.path.insert(0, sys.argv[1]); import sp_painel_estado as pe; "
              "print('GANHOU' if pe.reclamar_vaga(sys.argv[3], root=sys.argv[2]) else 'SEM-VAGA')")
    procs = [subprocess.Popen([sys.executable, "-I", "-c", codigo, str(SCRIPTS), str(tmp_path), f"{p}{i}"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for p in "ab" for i in range(4)]
    saidas = [p.communicate(timeout=60) for p in procs]
    assert all(p.returncode == 0 for p in procs), [e for _, e in saidas]
    assert sorted(o.strip() for o, _ in saidas) == ["GANHOU"] * 3 + ["SEM-VAGA"] * 5
    assert pe.vagas_livres(root=tmp_path) == 0
    assert sum(sp["estado"] == "a-correr" for f in pe.filas(root=tmp_path) for sp in f["sps"]) == 3
    assert not list(tmp_path.rglob("*.tmp")) and not list(tmp_path.rglob("*.lock"))


def test_duas_filas_criadas_em_paralelo_aparecem_na_listagem(tmp_path, capsys):
    ts = [threading.Thread(target=pe.criar_fila, kwargs={"programa": p, "ordem": [f"{p}-sp"], "root": tmp_path}) for p in ("fila-um", "fila-dois")]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert cli.main(["--listar", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "fila-um" in out and "fila-dois" in out and "fila-um-sp" in out and "fila-dois-sp" in out


# --- JSON corrompido ---

def test_json_corrompido_da_erro_claro_ocupa_vaga_e_nao_e_reescrito(tmp_path):
    a, _ = _duas_filas(tmp_path)
    mau = tmp_path / a / "a0.json"
    mau.write_text('{"estado": "a-cor', encoding="utf-8")
    with pytest.raises(pe.ErroEstado, match="ilegível"):
        pe.ler(a, "a0", root=tmp_path)
    with pytest.raises(pe.ErroEstado, match="ilegível"):
        pe.transitar("a0", "a-correr", root=tmp_path)
    assert mau.read_text(encoding="utf-8") == '{"estado": "a-cor'  # intacto para diagnóstico
    assert pe.vagas_livres(root=tmp_path) == 2  # na dúvida conta como ocupada
    lista = {sp["slug"]: sp["estado"] for f in pe.filas(root=tmp_path) for sp in f["sps"]}
    assert lista["a0"] == "ilegível" and lista["a1"] == "pendente"
    pe.transitar("a1", "a-correr", root=tmp_path)  # os vizinhos continuam a funcionar


def test_json_que_nao_e_objeto_ou_com_estado_estranho_e_ilegivel(tmp_path):
    a, _ = _duas_filas(tmp_path)
    (tmp_path / a / "a0.json").write_text("[1, 2]", encoding="utf-8")
    (tmp_path / a / "a1.json").write_text('{"estado": "voando"}', encoding="utf-8")
    for slug in ("a0", "a1"):
        with pytest.raises(pe.ErroEstado, match="ilegível"):
            pe.ler(a, slug, root=tmp_path)
    assert pe.vagas_livres(root=tmp_path) == 1


def test_fila_json_corrompido_aparece_na_listagem_sem_rebentar(tmp_path):
    a, b = _duas_filas(tmp_path)
    (tmp_path / a / "fila.json").write_text("{lixo", encoding="utf-8")
    por_id = {f["fila"]: f for f in pe.filas(root=tmp_path)}
    assert por_id[a].get("erro") and len(por_id[b]["sps"]) == 3
    with pytest.raises(pe.ErroEstado, match="ilegível"):
        pe.ler(a, root=tmp_path)


def test_filas_ativas_deixa_de_fora_as_acabadas(tmp_path):
    a, b = _duas_filas(tmp_path, n=1)
    pe.transitar("a0", "a-correr", root=tmp_path)
    pe.transitar("a0", "done", root=tmp_path)
    assert [f["fila"] for f in pe.filas_ativas(root=tmp_path)] == [b]
    assert len(pe.filas(root=tmp_path)) == 2


# --- CLI sp-estado.py ---

def test_cli_grava_estado_e_mensagem(tmp_path, capsys):
    a, _ = _duas_filas(tmp_path)
    assert cli.main(["a0", "a-correr", "--root", str(tmp_path)]) == 0
    assert cli.main(["a0", "pergunta", "--msg", "qual ramo?", "--root", str(tmp_path)]) == 0
    sp = pe.ler(a, "a0", root=tmp_path)
    assert (sp["estado"], sp["msg"]) == ("pergunta", "qual ramo?")
    assert "a0" in capsys.readouterr().out


def test_cli_usa_a_raiz_do_ambiente(tmp_path, monkeypatch):
    a, _ = _duas_filas(tmp_path)
    monkeypatch.setenv(pe.ENV_ROOT, str(tmp_path))
    assert cli.main(["a0", "a-correr"]) == 0 and pe.ler(a, "a0", root=tmp_path)["estado"] == "a-correr"


@pytest.mark.parametrize("args, pista", [
    (["a0", "done"], "transição inválida"),
    (["a0", "inventado"], "estado inválido"),
    (["nao-existe", "a-correr"], "desconhecido"),
    (["../a0", "a-correr"], "inválido"),
])
def test_cli_erro_da_rc1_sem_escrever(tmp_path, capsys, args, pista):
    _duas_filas(tmp_path)
    antes = _bytes(tmp_path)
    assert cli.main([*args, "--root", str(tmp_path)]) == 1
    assert pista in capsys.readouterr().err and _bytes(tmp_path) == antes


def test_cli_sem_vaga_da_rc1(tmp_path, capsys):
    _duas_filas(tmp_path)
    for s in ("a0", "a1", "b0"):
        assert cli.main([s, "a-correr", "--root", str(tmp_path)]) == 0
    assert cli.main(["b1", "a-correr", "--root", str(tmp_path)]) == 1
    assert "vaga" in capsys.readouterr().err


def test_cli_listar_mostra_nomes_e_nunca_o_pane(tmp_path, capsys):
    a, b = _duas_filas(tmp_path, n=2)
    pe.reclamar_vaga("a0", pane="pane-4242", modelo="claude-opus-5-5", worktree="C:/wt/a0", root=tmp_path)
    pe.transitar("a0", "pergunta", msg="sequencial ou paralelo?", root=tmp_path)
    assert cli.main(["--listar", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert all(x in out for x in (a, b, "a0", "a1", "b0", "b1", "pergunta", "sequencial ou paralelo?", "claude-opus-5-5"))
    assert "4242" not in out and "2/3" in out
    assert cli.main(["--listar", "--json", "--root", str(tmp_path)]) == 0
    bruto = capsys.readouterr().out
    dados = json.loads(bruto)
    assert "4242" not in bruto and dados["vagas_livres"] == 2 and dados["max"] == 3
    assert {f["fila"] for f in dados["filas"]} == {a, b}
    assert {sp["slug"]: sp["estado"] for f in dados["filas"] for sp in f["sps"]}["a0"] == "pergunta"


def test_cli_listar_neutraliza_caracteres_de_controlo_da_mensagem(tmp_path, capsys):
    _duas_filas(tmp_path, n=1)
    pe.reclamar_vaga("a0", root=tmp_path)
    pe.transitar("a0", "bloqueado", msg="linha 1\nprog-z · falso · done\x1b[2J\x07", root=tmp_path)
    assert cli.main(["--listar", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out and "\x07" not in out
    assert len(out.strip().splitlines()) == 5  # vagas + 2 filas + 2 SPs: a mensagem não inventa linhas
    assert "linha 1 prog-z" in out


def test_cli_em_processo_escreve_a_recusa_em_utf8(tmp_path):
    _duas_filas(tmp_path, n=1)
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "sp-estado.py"), "a0", "done", "--root", str(tmp_path)],
                       capture_output=True)
    assert r.returncode == 1 and "transição inválida" in r.stderr.decode("utf-8")


def test_cli_listar_sem_filas(tmp_path, capsys):
    assert cli.main(["--listar", "--root", str(tmp_path / "vazio")]) == 0
    assert "sem filas" in capsys.readouterr().out
    assert not (tmp_path / "vazio").exists()  # listar é só leitura


def test_cli_listar_com_json_corrompido_nao_rebenta(tmp_path, capsys):
    a, _ = _duas_filas(tmp_path)
    (tmp_path / a / "a0.json").write_text("{lixo", encoding="utf-8")
    assert cli.main(["--listar", "--root", str(tmp_path)]) == 0
    assert "ilegível" in capsys.readouterr().out


# --- migração do estado antigo ---

def _antigo(tmp_path, **over):
    base = {"max": 5, "ate": None, "orcamento": None, "usados": 0, "feitos": ["f1"], "falhados": ["x1"], "saltados": [],
            "sessoes": {"s1": {"inicio": "2026-11-10T09:00:00", "painel": "12", "worktree": "C:/wt/s1"}},
            "projeto": None, "inicio": "2026-11-10T08:30:00", "commits": [], "concorrencia": 2, "programa": "mae-antiga"}
    base.update(over)
    f = tmp_path / "sp-fila-estado.json"
    f.write_text(json.dumps(base), encoding="utf-8")
    return f


def test_migra_o_estado_antigo_para_uma_fila_e_deixa_o_ficheiro(tmp_path):
    antigo = _antigo(tmp_path)
    antes = antigo.read_bytes()
    root = tmp_path / "filas"
    fid = pe.migrar_antigo(antigo, root=root)
    assert fid == "mae-antiga" and antigo.read_bytes() == antes  # a série continua a usar o ficheiro antigo
    dados = pe.ler(fid, root=root)
    assert dados["fila"]["modo"] == "paralelo" and dados["fila"]["limites"]["max"] == 5
    estados = {s: sp["estado"] for s, sp in dados["sps"].items()}
    assert estados == {"f1": "done", "x1": "falhou", "s1": "a-correr"}
    s1 = dados["sps"]["s1"]
    assert (s1["pane"], s1["worktree"], s1["inicio"]) == ("12", "C:/wt/s1", "2026-11-10T09:00:00")
    assert pe.vagas_livres(root=root) == 2


def test_migra_formato_lancado_sem_programa(tmp_path):
    antigo = _antigo(tmp_path, programa=None, sessoes={}, lancado="unico", concorrencia=1)
    root = tmp_path / "filas"
    fid = pe.migrar_antigo(antigo, root=root)
    assert fid == "fila-20261110-083000"
    dados = pe.ler(fid, root=root)
    assert dados["fila"]["modo"] == "sequencial" and dados["sps"]["unico"]["estado"] == "a-correr"


def test_migracao_sem_ficheiro_antigo_nao_faz_nada(tmp_path):
    assert pe.migrar_antigo(tmp_path / "nao-ha.json", root=tmp_path / "filas") is None
    assert not (tmp_path / "filas").exists()


@pytest.mark.parametrize("conteudo, pista", [
    ("{lixo", "ilegível"),
    ("[1, 2]", "formato"),
    ('{"qualquer": 1}', "formato"),
    (json.dumps({"sessoes": {"../fora": {}}, "inicio": "2026-11-10T08:30:00"}), "inválido"),
    (json.dumps({"sessoes": {f"s{i}": {} for i in range(4)}, "inicio": "2026-11-10T08:30:00"}), "teto"),
    (json.dumps({"sessoes": {"s1": {}}, "concorrencia": "muitos", "programa": "mae-x"}), "formato"),
    (json.dumps({"sessoes": {}, "lancado": ["a", "b"], "programa": "mae-x"}), "formato"),
    (json.dumps({"sessoes": {}, "feitos": [["a"], {"b": 1}], "programa": "mae-x"}), "formato"),
    (json.dumps({"sessoes": {}, "feitos": "abc", "programa": "mae-x"}), "formato"),
    (json.dumps({"sessoes": {"s1": {}}, "programa": ["mae-x"]}), "inválido"),
])
def test_migracao_recusada_com_mensagem_clara(tmp_path, conteudo, pista):
    antigo = tmp_path / "sp-fila-estado.json"
    antigo.write_text(conteudo, encoding="utf-8")
    root = tmp_path / "filas"
    with pytest.raises(pe.ErroEstado, match=pista):
        pe.migrar_antigo(antigo, root=root)
    assert antigo.read_text(encoding="utf-8") == conteudo
    assert not [p for p in root.rglob("*") if p.name != "estado.lock"] if root.exists() else True  # nem pasta a meio


def test_migracao_repetida_e_recusada(tmp_path):
    antigo = _antigo(tmp_path)
    root = tmp_path / "filas"
    pe.migrar_antigo(antigo, root=root)
    antes = _bytes(root)
    with pytest.raises(pe.ErroEstado, match="já"):
        pe.migrar_antigo(antigo, root=root)
    assert _bytes(root) == antes


def test_cli_migrar(tmp_path, capsys):
    antigo = _antigo(tmp_path)
    root = tmp_path / "filas"
    assert cli.main(["--migrar", "--antigo", str(antigo), "--root", str(root)]) == 0
    assert "mae-antiga" in capsys.readouterr().out
    assert cli.main(["--migrar", "--antigo", str(antigo), "--root", str(root)]) == 1
    assert "já" in capsys.readouterr().err
    assert cli.main(["--migrar", "--antigo", str(tmp_path / "nao-ha.json"), "--root", str(root)]) == 0


def test_sp_fila_estado_delega_no_modulo_novo():
    import sp_fila_estado
    assert sp_fila_estado.bloqueio is pe.bloqueio and sp_fila_estado.guardar is pe.guardar
    assert sp_fila_estado.pid_vivo is pe.pid_vivo and sp_fila_estado.migrar_para_filas


def test_listar_omite_arvores_terminadas_e_todas_mostra(tmp_path):
    velha = pe.criar_fila(programa="velha", ordem=["v1"], root=tmp_path, agora=T0)
    pe.registar(velha, "v1", root=tmp_path, agora=T0)
    pe.transitar("v1", "a-correr", root=tmp_path, agora=T0)
    pe.transitar("v1", "done", root=tmp_path, agora=T0)
    viva = pe.criar_fila(programa="viva", ordem=["x1"], root=tmp_path, agora=T0)
    pe.registar(viva, "x1", root=tmp_path, agora=T0)
    texto = cli.listar(tmp_path)
    assert "viva" in texto and "velha" not in texto
    assert "velha" in cli.listar(tmp_path, todas=True)
