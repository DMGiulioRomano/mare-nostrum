"""Il JS della pagina: che sia sintatticamente valido e che la FFT sia giusta.

Gira solo dove c'e' `node`. La STFT e' l'unico pezzo di matematica della
pagina, ed e' anche l'unico che puo' sbagliare in silenzio: uno spettrogramma
storto si guarda senza accorgersene. Il resto (canvas, cursori) e' verificabile
solo a occhio e resta fuori.
"""
import os
import shutil
import subprocess

import pytest

from granstudies.graph import _TEMPLATE_PATH

node = pytest.mark.skipif(shutil.which("node") is None, reason="serve node")


def _script() -> str:
    s = open(_TEMPLATE_PATH).read()
    return s[s.index("<script>") + len("<script>"):s.index("</script>")]


def _run(extra: str, tmp_path) -> str:
    js = _script()
    js = js[js.index("const twiddles"):js.index("function mixdown")]
    p = tmp_path / "t.js"
    p.write_text(js + extra)
    out = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


@node
def test_il_javascript_della_pagina_e_sintatticamente_valido(tmp_path):
    p = tmp_path / "page.js"
    p.write_text(_script().replace("__DATA__", "{keys:[],values:{},combos:[]}"))
    out = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


@node
@pytest.mark.parametrize("nfft", [256, 512, 1024, 2048, 4096, 8192])
def test_la_stft_mette_il_picco_alla_frequenza_giusta(tmp_path, nfft):
    """Seno a 1000 Hz: il bin di massima energia vale ~1000 Hz, a ogni finestra.

    Vale per tutte le risoluzioni offerte dalla pagina: cambiare finestra
    cambia la precisione, non la taratura.
    """
    got = _run("""
const rate = 48000, f = 1000, N = %d * 8, NFFT = %d;
const x = new Float32Array(N);
for (let i = 0; i < N; i++) x[i] = Math.sin(2 * Math.PI * f * i / rate);
const s = stft(x, NFFT);
let best = 0;
for (let b = 0; b < s.bins; b++) if (s.db[b] > s.db[best]) best = b;
const far = Math.round(s.bins * 0.9);
console.log((best * (rate / 2) / s.bins).toFixed(1), s.db[best].toFixed(2), s.db[far].toFixed(1));
""" % (nfft, nfft), tmp_path)
    hz, peak_db, far_db = (float(v) for v in got.split())
    assert abs(hz - 1000) <= 48000 / nfft   # entro una risoluzione di bin
    assert -8 < peak_db < -5                # ampiezza 1, ~6 dB tolti dalla finestra di Hann
    assert far_db == -96                    # lontano dal picco si sta sul floor


@node
def test_l_hop_e_un_quarto_della_finestra_a_ogni_risoluzione(tmp_path):
    """Il numero di colonne segue l'hop: quattro volte piu' fitto per ottava."""
    got = _run("""
const x = new Float32Array(48000);
console.log([512, 1024, 2048].map(n => stft(x, n).cols).join(" "));
""", tmp_path)
    c512, c1024, c2048 = (int(v) for v in got.split())
    assert abs(c512 / c1024 - 2) < 0.05
    assert abs(c1024 / c2048 - 2) < 0.05


@node
def test_la_stft_tiene_la_continua_nel_bin_zero(tmp_path):
    got = _run("""
const s = stft(new Float32Array(2048 * 4).fill(1), 2048);
console.log(s.db[0].toFixed(1), s.db[50].toFixed(1));
""", tmp_path)
    dc_db, far_db = (float(v) for v in got.split())
    assert abs(dc_db) < 0.5
    assert far_db == -96
