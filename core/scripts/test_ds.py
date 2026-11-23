"""Testes de ds_core.py, ds-init.py, ds-validate.py e ds-export.py (design system por projeto, tokens DTCG).

Uso: python -m pytest scripts/test_ds.py -q
rc: o do pytest
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from sp_carregar import carregar

AQUI = Path(__file__).resolve().parent
ds_core = carregar(AQUI / "ds_core.py", "ds_core")
ds_init = carregar(AQUI / "ds-init.py")
ds_validate = carregar(AQUI / "ds-validate.py")
ds_export = carregar(AQUI / "ds-export.py")


@pytest.fixture
def proj(tmp_path):
    assert ds_init.main(["demo", "--dir", str(tmp_path)]) == 0
    return tmp_path


def _tokens(proj):
    return json.loads((proj / "design" / "tokens.json").read_text(encoding="utf-8"))


def _grava(proj, tokens):
    (proj / "design" / "tokens.json").write_text(json.dumps(tokens), encoding="utf-8")


# --- contraste -----------------------------------------------------------------

def test_contraste_preto_branco_e_21():
    assert ds_core.contraste("#000", "#ffffff") == pytest.approx(21.0)


def test_contraste_e_simetrico_e_igual_a_1_para_a_mesma_cor():
    assert ds_core.contraste("#2563eb", "#ffffff") == pytest.approx(ds_core.contraste("#ffffff", "#2563eb"))
    assert ds_core.contraste("#777777", "#777777") == pytest.approx(1.0)


def test_contraste_valor_de_referencia_wcag():
    # #767676 sobre branco é o limite clássico de 4.54:1
    assert ds_core.contraste("#767676", "#fff") == pytest.approx(4.54, abs=0.01)


# --- ds-init ---------------------------------------------------------------------

def test_init_cria_design_md_e_tokens(proj):
    assert (proj / "DESIGN.md").read_text(encoding="utf-8").startswith("# demo")
    t = _tokens(proj)
    for grupo in ("color", "space", "radius", "shadow", "font", "motion", "breakpoint"):
        assert grupo in t
    for papel in ("bg", "surface", "text", "text-muted", "border", "primary", "on-primary", "focus", "danger"):
        assert papel in t["color"]["light"] and papel in t["color"]["dark"]
    assert [v["$value"] for v in t["space"].values()][:4] == ["0px", "4px", "8px", "12px"]


def test_init_nao_sobrescreve_sem_force(proj, capsys):
    assert ds_init.main(["demo", "--dir", str(proj)]) == 1
    assert "--force" in capsys.readouterr().err
    assert ds_init.main(["demo", "--dir", str(proj), "--force"]) == 0


def test_init_cor_invalida_rc2(tmp_path):
    assert ds_init.main(["x", "--dir", str(tmp_path), "--primaria", "azul"]) == 2
    assert not (tmp_path / "design").exists()


@pytest.mark.parametrize("cor", ["#2563eb", "#ffff00", "#000000", "#ffffff", "#ff0000", "#00ff00", "#9333ea", "#f97316", "#0f766e", "#abc"])
def test_gerado_passa_a_validacao_para_qualquer_cor_base(cor, tmp_path):
    assert ds_init.main(["p", "--dir", str(tmp_path), "--primaria", cor]) == 0
    assert ds_core.validar(_tokens(tmp_path)) == []


# --- ds-validate -----------------------------------------------------------------

def test_validate_ok(proj, capsys):
    assert ds_validate.main(["--dir", str(proj)]) == 0
    assert capsys.readouterr().out.startswith("ok:")


def test_validate_alias_partido(proj, capsys):
    t = _tokens(proj)
    t["color"]["light"]["primary"]["$value"] = "{color.palette.brand.999}"
    _grava(proj, t)
    assert ds_validate.main(["--dir", str(proj)]) == 1
    out = capsys.readouterr().out
    assert "[alias] color.light.primary: alias partido: {color.palette.brand.999}" in out


def test_validate_ciclo_de_alias():
    t = {"a": {"$type": "color", "$value": "{b}"}, "b": {"$type": "color", "$value": "{a}"}}
    assert any("ciclo de alias" in f for f in ds_core.validar(t))


def test_validate_contraste_insuficiente(proj, capsys):
    t = _tokens(proj)
    t["color"]["light"]["text"]["$value"] = "{color.palette.neutral.300}"
    _grava(proj, t)
    assert ds_validate.main(["--dir", str(proj)]) == 1
    out = capsys.readouterr().out
    assert "[contraste] color.light.text sobre color.light.bg" in out and "< 4.5:1 (text)" in out


def test_validate_ui_usa_limite_3(proj):
    t = _tokens(proj)
    t["color"]["palette"]["x"] = {"$type": "color", "$value": "#949494"}  # ~3.03:1 sobre branco
    t["color"]["light"]["border"]["$value"] = "{color.palette.x}"
    assert ds_core.validar(t) == []
    t["color"]["palette"]["x"]["$value"] = "#bbbbbb"
    assert any("color.light.border" in f and "3.0:1" in f for f in ds_core.validar(t))


def test_validate_sem_pares_declarados(proj):
    t = _tokens(proj)
    del t["$extensions"]
    assert any("sem pares declarados" in f for f in ds_core.validar(t))


def test_validate_par_com_token_inexistente(proj):
    t = _tokens(proj)
    t["$extensions"]["kaizen"]["contrast"].append({"fg": "color.light.nada", "bg": "color.light.bg"})
    assert any("token inexistente color.light.nada" in f for f in ds_core.validar(t))


def test_validate_schema_sem_type_e_valor_invalido(proj):
    t = _tokens(proj)
    t["radius"]["sm"] = {"$value": "4px"}
    t["radius"]["md"]["$value"] = "oito"
    t["color"]["palette"]["white"]["$value"] = "#12"
    f = ds_core.validar(t)
    assert any("radius.sm: sem $type" in x for x in f)
    assert any("radius.md: dimensão inválida" in x for x in f)
    assert any("color.palette.white" in x and "cor inválida" in x for x in f)


def test_validate_tipo_herdado_do_grupo():
    t = {"$extensions": {"kaizen": {"contrast": [{"fg": "c.a", "bg": "c.b"}]}},
         "c": {"$type": "color", "a": {"$value": "#000000"}, "b": {"$value": "#ffffff"}}}
    assert ds_core.validar(t) == []


def test_validate_escala_de_espacamento(proj):
    t = _tokens(proj)
    t["space"]["2"]["$value"] = "10px"
    f = ds_core.validar(t)
    assert any("space.2: 10px não é múltiplo de 4" in x for x in f)
    t = _tokens(proj)
    t["space"]["3"]["$value"] = "8px"
    assert any("space.3" in x and "não é maior" in x for x in ds_core.validar(t))


def test_validate_dimensao_em_rem_e_objeto():
    assert ds_core.px("0.5rem") == 8 and ds_core.px({"value": 4, "unit": "px"}) == 4 and ds_core.px("4em") is None


def test_validate_json_invalido_e_ficheiro_em_falta(tmp_path, capsys):
    assert ds_validate.main(["--dir", str(tmp_path)]) == 2
    (tmp_path / "design").mkdir()
    (tmp_path / "design" / "tokens.json").write_text("{", encoding="utf-8")
    assert ds_validate.main(["--dir", str(tmp_path)]) == 2
    assert "JSON válido" in capsys.readouterr().err


def test_validate_raiz_nao_objeto_e_sem_tokens():
    assert ds_core.validar([]) == ["[schema] (raiz): o JSON tem de ser um objeto"]
    assert any("sem tokens" in f for f in ds_core.validar({}))


# --- ds-export -------------------------------------------------------------------

def test_export_gera_css_com_tema_claro_e_escuro(proj):
    assert ds_export.main(["--dir", str(proj)]) == 0
    css = (proj / "design" / "tokens.css").read_text(encoding="utf-8")
    t = _tokens(proj)
    assert css.count("{") == css.count("}")
    assert "--space-2: 8px;" in css and "--radius-md: 8px;" in css
    assert "@media (prefers-color-scheme: dark)" in css and '[data-theme="dark"]' in css
    claro = ds_core.resolver(t["color"]["light"]["primary"]["$value"], t)
    escuro = ds_core.resolver(t["color"]["dark"]["primary"]["$value"], t)
    assert f"--color-primary: {claro};" in css and f"--color-primary: {escuro};" in css
    assert "{" not in "".join(ln for ln in css.splitlines() if ln.strip().startswith("--"))  # nenhum alias por resolver


def test_export_preset_tailwind(proj):
    ds_export.main(["--dir", str(proj)])
    js = (proj / "design" / "tailwind.preset.js").read_text(encoding="utf-8")
    assert js.startswith("//") and "module.exports = " in js
    preset = json.loads(js.split("module.exports = ", 1)[1].rstrip().rstrip(";"))
    ext = preset["theme"]["extend"]
    assert ext["colors"]["primary"] == "var(--color-primary)"
    assert ext["spacing"]["2"] == "var(--space-2)" and ext["screens"]["md"] == "768px"  # media queries não aceitam var()
    assert ext["fontFamily"]["sans"][0] == "Inter"


def test_export_recusa_tokens_invalidos_e_nao_escreve(proj, capsys):
    t = _tokens(proj)
    t["color"]["light"]["text"]["$value"] = "{color.palette.neutral.300}"
    _grava(proj, t)
    assert ds_export.main(["--dir", str(proj)]) == 1
    assert not (proj / "design" / "tokens.css").exists()
    assert "nada exportado" in capsys.readouterr().err


def test_export_out_noutra_pasta(proj, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    assert ds_export.main(["--dir", str(proj), "--out", str(out)]) == 0
    assert (out / "tokens.css").is_file() and not (proj / "design" / "tokens.css").exists()


def test_export_nao_mexe_nos_tokens(proj):
    antes = copy.deepcopy(_tokens(proj))
    ds_export.main(["--dir", str(proj)])
    assert _tokens(proj) == antes


# --- ponta a ponta pela linha de comandos ------------------------------------------

def test_cli_ponta_a_ponta(tmp_path):
    def corre(*a):
        return subprocess.run([sys.executable, "-I", *map(str, a)], capture_output=True, text=True, cwd=tmp_path)
    assert corre(AQUI / "ds-init.py", "demo").returncode == 0
    assert corre(AQUI / "ds-validate.py").returncode == 0
    assert corre(AQUI / "ds-export.py").returncode == 0
    assert (tmp_path / "design" / "tokens.css").is_file()
