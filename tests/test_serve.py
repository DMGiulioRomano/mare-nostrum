"""Il render on demand: documento JSON -> YAML leggibile -> engine."""
import os
import subprocess

from granstudies import serve as S


def _ok(*a, **k):
    return subprocess.CompletedProcess(a, 0, "", "")


DOC = {"duration": 4, "streams": [{"stream_id": "lab",
                                   "grain": {"duration": [[0, 0.001], [1, 0.02]]}}]}


def test_scrive_yaml_e_audio_accanto(tmp_path, monkeypatch):
    monkeypatch.setattr(S.subprocess, "run", _ok)
    out = S.render_doc(DOC, "prova bp", str(tmp_path), str(tmp_path))
    assert (out["ok"], out["src"], out["yaml"]) == (True, "live/prova_bp.aif", "live/prova_bp.yml")
    # I breakpoint su una riga sola: e' la forma in cui questi documenti si
    # leggono, e in block style sarebbero sei righe di trattini.
    assert "duration: [[0, 0.001], [1, 0.02]]" in (tmp_path / "live" / "prova_bp.yml").read_text()


def test_errore_dell_engine_torna_alla_pagina(tmp_path, monkeypatch):
    monkeypatch.setattr(S.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "boom"))
    out = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path))
    assert out["ok"] is False and "boom" in out["error"]


def test_nome_senza_scappatoie_di_percorso(tmp_path, monkeypatch):
    monkeypatch.setattr(S.subprocess, "run", _ok)
    out = S.render_doc(DOC, "../../etc/passwd", str(tmp_path), str(tmp_path))
    assert out["src"] == "live/.._.._etc_passwd.aif"
    assert (tmp_path / "live").exists() and list((tmp_path / "live").glob("*.yml"))


def test_salva_senza_rendere(tmp_path, monkeypatch):
    """Salvare e' immediato, rendere no: si tiene il lavoro senza aspettare."""
    chiamato = []
    monkeypatch.setattr(S.subprocess, "run", lambda *a, **k: chiamato.append(a) or _ok())
    out = S.render_doc(DOC, "bozza", str(tmp_path), str(tmp_path), render=False)
    assert (out["ok"], out["src"], out["yaml"]) == (True, None, "live/bozza.yml")
    assert not chiamato                      # l'engine non e' stato toccato
    assert (tmp_path / "live" / "bozza.yml").exists()


def test_la_pagina_non_si_cacha_ma_l_audio_si(tmp_path):
    """La pagina cambia a ogni `graph`: una copia vecchia mostra un
    laboratorio di ieri senza dirlo. L'audio invece ha sempre un nome nuovo."""
    import http.client
    import threading

    (tmp_path / "graph.html").write_text("<p>x</p>")
    (tmp_path / "a.aif").write_bytes(b"FORM")
    srv = S.crea(str(tmp_path), str(tmp_path), 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
        got = {}
        for path in ("/graph.html", "/a.aif"):
            c.request("GET", path)
            r = c.getresponse()
            got[path] = r.getheader("Cache-Control")
            r.read()
        assert got["/graph.html"] == "no-store"
        assert got["/a.aif"] is None
    finally:
        srv.shutdown()


def test_si_scrive_solo_dove_l_utente_ha_scelto_nel_pannello(tmp_path, monkeypatch):
    """Il dialogo nativo E' l'autorizzazione: senza, un POST scriverebbe ovunque."""
    monkeypatch.setattr(S.subprocess, "run", _ok)
    studio = tmp_path / "studio"
    studio.mkdir()
    fuori = tmp_path / "altrove" / "stream.yml"
    fuori.parent.mkdir()
    out = S.render_doc(DOC, "x", str(studio), str(studio), render=False, path=str(fuori))
    assert out["ok"] is False and "pannello" in out["error"]
    assert not fuori.exists()

    S._AUTORIZZATI.add(os.path.abspath(str(fuori)))
    out = S.render_doc(DOC, "x", str(studio), str(studio), render=False, path=str(fuori))
    assert out["ok"] and out["path"] == str(fuori)
    assert "duration: [[0, 0.001], [1, 0.02]]" in fuori.read_text()
    # Fuori dallo studio il path resta assoluto: la pagina non puo' servirlo
    # via HTTP, e spacciarlo per relativo darebbe un 404 silenzioso.
    assert out["yaml"] == str(fuori)


def test_il_pannello_annullato_non_e_un_errore(monkeypatch):
    """-128 vuol dire che l'utente ha chiuso il dialogo: si torna e basta."""
    monkeypatch.setattr(S.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 1, "", "execution error: Utente annullato. (-128)"))
    assert S.pannello("open") == ("", "")


def test_il_pannello_che_non_si_apre_lo_dice(monkeypatch):
    """Annullato e non-comparso sono lo stesso silenzio a schermo, cause opposte."""
    monkeypatch.setattr(S.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 1, "", "osascript: not authorized to send Apple events"))
    path, err = S.pannello("open")
    assert path == "" and "not authorized" in err


def test_il_percorso_scelto_diventa_autorizzato(monkeypatch, tmp_path):
    scelto = str(tmp_path / "nuovo.yml")
    monkeypatch.setattr(S.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, scelto + "\n", ""))
    assert S.pannello("save", "nuovo.yml") == (scelto, "")
    assert S.autorizzato(scelto)


def test_i_sample_si_servono_ma_solo_quelli(tmp_path):
    """Il laboratorio fa sentire un sample prima di sceglierlo: i file stanno
    in <repo>/samples, fuori dalla cartella servita. Fuori di li' niente."""
    import http.client
    import threading

    studio = tmp_path / "generated" / "s"
    studio.mkdir(parents=True)
    (tmp_path / "samples").mkdir()
    (tmp_path / "samples" / "a.wav").write_bytes(b"RIFF")
    (tmp_path / "segreto.txt").write_text("x")
    srv = S.crea(str(studio), str(tmp_path), 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        def get(url):
            c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            c.request("GET", url)
            r = c.getresponse()
            return r.status, r.read()

        assert get("/samples/a.wav") == (200, b"RIFF")
        assert get("/samples/../segreto.txt")[0] == 404
        assert get("/samples/manca.wav")[0] == 404
    finally:
        srv.shutdown()
