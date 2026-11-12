"""Testes de `sp_leitura` (frontmatter e secções de SP).

Uso: python -m pytest scripts/test_sp_leitura.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_leitura  # noqa: E402

LF = "---\nslug: x\nmodo: 'auto'  # nota\ngates:\n  - cmd: pytest\n---\n# T\n\n## 4. Criterios\n- a\n\n## Progresso\nfeito\n"
CRLF = LF.replace("\n", "\r\n")


def test_frontmatter_lf_e_crlf_iguais():
    esperado = {"slug": "x", "modo": "auto", "gates": "", "- cmd": "pytest"}
    assert sp_leitura.frontmatter(LF) == esperado
    assert sp_leitura.frontmatter(CRLF) == esperado


def test_campos_so_topo_sem_limpar_aspas_nem_comentarios():
    for t in (LF, CRLF):
        c = sp_leitura.campos(t)
        assert c["slug"] == "x"
        assert c["modo"] == "'auto'  # nota"
        assert "- cmd" not in c and "cmd" not in c


def test_sem_frontmatter():
    assert sp_leitura.frontmatter("# so corpo\n") == {}
    assert sp_leitura.campos("# so corpo\n") == {}
    assert sp_leitura.bloco("# so corpo\n") == ""


def test_frontmatter_por_fechar():
    t = "---\nslug: x\nmodo: auto\n"
    assert sp_leitura.frontmatter(t) == {"slug": "x", "modo": "auto"}
    assert sp_leitura.campos(t) == {}
    assert sp_leitura.bloco(t) == ""


def test_frontmatter_invalido_ignora_linhas_sem_chave():
    assert sp_leitura.frontmatter("---\nsem-dois-pontos\n: vazio\nok: 1\n---\n") == {"ok": "1"}


def test_bloco_crlf():
    assert sp_leitura.bloco(CRLF).splitlines()[0] == "slug: x"


def test_seccao_meio_e_fim_do_ficheiro():
    for t in (LF, CRLF):
        assert sp_leitura.seccao(t, "4.").strip() == "- a"
        assert sp_leitura.seccao(t, "Progresso").strip() == "feito"


def test_seccao_inexistente():
    assert sp_leitura.seccao(LF, "Reflect") == ""


def test_seccao_caixa():
    assert sp_leitura.seccao(LF, "progresso") == ""
    assert sp_leitura.seccao(LF, "progresso", maiusculas=False).strip() == "feito"


def test_ler(tmp_path):
    p = tmp_path / "sp.md"
    p.write_bytes(CRLF.encode())
    fm, texto = sp_leitura.ler(p)
    assert fm["slug"] == "x"
    assert texto == LF  # read_text normaliza o CRLF
