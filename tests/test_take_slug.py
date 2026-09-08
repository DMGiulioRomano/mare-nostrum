"""Nome della take: le chiavi cambiate, non solo il timestamp."""
from granstudies.__main__ import study_diff_slug


def _w(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


BASE = """
base:
  volume: 12
  grain: {duration: 0.01, envelope: hanning}
axes:
  fill_factor: {values: [1, 2]}
"""


def test_chiave_annidata_senza_prefisso_di_sezione(tmp_path):
    new = _w(tmp_path, "new.yml", BASE.replace("0.01", "0.02"))
    assert study_diff_slug(_w(tmp_path, "old.yml", BASE), new) == "grain.duration"


def test_lista_di_un_asse_e_una_chiave_sola_senza_values(tmp_path):
    new = _w(tmp_path, "new.yml", BASE.replace("[1, 2]", "[1, 2, 3, 4]"))
    assert study_diff_slug(_w(tmp_path, "old.yml", BASE), new) == "fill_factor"


def test_piu_chiavi_oltre_il_limite_si_contano(tmp_path):
    new = _w(tmp_path, "new.yml", BASE.replace("12", "9").replace("0.01", "0.02")
             .replace("hanning", "gauss").replace("[1, 2]", "[3]"))
    assert study_diff_slug(_w(tmp_path, "old.yml", BASE), new).endswith("+1altre")


def test_invariato_e_snapshot_assente_danno_slug_vuoto(tmp_path):
    old = _w(tmp_path, "old.yml", BASE)
    assert study_diff_slug(old, _w(tmp_path, "new.yml", BASE)) == ""
    assert study_diff_slug(str(tmp_path / "manca.yml"), old) == ""


def test_chiave_rimossa_compare_nel_nome(tmp_path):
    new = _w(tmp_path, "new.yml", BASE.replace("  volume: 12\n", ""))
    assert study_diff_slug(_w(tmp_path, "old.yml", BASE), new) == "volume"
