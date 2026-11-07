import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_indice  # noqa: E402


def _sp(p, status="TODO", crlf=False):
    txt = f"---\nstatus: {status}\nslug: x\n---\n# t\n"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes((txt.replace("\n", "\r\n") if crlf else txt).encode("utf-8"))


def test_frontmatter_cache_um_so_read(tmp_path, monkeypatch):
    sp_indice.invalidar()
    f = tmp_path / "sp" / "TODO" / "a.md"
    _sp(f)
    n = []
    real = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: (n.append(1), real(self, *a, **k))[1])
    assert sp_indice.frontmatter(f)["status"] == "TODO"
    assert sp_indice.frontmatter(f)["slug"] == "x"
    assert len(n) == 1


def test_frontmatter_devolve_copia(tmp_path):
    sp_indice.invalidar()
    f = tmp_path / "a.md"
    _sp(f)
    sp_indice.frontmatter(f)["status"] = "mudado"
    assert sp_indice.frontmatter(f)["status"] == "TODO"


def test_frontmatter_crlf(tmp_path):
    sp_indice.invalidar()
    f = tmp_path / "a.md"
    _sp(f, crlf=True)
    assert sp_indice.frontmatter(f) == {"status": "TODO", "slug": "x"}


def test_alteracao_do_ficheiro_invalida(tmp_path):
    sp_indice.invalidar()
    f = tmp_path / "a.md"
    _sp(f)
    assert sp_indice.frontmatter(f)["status"] == "TODO"
    _sp(f, status="Doing-longo")
    assert sp_indice.frontmatter(f)["status"] == "Doing-longo"


def test_invalidar_limpa(tmp_path):
    f = tmp_path / "a.md"
    _sp(f)
    sp_indice.listar(tmp_path)
    assert sp_indice._LISTAS
    sp_indice.invalidar()
    assert not sp_indice._LISTAS
    (tmp_path / "b.md").write_text("x", encoding="utf-8")
    assert [p.name for p in sp_indice.listar(tmp_path)] == ["a.md", "b.md"]


def test_listar_ordenado_e_cache(tmp_path):
    sp_indice.invalidar()
    for n in ("b.md", "a.md"):
        _sp(tmp_path / n)
    assert [p.name for p in sp_indice.listar(tmp_path)] == ["a.md", "b.md"]


def test_erro_de_leitura_propaga(tmp_path):
    sp_indice.invalidar()
    f = tmp_path / "a.md"
    f.write_bytes(b"\xff\xfe\x00bad")
    try:
        sp_indice.frontmatter(f)
    except UnicodeDecodeError:
        return
    raise AssertionError("devia propagar UnicodeDecodeError")


def test_listar_ve_ficheiro_novo_sem_invalidar(tmp_path):
    # O mtime de pasta é grosseiro em alguns runners Windows: avança-o à mão
    # depois de cada alteração para o teste não depender do relógio do FS.
    tick = [10**18]

    def bump():
        tick[0] += 10**9
        for pasta, _subs, _nomes in os.walk(tmp_path):
            os.utime(pasta, ns=(tick[0], tick[0]))

    sp_indice.invalidar()
    _sp(tmp_path / "a" / "sp" / "TODO" / "x.md")
    bump()
    assert len(sp_indice.listar(tmp_path)) == 1
    _sp(tmp_path / "b" / "sp" / "TODO" / "y.md")
    _sp(tmp_path / "a" / "sp" / "TODO" / "z.md")
    bump()
    assert [p.name for p in sp_indice.listar(tmp_path)] == ["x.md", "z.md", "y.md"]
    (tmp_path / "a" / "sp" / "TODO" / "x.md").unlink()
    bump()
    assert [p.name for p in sp_indice.listar(tmp_path)] == ["z.md", "y.md"]
