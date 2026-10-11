"""L'`.envrc` dichiara il motore: `PGE_ENGINE_ROOT` sul submodule `engine/` (#1).

PGE-ui si lancia dalla cartella del brano (`cd mare-nostrum && pge-ui`, vedi
DMGiulioRomano/PGE-ui#165): il workspace e' la cwd, e il motore lo sceglie con
questa precedenza — `--root`, poi `$PGE_ENGINE_ROOT`, poi un `engine/` trovato
risalendo dalla cwd fino alla radice del repo. Qui la risposta e' una sola: il
submodule pinnato, lo stesso che rende `make brano`.

La risalita lo troverebbe anche senza dichiararlo, ma viene DOPO l'ambiente:
un `PGE_ENGINE_ROOT` ereditato dalla shell (quello di un altro checkout, per i
test di PGE-ui) vincerebbe sul submodule, e l'editor girerebbe su un motore
diverso da quello del Makefile senza dirlo. Dichiararlo nell'`.envrc` e' cio'
che lo fa vincere. Qui si pretende:

- che l'`.envrc`, valutato dalla sua cartella come fa direnv, dia
  `PGE_ENGINE_ROOT` = `<repo>/engine`, anche sopra uno ereditato;
- che quel motore sia quello di `make brano` e del ponte (`engine_bridge`):
  UI e Makefile sullo stesso codice per costruzione, non per coincidenza;
- che sia un motore per il criterio di PGE-ui (`src/main.py`), dove il
  submodule c'e': una dichiarazione sbagliata il bridge la rifiuta.
"""
import os
import re
import shutil
import subprocess

import pytest

from granstudies import engine_bridge

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENVRC = os.path.join(ROOT, ".envrc")
ENGINE = os.path.join(ROOT, "engine")

SHELL = shutil.which("bash") or shutil.which("sh")
shell = pytest.mark.skipif(SHELL is None, reason="serve una shell POSIX")
make = pytest.mark.skipif(shutil.which("make") is None, reason="serve make")


def _ambiente(**eredita):
    """L'ambiente di chi entra nel repo, senza le variabili di chi ha lanciato
    i test: un `PGE_ENGINE_ROOT` della shell non deve decidere il verdetto, in
    nessuna delle due direzioni."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("PGE_ENGINE_ROOT", "MAKEFLAGS", "MAKELEVEL", "MFLAGS")}
    env.update(eredita)
    return env


def _dichiarato(**eredita):
    """`PGE_ENGINE_ROOT` dopo l'`.envrc`, valutato dalla sua cartella.

    direnv fa cosi': entra nella cartella dell'`.envrc` e lo esegue in bash,
    quindi `$PWD` e' la radice del repo da qualunque sottocartella si arrivi."""
    p = subprocess.run(
        [SHELL, "-c", '. ./.envrc && printf %s "${PGE_ENGINE_ROOT-}"'],
        cwd=ROOT, env=_ambiente(**eredita),
        capture_output=True, text=True, check=True)
    return p.stdout


@shell
def test_envrc_dichiara_il_motore_sul_submodule():
    assert os.path.realpath(_dichiarato()) == os.path.realpath(ENGINE)


@shell
def test_la_dichiarazione_vince_su_un_motore_ereditato():
    """E' la ragione per scriverla: senza, l'ambiente batte la risalita."""
    altrove = os.path.join(os.sep, "altrove", "PythonGranularEngine")
    assert os.path.realpath(_dichiarato(PGE_ENGINE_ROOT=altrove)) \
        == os.path.realpath(ENGINE)


@shell
def test_il_motore_dichiarato_e_quello_del_ponte():
    """`engine_bridge` (analisi del laboratorio, test col motore) legge
    `engine/src` dal repo: lo stesso albero."""
    assert os.path.realpath(os.path.join(_dichiarato(), "src")) \
        == os.path.realpath(engine_bridge.ENGINE_SRC)


@shell
@make
def test_il_motore_dichiarato_e_quello_di_make_brano():
    """Si chiede a `make -n brano`, non lo si trascrive: il path che il
    Makefile manda all'interprete, risolto sulla cwd della ricetta (la radice),
    e' `src/main.py` del motore dichiarato. `MARKER=` toglie il venv dai
    prerequisiti, che `-n` stamperebbe senza dire niente del motore."""
    p = subprocess.run(["make", "-n", "brano", "MARKER="], cwd=ROOT,
                       env=_ambiente(), capture_output=True, text=True,
                       check=True)
    main = [t for t in re.split(r"\s+", p.stdout) if t.endswith("src/main.py")]
    assert len(main) == 1, p.stdout
    assert os.path.realpath(os.path.join(ROOT, main[0])) \
        == os.path.realpath(os.path.join(_dichiarato(), "src", "main.py"))


@shell
@pytest.mark.skipif(not os.path.isdir(engine_bridge.ENGINE_SRC),
                    reason="serve il submodule engine")
def test_il_motore_dichiarato_e_un_motore_per_pge_ui():
    """Il criterio di `is_engine_root` in PGE-ui: un checkout del motore e' una
    cartella con `src/main.py`. Una dichiarazione che non lo soddisfa non e'
    un invito a cercare altrove: il bridge esce nominandola."""
    assert os.path.isfile(os.path.join(_dichiarato(), "src", "main.py"))
