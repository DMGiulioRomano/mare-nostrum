"""`make serve FILES=... / DIR=...`: un laboratorio per file, porte in fila.

Si chiede a `make -n` cosa lancerebbe: nessun server parte davvero.
"""
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="serve make")


def _lanci(**var):
    out = subprocess.run(["make", "-n", "serve", "STUDY=001-41-duration-pitch"]
                         + [f"{k}={v}" for k, v in var.items()],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    riga = next(l for l in out.splitlines() if "--apri" in l or "granstudies serve" in l)
    return riga


def test_i_nomi_si_cercano_in_configs_streams():
    riga = _lanci(FILES="stream2 stream7.yml")
    assert "for f in configs/streams/stream2.yml configs/streams/stream7.yml;" in riga


def test_un_path_resta_com_e():
    riga = _lanci(FILES="studies/x/y.yml")
    assert "for f in studies/x/y.yml;" in riga


def test_dir_apre_tutti_i_suoi_yaml():
    riga = _lanci(DIR="configs/streams")
    attesi = sorted(f"configs/streams/{n}" for n in os.listdir(os.path.join(ROOT, "configs/streams"))
                    if n.endswith(".yml"))
    assert re.search(r"for f in ([^;]*);", riga).group(1).split() == attesi


def test_senza_file_e_il_laboratorio_di_sempre():
    riga = _lanci()
    assert "--apri" not in riga and "--port 8000" in riga
