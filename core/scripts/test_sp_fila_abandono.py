"""Testes de scripts/sp-fila.py: arquivar fila obsoleta pára o vigia e remove a fila de painéis antes de mover."""
from sp_fila_testlib import sp_fila, _estado


def test_arquivar_obsoleta_para_vigia_e_remove_fila_paineis(tmp_path, monkeypatch):
    st = _estado(tmp_path, fila_paineis="fila-x", sessoes={})
    feito = []
    monkeypatch.setattr(sp_fila.sp_vigia, "parar", lambda *a: feito.append("vigia") or 123)
    monkeypatch.setattr(sp_fila.sp_fila_paineis.pe, "remover_fila", lambda fid: feito.append(("remover", fid)))
    destino = sp_fila.arquivar_obsoleta(st, sp_fila.ler(st), "m")
    assert feito == ["vigia", ("remover", "fila-x")] and not st.exists() and destino.exists()
    assert destino.parent == tmp_path / "obsoletas"


def test_arquivar_obsoleta_sem_fila_paineis_nao_toca_em_paineis(tmp_path, monkeypatch):
    st = _estado(tmp_path, sessoes={})
    feito = []
    monkeypatch.setattr(sp_fila.sp_vigia, "parar", lambda *a: feito.append("vigia"))
    monkeypatch.setattr(sp_fila.sp_fila_paineis.pe, "remover_fila", lambda fid: feito.append("remover"))
    assert sp_fila.arquivar_obsoleta(st, sp_fila.ler(st), "m").exists()
    assert feito == [] and not st.exists()


def test_falha_a_limpar_paineis_so_avisa_e_arquiva(tmp_path, monkeypatch, capsys):
    st = _estado(tmp_path, fila_paineis="fila-z", sessoes={})

    def falha(*a):
        raise RuntimeError("boom")
    monkeypatch.setattr(sp_fila.sp_vigia, "parar", falha)
    monkeypatch.setattr(sp_fila.sp_fila_paineis.pe, "remover_fila", falha)
    destino = sp_fila.arquivar_obsoleta(st, sp_fila.ler(st), "m")
    assert destino.exists() and not st.exists() and "aviso" in capsys.readouterr().err


def test_dois_arquivos_no_mesmo_segundo_nao_se_sobrepoem(tmp_path):
    from datetime import datetime
    agora = datetime(2026, 11, 20, 12, 0, 0)
    a = sp_fila.arquivar_obsoleta(_estado(tmp_path, sessoes={}), {}, "m", agora)
    b = sp_fila.arquivar_obsoleta(_estado(tmp_path, sessoes={}), {}, "m", agora)
    assert a != b and a.exists() and b.exists()
