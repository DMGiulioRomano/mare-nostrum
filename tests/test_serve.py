"""Il render on demand: documento JSON -> YAML leggibile -> engine."""
import os
import socket
import subprocess
import sys
import time

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


def test_si_salva_il_documento_e_si_rende_l_ascolto(tmp_path, monkeypatch):
    """Con `ascolto` il file su disco e' `doc`, l'audio viene da `ascolto`.

    E' la pagina a sapere cosa togliere per ascoltare (il piazzamento nel
    brano); il server scrive i due e rende il secondo, accanto al primo.
    """
    rese = []
    monkeypatch.setattr(S.subprocess, "run", lambda cmd, **k: rese.append(cmd) or _ok())
    ascolto = {"duration": 4, "streams": [dict(DOC["streams"][0], onset=0)]}
    doc = {"duration": 4, "streams": [dict(DOC["streams"][0], onset=43.761, mute=True)]}
    out = S.render_doc(doc, "x", str(tmp_path), str(tmp_path), ascolto=ascolto)
    salvato = tmp_path / "live" / "x.yml"
    assert out["ok"] and out["yaml"] == "live/x.yml" and out["src"] == "live/x.aif"
    assert S.yaml.safe_load(salvato.read_text()) == doc
    reso = rese[0][2]
    assert reso != str(salvato)
    assert S.yaml.safe_load(open(reso).read()) == ascolto
    assert rese[0][3] == str(tmp_path / "live" / "x.aif")


def test_senza_ascolto_si_rende_il_documento_salvato(tmp_path, monkeypatch):
    rese = []
    monkeypatch.setattr(S.subprocess, "run", lambda cmd, **k: rese.append(cmd) or _ok())
    S.render_doc(DOC, "x", str(tmp_path), str(tmp_path), ascolto=DOC)
    assert rese[0][2] == str(tmp_path / "live" / "x.yml")


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


def test_un_estensione_maiuscola_non_si_raddoppia(tmp_path, monkeypatch):
    """`risacca.YML` e' gia' un documento YAML. Scritto in `risacca.YML.yml`,
    il file aperto restava com'era e il laboratorio ne lavorava un altro accanto
    — che il master del brano non importa."""
    monkeypatch.setattr(S.subprocess, "run", _ok)
    f = tmp_path / "risacca.YML"
    S._AUTORIZZATI.add(os.path.abspath(str(f)))
    out = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path), render=False, path=str(f))
    assert out["ok"] and out["path"] == str(f)
    assert f.exists() and not (tmp_path / "risacca.YML.yml").exists()


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


# --- la porta occupata: un nostro orfano si chiude, un estraneo no ---------

def _serverino(port):
    """Un server qualunque sulla porta: non e' un `granstudies serve`."""
    p = subprocess.Popen([sys.executable, "-m", "http.server", str(port),
                          "--bind", "127.0.0.1"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        time.sleep(0.1)
        if S.pid_sulla_porta(port) == p.pid:
            return p
    p.kill()
    raise AssertionError("il serverino di prova non ha preso la porta")


def _porta_libera():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_un_processo_non_nostro_non_si_chiude():
    port = _porta_libera()
    p = _serverino(port)
    try:
        assert S.libera_porta(port) is None      # non e' un granstudies serve
        assert p.poll() is None                  # ed e' ancora vivo
    finally:
        p.kill(); p.wait()


def test_un_nostro_serve_orfano_si_chiude_e_libera_la_porta(monkeypatch):
    port = _porta_libera()
    p = _serverino(port)
    try:
        # L'unica cosa che qui non si puo' avere davvero e' la riga di comando
        # di un `granstudies serve`: il resto (kill, attesa, porta libera) e'
        # quello vero.
        monkeypatch.setattr(S, "_e_un_nostro_serve", lambda pid: True)
        assert S.libera_porta(port) == p.pid
        assert S.pid_sulla_porta(port) is None
    finally:
        if p.poll() is None:
            p.kill()
        p.wait()


def test_i_recenti_sopravvivono_al_riavvio_e_restano_autorizzati(tmp_path, monkeypatch):
    """Gli ultimi tre file usciti da un pannello, il piu' recente in testa.

    La lista e' anche l'autorizzazione: un file gia' scelto in un pannello si
    riapre al prossimo avvio senza ripassare di li', altrimenti un recente si
    potrebbe elencare ma non aprire. Chi e' sparito dal disco non e' piu' un
    recente.
    """
    gen = tmp_path / "gen"
    gen.mkdir()
    S.recenti_carica(str(gen))
    scelti = []
    for n in ("a.yml", "b.yml", "c.yml", "d.yml"):
        f = tmp_path / n
        f.write_text("streams: []\n")
        scelti.append(str(f))
        monkeypatch.setattr(S.subprocess, "run",
                            lambda *a, _p=str(f), **k:
                            subprocess.CompletedProcess(a, 0, _p + "\n", ""))
        S.pannello("open")
    assert S._RECENTI == scelti[:0:-1]          # d, c, b: tre, il piu' nuovo primo
    os.remove(scelti[2])                        # c sparisce dal disco
    S._AUTORIZZATI.clear()                      # un altro avvio del server
    S._RECENTI.clear()
    S.recenti_carica(str(gen))
    assert S._RECENTI == [scelti[3], scelti[1]]
    assert S.autorizzato(scelti[3]) and not S.autorizzato(scelti[2])


# --- due editor, un file: la guardia sulla firma (#6) ----------------------
# Lo stesso file puo' stare aperto qui e in PGE-ui (regola 7 del piano). Chi
# scrive manda la firma che il file aveva quando l'ha letto; il server
# confronta e, se non coincide, non scrive.

def _mio(tmp_path, testo="streams: [{stream_id: risacca}]\n"):
    """Un file dell'utente, autorizzato, con la firma che l'editor ha letto."""
    f = tmp_path / "risacca.yml"
    f.write_text(testo)
    S._AUTORIZZATI.add(os.path.abspath(str(f)))
    return str(f), S.firma(str(f))


def test_la_firma_e_del_contenuto_non_dell_mtime(tmp_path):
    """Un mtime dice che qualcuno ha scritto, non che il file sia diverso — e
    le due risposte portano a cose opposte: rileggere, oppure lasciar passare
    la riscrittura di un file identico. L'algoritmo e' nel prefisso perche' la
    stessa firma la calcola PGE-ui (DMGiulioRomano/PGE-ui#185)."""
    f = tmp_path / "a.yml"
    f.write_text("streams: []\n")
    prima = S.firma(str(f))
    assert prima.startswith("sha256:")
    time.sleep(0.01)
    f.write_text("streams: []\n")              # l'altro editor salva identico
    assert S.firma(str(f)) == prima and not S.cambiato_su_disco(str(f), prima)
    f.write_text("streams: [x]\n")
    assert S.firma(str(f)) != prima and S.cambiato_su_disco(str(f), prima)


def test_non_si_scrive_se_il_file_su_disco_non_e_quello_letto(tmp_path, monkeypatch):
    monkeypatch.setattr(S.subprocess, "run", _ok)
    path, letta = _mio(tmp_path)
    open(path, "w").write("streams: [{stream_id: altro}]\n")   # l'altro editor
    out = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path), render=False,
                       path=path, firma_letta=letta)
    assert out["ok"] is False and out["cambiato"] is True
    assert "cambiato su disco" in out["error"]
    # E non ha scritto: il lavoro dell'altro editor e' ancora li'.
    assert "altro" in open(path).read()


def test_si_scrive_se_la_firma_coincide_e_torna_quella_nuova(tmp_path, monkeypatch):
    """La firma di cio' che si e' appena scritto torna alla pagina: senza, il
    salvataggio dopo manderebbe quella di prima e si accuserebbe da solo."""
    monkeypatch.setattr(S.subprocess, "run", _ok)
    path, letta = _mio(tmp_path)
    out = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path), render=False,
                       path=path, firma_letta=letta)
    assert out["ok"] and out["firma"] == S.firma(path) != letta
    assert S.yaml.safe_load(open(path).read()) == DOC
    # Il giro dopo, con la firma che e' tornata, passa.
    due = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path), render=False,
                       path=path, firma_letta=out["firma"])
    assert due["ok"] and due["firma"] == S.firma(path)


def test_sovrascrivi_scrive_sul_file_cambiato(tmp_path, monkeypatch):
    """La decisione dell'utente, presa nella pagina: qui si esegue."""
    monkeypatch.setattr(S.subprocess, "run", _ok)
    path, letta = _mio(tmp_path)
    open(path, "w").write("streams: [{stream_id: altro}]\n")
    out = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path), render=False,
                       path=path, firma_letta=letta, sovrascrivi=True)
    assert out["ok"] and S.yaml.safe_load(open(path).read()) == DOC


def test_un_file_che_non_c_e_piu_non_e_un_file_cambiato(tmp_path, monkeypatch):
    """Non ci sta il lavoro di nessuno, e rifiutare lascerebbe la domanda
    senza via d'uscita: "ricarica" non puo' rileggere un file cancellato, e
    scriverlo e' esattamente cio' che si stava chiedendo."""
    monkeypatch.setattr(S.subprocess, "run", _ok)
    path, letta = _mio(tmp_path)
    os.remove(path)
    out = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path), render=False,
                       path=path, firma_letta=letta)
    assert out["ok"] and os.path.isfile(path)


def test_senza_firma_letta_non_c_e_niente_da_confrontare(tmp_path, monkeypatch):
    """E' il `salva con nome` su un percorso nuovo: il laboratorio quel file
    non l'ha letto, e della sovrascrittura ha chiesto il pannello nativo."""
    monkeypatch.setattr(S.subprocess, "run", _ok)
    path, _ = _mio(tmp_path, "streams: [{stream_id: di-qualcun-altro}]\n")
    out = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path), render=False,
                       path=path)
    assert out["ok"] and S.yaml.safe_load(open(path).read()) == DOC


def test_il_giro_vero_open_poi_render_rifiutato(tmp_path, monkeypatch):
    """Le due rotte insieme, come le usa la pagina: `/open` da' il documento e
    la sua firma, `/render` la riporta. In mezzo scrive l'altro editor."""
    import http.client
    import threading

    monkeypatch.setattr(S.subprocess, "run", _ok)
    studio = tmp_path / "gen"
    studio.mkdir()
    path, _ = _mio(tmp_path)
    srv = S.crea(str(studio), str(tmp_path), 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        def posta(rotta, body):
            c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            c.request("POST", rotta, S.json.dumps(body),
                      {"Content-Type": "application/json"})
            return S.json.loads(c.getresponse().read())

        ap = posta("/open", {"path": path})
        assert ap["ok"] and ap["firma"] == S.firma(path)
        # La firma e' di esattamente il documento che e' tornato: una lettura
        # sola, non un hash preso a parte.
        assert ap["doc"] == S.yaml.safe_load(open(path, "rb").read())

        open(path, "w").write("streams: [{stream_id: altro}]\n")
        corpo = {"doc": DOC, "render": False, "path": path, "firma": ap["firma"]}
        no = posta("/render", corpo)
        assert no["ok"] is False and no["cambiato"] is True
        assert "altro" in open(path).read()

        # Rileggere e riprovare: la firma nuova passa.
        di_nuovo = posta("/open", {"path": path})
        si = posta("/render", dict(corpo, firma=di_nuovo["firma"]))
        assert si["ok"] and S.yaml.safe_load(open(path).read()) == DOC
    finally:
        srv.shutdown()


def test_un_render_fallito_dopo_la_scrittura_torna_la_firma_del_file(tmp_path, monkeypatch):
    """Lo YAML si scrive prima di rendere: se poi l'engine fallisce, il file
    su disco e' gia' quello nuovo. Senza la sua firma nella risposta la pagina
    terrebbe quella di prima, e la scrittura dopo si accuserebbe da sola di
    aver cambiato il file — che e' proprio quello che ha scritto lei."""
    def _ko(*a, **k):
        return subprocess.CompletedProcess(a, 1, "", "ValueError: bounds")
    monkeypatch.setattr(S.subprocess, "run", _ko)
    path, letta = _mio(tmp_path)
    out = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path), render=True,
                       path=path, firma_letta=letta)
    assert out["ok"] is False and "bounds" in out["error"]
    assert out["path"] == path and out["firma"] == S.firma(path) != letta
    # Il giro dopo, con quella firma, passa.
    monkeypatch.setattr(S.subprocess, "run", _ok)
    due = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path), render=False,
                       path=path, firma_letta=out["firma"])
    assert due["ok"]


# --- un documento gia' su disco non si riscrive --------------------------------
# I due editor scrivono lo stesso documento con formattazioni diverse (PGE-ui
# con js-yaml e la sua intestazione, il laboratorio con `_Dumper`), e la firma
# e' dei byte. Se il laboratorio riscrivesse il file a ogni `rendi e ascolta`
# anche senza averlo toccato, ogni ascolto cambierebbe i byte e la guardia
# dell'altro editor (DMGiulioRomano/PGE-ui#185, stessa firma) parlerebbe a
# vuoto: "cambiato su disco" su un documento che nessuno ha cambiato.

# Lo stesso documento di `DOC`, come lo scriverebbe un altro editor: un'altra
# formattazione e un commento in testa.
ALTRO_EDITOR = ("# saved: 2026-10-06T12:00:00\n"
                "duration: 4\n"
                "streams:\n"
                "  - stream_id: lab\n"
                "    grain:\n"
                "      duration:\n"
                "        - [0, 0.001]\n"
                "        - [1, 0.02]\n")


def test_un_documento_gia_su_disco_non_si_riscrive(tmp_path, monkeypatch):
    """Il file contiene gia' il documento: non si scrive, i byte dell'altro
    editor restano (commento compreso), e la firma che torna e' quella del
    file com'e'. Il render parte lo stesso, dal file su disco."""
    chiamate = []
    monkeypatch.setattr(S.subprocess, "run",
                        lambda cmd, **k: chiamate.append(cmd) or _ok(cmd))
    path, letta = _mio(tmp_path, ALTRO_EDITOR)
    out = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path), render=True,
                       path=path, firma_letta=letta)
    assert out["ok"] and out["firma"] == letta
    assert open(path).read() == ALTRO_EDITOR
    assert chiamate and chiamate[0][2] == path


def test_gia_su_disco_e_lo_stesso_documento_non_un_file_cambiato(tmp_path, monkeypatch):
    """L'altro editor ha riscritto lo stesso documento a modo suo dopo che
    l'ho letto: i byte sono cambiati, il documento no. Scrivere non
    cambierebbe niente, quindi non c'e' niente da sovrascrivere e niente da
    chiedere — e non si scrive."""
    monkeypatch.setattr(S.subprocess, "run", _ok)
    path, letta = _mio(tmp_path, S.yaml.safe_dump(DOC))
    open(path, "w").write(ALTRO_EDITOR)
    out = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path), render=False,
                       path=path, firma_letta=letta)
    assert out["ok"] and "cambiato" not in out
    assert open(path).read() == ALTRO_EDITOR
    assert out["firma"] == S.firma(path) != letta


def test_gia_su_disco_vuol_dire_anche_lo_stesso_tipo(tmp_path, monkeypatch):
    """Per l'engine `4` e `4.0` non sono sempre la stessa cosa (un `n_reps`
    float e' un errore dalla PGE#211), e nemmeno `1` e `true`: per Python
    sono uguali, per il documento no. Un valore che cambia tipo si scrive."""
    monkeypatch.setattr(S.subprocess, "run", _ok)
    for su_disco in (ALTRO_EDITOR.replace("duration: 4\n", "duration: 4.0\n"),
                     ALTRO_EDITOR.replace("[1, 0.02]", "[true, 0.02]")):
        path, letta = _mio(tmp_path, su_disco)
        out = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path), render=False,
                           path=path, firma_letta=letta)
        assert out["ok"] and open(path).read() != su_disco
        assert S.yaml.safe_load(open(path).read()) == DOC


def test_il_giro_vero_riletto_e_reso_non_riscrive_il_file_dell_altro_editor(tmp_path, monkeypatch):
    """Il caso per cui c'e' la regola: senza modifiche proprie il laboratorio
    rilegge il file che l'altro editor ha scritto e lo rende. Il documento
    che manda e' quello appena riletto, quindi il file resta dell'altro
    editor, byte per byte: la sua guardia, al giro dopo, non trova niente."""
    import http.client
    import threading

    monkeypatch.setattr(S.subprocess, "run", _ok)
    studio = tmp_path / "gen"
    studio.mkdir()
    path, _ = _mio(tmp_path, S.yaml.safe_dump({"streams": [{"stream_id": "lab"}]}))
    srv = S.crea(str(studio), str(tmp_path), 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        def posta(rotta, body):
            c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            c.request("POST", rotta, S.json.dumps(body),
                      {"Content-Type": "application/json"})
            return S.json.loads(c.getresponse().read())

        ap = posta("/open", {"path": path})
        open(path, "w").write(ALTRO_EDITOR)                 # l'altro editor
        no = posta("/render", {"doc": ap["doc"], "render": True, "path": path,
                               "firma": ap["firma"]})
        assert no["cambiato"] is True
        di_nuovo = posta("/open", {"path": path})
        si = posta("/render", {"doc": di_nuovo["doc"], "render": True,
                               "path": path, "firma": di_nuovo["firma"]})
        assert si["ok"] and si["firma"] == di_nuovo["firma"]
        assert open(path).read() == ALTRO_EDITOR
    finally:
        srv.shutdown()
