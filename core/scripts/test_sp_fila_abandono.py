"""Testes de scripts/sp-fila.py: abandonar fila obsoleta limpa também o vigia e a fila de painéis."""
from sp_fila_testlib import sp_fila, _estado

A = type("A", (), {"abandonar_obsoleta": True})


def test_abandonar_obsoleta_para_vigia_e_remove_fila_paineis(tmp_path, monkeypatch):
    st = _estado(tmp_path, fila_paineis="fila-x", sessoes={})
    feito = []
    monkeypatch.setattr(sp_fila.sp_vigia, "parar", lambda *a: feito.append("vigia") or 123)
    monkeypatch.setattr(sp_fila.sp_fila_paineis.pe, "remover_fila", lambda fid: feito.append(("remover", fid)))
    assert sp_fila.abandonar_obsoleta(st, sp_fila.ler(st), "m", A(), tty=False)
    assert feito == ["vigia", ("remover", "fila-x")] and not st.exists()


def test_abandonar_obsoleta_sem_fila_paineis_nao_toca_em_paineis(tmp_path, monkeypatch):
    st = _estado(tmp_path, sessoes={})
    feito = []
    monkeypatch.setattr(sp_fila.sp_vigia, "parar", lambda *a: feito.append("vigia"))
    monkeypatch.setattr(sp_fila.sp_fila_paineis.pe, "remover_fila", lambda fid: feito.append("remover"))
    assert sp_fila.abandonar_obsoleta(st, sp_fila.ler(st), "m", A(), tty=False)
    assert feito == [] and not st.exists()
