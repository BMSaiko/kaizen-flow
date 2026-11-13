"""Testes de scripts/sp-aprovar.py e do portão «por aprovar» (fila, validador, sp-new)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
from sp_fila_testlib import make_sp, plan, reasons, slugs  # noqa: E402

sp_aprovar = kaizen_engine.load("sp-aprovar")
sp_validate = kaizen_engine.load("sp-validate")
sp_list = kaizen_engine.load("sp-list")


def fm_de(path):
    return sp_list.parse_frontmatter(path.read_bytes().decode("utf-8"))


def test_aprovar_grava_aprovado_e_grill(tmp_path):
    p = make_sp(tmp_path, "x", extra={"date": "2026-11-13"})
    msg = sp_aprovar.aprovar(tmp_path, "x", rondas=2)
    fm = fm_de(p)
    assert fm["aprovado"].startswith("20") and fm["aprovado"].endswith("Z")
    assert fm["grill"] == "2"
    assert "x" in msg


def test_aprovar_idempotente_e_preserva_crlf(tmp_path):
    p = make_sp(tmp_path, "x", extra={"date": "2026-11-13"})
    p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    sp_aprovar.aprovar(tmp_path, "x", rondas=1)
    antes = p.read_bytes()
    sp_aprovar.aprovar(tmp_path, "x", rondas=1)
    assert p.read_bytes() == antes
    assert b"\r\n" in antes and b"\n" not in antes.replace(b"\r\n", b"")


def test_aprovar_programa_cobre_mae_e_filhos(tmp_path):
    mae = make_sp(tmp_path, "mae", kind="program", extra={"date": "2026-11-13"})
    f1 = make_sp(tmp_path, "f1", extra={"date": "2026-11-13", "parent": "mae"})
    f2 = make_sp(tmp_path, "f2", folder="Done", extra={"date": "2026-11-13", "parent": "mae"})
    sp_aprovar.aprovar(tmp_path, "mae", rondas=3, programa=True)
    for p in (mae, f1, f2):
        assert fm_de(p)["grill"] == "3" and "aprovado" in fm_de(p)


def test_aprovar_exige_rondas_minimas(tmp_path):
    make_sp(tmp_path, "x", extra={"date": "2026-11-13"})
    try:
        sp_aprovar.aprovar(tmp_path, "x", rondas=0)
    except sp_aprovar.SpAprovarError as exc:
        assert "grill" in str(exc)
    else:
        raise AssertionError("devia recusar 0 rondas")


def test_verificar_recusa_sp_por_aprovar(tmp_path):
    make_sp(tmp_path, "x", extra={"date": "2026-11-13"})
    rc, msg = sp_aprovar.verificar(tmp_path, "x")
    assert rc == 1 and "sp-resumo.py" in msg
    sp_aprovar.aprovar(tmp_path, "x", rondas=1)
    assert sp_aprovar.verificar(tmp_path, "x")[0] == 0


def test_fila_ignora_sp_por_aprovar(tmp_path):
    make_sp(tmp_path, "novo", extra={"date": "2026-11-13"})
    make_sp(tmp_path, "velho", extra={"date": "2026-11-12"})
    r = plan(tmp_path)
    assert slugs(r) == ["velho"]
    assert "por aprovar" in reasons(r)["novo"]


def test_fila_aceita_aprovado_e_origem(tmp_path):
    make_sp(tmp_path, "ok", extra={"date": "2026-11-13", "aprovado": "2026-11-13T10:00:00Z", "grill": "1"})
    make_sp(tmp_path, "corr", extra={"date": "2026-11-13", "origem": "veredicto:abc"})
    assert sorted(slugs(plan(tmp_path))) == ["corr", "ok"]


def _texto(extra=""):
    return (
        "---\nstatus: TODO\ncreated: 2026-11-13T00:00:00Z\nupdated: 2026-11-13T00:00:00Z\nphase: SP\nslug: s\n"
        "date: 2026-11-13\nproject: p\npriority: P1\nmodo: auto\ngates:\n  - cmd: echo ok\n" + extra + "---\n"
        + "".join(f"## {n}. {t}\ncorpo\n\n" for n, t in sp_validate.SECTION_NAMES.items())
    )


def test_validate_exige_decisoes_e_gates_em_sp_novo():
    erros = sp_validate.validate(_texto())
    assert any("Decisões" in e for e in erros)
    ok = sp_validate.validate(_texto() + "## Decisões\n- uma decisão\n")
    assert not any("Decisões" in e for e in ok)


def test_validate_sp_sem_gates_falha_mesmo_manual():
    texto = _texto().replace("modo: auto", "modo: manual").replace("gates:\n  - cmd: echo ok\n", "") + "## Decisões\n- x\n"
    assert any("gate" in e for e in sp_validate.validate(texto))


def test_validate_origem_dispensa_decisoes():
    assert not any("Decisões" in e for e in sp_validate.validate(_texto("origem: pentest:x\n")))


def test_validate_sp_antigo_dispensa_decisoes():
    antigo = _texto().replace("date: 2026-11-13", "date: 2026-11-12")
    assert not any("Decisões" in e for e in sp_validate.validate(antigo))


def test_validate_ui_exige_esboco():
    base = _texto("ui: sim\n") + "## Decisões\n- x\n"
    assert any("Esboço" in e for e in sp_validate.validate(base))
    assert not any("Esboço" in e for e in sp_validate.validate(base + "## Esboço\n+--+\n"))
