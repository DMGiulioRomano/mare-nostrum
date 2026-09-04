"""Impalcatura comune agli end-to-end (issue #4).

Un e2e, qui, e' un giro della **CLI vera** su un repo finto: una cartella
temporanea con lo stesso layout di quella reale — ``studies/<STUDY>/study.yml``,
``samples/``, ``generated/`` — ottenuta ridefinendo ``REPO_ROOT`` nel modulo
della CLI. I comandi girano identici a ``make sweep STUDY=...``, ma nessun
byte finisce nel repo di lavoro.

La differenza con i test unit non e' la profondita' delle asserzioni: e' il
punto d'ingresso. Qui si parte da uno `study.yml` **su disco**, si passa per
l'argparse e per la risoluzione dei path, e — dove l'engine c'e' — si arriva
al file audio. Un errore che vive solo nella cucitura fra questi pezzi (un
path costruito male, un documento sintatticamente valido ma che l'engine
rifiuta) non ha altro modo di farsi vedere.
"""
import os
import shutil

import numpy as np
import pytest
import soundfile as sf
import yaml

import granstudies.__main__ as cli


FIXTURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures"
)

STUDY = "e2e"
SAMPLE = "e2e_corpus.wav"

# Il sample sintetico: una sinusoide a 220 Hz, 2 s a 44.1 kHz. Deve essere
# piu' lungo del punto di lettura piu' avanzato usato dalle fixture, e non
# silenzioso — il render si asserisce anche sull'ampiezza.
SAMPLE_SR = 44100
SAMPLE_SECONDS = 2.0


class Repo:
    """Un repo granulation-studies usa-e-getta, pilotato dalla CLI."""

    def __init__(self, root: str):
        self.root = root
        self.study = STUDY
        self.sample = SAMPLE

    @staticmethod
    def fixture(name: str) -> str:
        """Path di una fixture di tests/fixtures/ (per gli override nei test)."""
        return os.path.join(FIXTURES, name)

    # --- pilotaggio -------------------------------------------------------

    def run(self, *argv: str) -> int:
        """Esegue un comando della CLI e pretende exit code 0."""
        rc = cli.main(list(argv))
        assert rc == 0, f"la CLI ha fallito: {' '.join(argv)} -> exit {rc}"
        return rc

    def write_study(self, data: dict) -> None:
        """Riscrive lo study.yml del repo finto (per gli override nei test)."""
        with open(self.study_yml, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)

    # --- path -------------------------------------------------------------

    @property
    def study_yml(self) -> str:
        return os.path.join(self.root, "studies", STUDY, "study.yml")

    @property
    def samples(self) -> str:
        return os.path.join(self.root, "samples")

    @property
    def generated(self) -> str:
        return os.path.join(self.root, "generated", STUDY)

    def yaml_dir(self, *parts: str) -> str:
        return os.path.join(self.generated, "yaml", *parts)

    # --- lettura di quello che e' stato scritto ---------------------------

    def written(self, *parts: str) -> list[str]:
        """Path degli YAML sotto ``yaml/<parts>``, ordinati, ricorsivi.

        ``streams_expanded.yml`` resta fuori: e' un artefatto di sola
        ispezione, non una variante (stessa esclusione che fa
        ``render_variants``).
        """
        out: list[str] = []
        for root, _, files in os.walk(self.yaml_dir(*parts)):
            for fname in files:
                if fname == "streams_expanded.yml":
                    continue
                if fname.endswith((".yml", ".yaml")):
                    out.append(os.path.join(root, fname))
        return sorted(out)

    def names(self, *parts: str) -> list[str]:
        """Basename senza estensione degli YAML sotto ``yaml/<parts>``."""
        return [
            os.path.splitext(os.path.basename(p))[0] for p in self.written(*parts)
        ]

    def document(self, *parts: str) -> dict:
        """Carica un singolo documento generato: ``document("stack", "stack.yml")``."""
        with open(self.yaml_dir(*parts), "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    def load(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)


def _make_repo(tmp_path, monkeypatch, fixture: str) -> Repo:
    root = str(tmp_path / "repo")
    os.makedirs(os.path.join(root, "studies", STUDY))
    os.makedirs(os.path.join(root, "samples"))

    shutil.copyfile(
        os.path.join(FIXTURES, fixture),
        os.path.join(root, "studies", STUDY, "study.yml"),
    )

    t = np.arange(int(SAMPLE_SR * SAMPLE_SECONDS)) / SAMPLE_SR
    sf.write(
        os.path.join(root, "samples", SAMPLE),
        0.5 * np.sin(2 * np.pi * 220 * t),
        SAMPLE_SR,
    )

    # study_dir/gen_dir/samples_dir leggono il REPO_ROOT del modulo CLI: e' la
    # sola cucitura da spostare per far vivere la pipeline altrove.
    monkeypatch.setattr(cli, "REPO_ROOT", root)
    return Repo(root)


@pytest.fixture
def sweep_repo(tmp_path, monkeypatch) -> Repo:
    """Repo finto con la fixture dello sweep (quattro assi, tre valori)."""
    return _make_repo(tmp_path, monkeypatch, "e2e_study.yml")


@pytest.fixture
def processes_repo(tmp_path, monkeypatch) -> Repo:
    """Repo finto con la fixture multi-stream (stack, versions, percorso)."""
    return _make_repo(tmp_path, monkeypatch, "e2e_processes.yml")
