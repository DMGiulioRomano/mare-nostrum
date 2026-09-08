"""CLI di granstudies: orchestrazione della pipeline a stadi.

    granstudies sweep    STUDY      genera le varianti YAML (processo sweep)
    granstudies stack    STUDY      genera il documento multi-stream (processo stack)
    granstudies versions STUDY      genera il documento delle versioni (processo versions)
    granstudies percorso STUDY      genera il documento del percorso (processo percorso)
    granstudies render   STUDY      renderizza audio + partitura
    granstudies describe STUDY      calcola descrittori, aggiorna results.yml
    granstudies matrix   STUDY      costruisce kinship.json
    granstudies compose  STUDY      genera final.yml dal percorso/grafo
    granstudies render-final STUDY  renderizza il brano finale
    granstudies where    STUDY      stampa la cartella di output corrente

STUDY e' il nome della cartella sotto ``studies/`` (es. base).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
import time
from typing import Any, Dict

import yaml

from .document_let import apply_document_let
from .engine_bridge import REPO_ROOT
from .errors import SpecError


# --- layout dei path -------------------------------------------------------

def study_dir(study: str) -> str:
    return os.path.join(REPO_ROOT, "studies", study)


def take_label() -> str | None:
    """Label della take attiva, o ``None`` se la modalita' take e' spenta.

    L'interruttore e' la env ``TAKE``, pensata per essere esportata una volta
    per sessione di ascolto. ``1``/``true``/``yes`` vale "la take corrente",
    cioe' il symlink ``latest`` che ``make take`` sposta; qualunque altro
    valore e' la label di una take specifica, per tornare su una vecchia e
    rigenerare li' dentro.
    """
    take = os.environ.get("TAKE", "").strip()
    if not take:
        return None
    return "latest" if take.lower() in ("1", "true", "yes") else take


def gen_dir(study: str) -> str:
    """Cartella di output dello studio.

    Con la modalita' take attiva l'output non e' piu' ``generated/<study>/`` ma
    ``takes/<study>/<label>/``: albero completo e autonomo, cosi' l'audio della
    sessione precedente non viene sovrascritto. Le take nascono come hardlink
    della precedente (``make take``), quindi costano solo cio' che cambia.
    """
    label = take_label()
    if label is None:
        return os.path.join(REPO_ROOT, "generated", study)
    path = os.path.join(REPO_ROOT, "takes", study, label)
    if not os.path.isdir(path):
        raise SpecError(
            f"modalita' take attiva (TAKE={os.environ.get('TAKE')}) ma la take "
            f"'{label}' di '{study}' non esiste",
            hint=f"aprine una con 'make take STUDY={study}', "
                 f"o togli TAKE dall'ambiente per tornare a generated/",
        )
    # Il symlink ``latest`` viene risolto: i path che finiscono nei log, negli
    # snapshot e nelle sessioni .sv nominano la take vera, non l'alias mobile.
    return os.path.realpath(path)


def samples_dir(spec_samples: str | None) -> str:
    if spec_samples:
        return spec_samples if os.path.isabs(spec_samples) else os.path.join(REPO_ROOT, spec_samples)
    return os.path.join(REPO_ROOT, "samples")


def _load_spec(study: str):
    """Primo spec dello studio, con le stream risolte.

    Il documento grezzo di uno studio multi-stream e' incompleto per
    costruzione (gli override di stream completano le bande): va validato
    per-stream, mai cosi' com'e'. I campi che i comandi consumano da questo
    spec (samples_dir, base, seed) sono top-level, identici su ogni stream.
    """
    specs = _load_specs(study)
    return specs[0]


def _load_data(study: str) -> Dict[str, Any]:
    path = os.path.join(study_dir(study), "study.yml")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _emit(items) -> None:
    """Stampa la diagnostica non fatale su stderr. **Non** tocca l'exit code.

    Prefisso ``[warn]`` e lo stesso blocco degli errori: un rilievo e un
    errore devono leggersi allo stesso modo. La lista arriva da funzioni pure
    (``granstudies.diagnostics``), che il language server consuma tali e
    quali.
    """
    for d in items:
        print(f"[warn] {d.code}\n\n{d.format_block()}\n", file=sys.stderr)


def _load_specs(study: str, stream: str | None = None) -> list:
    from .diagnostics import check_corredi
    from .study_spec import resolve_streams
    from .yaml_loc import load as load_with_locations

    path = os.path.join(study_dir(study), "study.yml")
    data, locs = load_with_locations(path)
    # Diagnostica non fatale sul documento **grezzo**: apply_document_let
    # consuma e rimuove il blocco ``let:``, dove i corredi sono dichiarati.
    _emit(check_corredi(data, locs))
    # Manopole di documento (`let:` top-level): risolte e iniettate al load,
    # prima del parse degli stream — il riposo che versions/percorso poi muovono.
    data = apply_document_let(data, locs)
    sid = data.get("study_id") or study
    specs = resolve_streams(data, sid, locs=locs)
    if stream:
        # Match esatto (un cugino) o spread: il nome-spread 'zona_ombra_d05'
        # seleziona tutti i cugini 'zona_ombra_d05_1'..'_N'.
        pref = stream + "_"
        specs = [s for s in specs if s.stream_id == stream or s.stream_id.startswith(pref)]
        if not specs:
            print(f"[sweep] stream '{stream}' non trovata in {study}.", file=sys.stderr)
    return specs


def _write_expanded_streams(study: str, data: Dict[str, Any]) -> None:
    """Materializza il dict ``streams:`` espanso quando lo studio ha spread.

    E' lo "yaml di aiuto": ``generated/<study>/yaml/streams_expanded.yml``
    mostra gli stream generati dalle entry-spread (solo ispezione, la
    pipeline legge sempre ``study.yml``). Va chiamato dopo ``_load_specs``,
    a validazione gia' avvenuta. Scrittura incrementale come ogni YAML
    generato (mtime fermo a contenuto identico).
    """
    from .group_let import apply_group_let
    from .render import _dump
    from .spread import expand_spreads

    # Riflette le manopole di documento nel dump (no-op se gia' iniettate:
    # apply_document_let rimuove il blocco 'let:'). Post-validazione, quindi
    # gli errori di manopola sono gia' emersi con le posizioni via _load_specs.
    data = apply_document_let(data)
    streams = data.get("streams") or {}
    if not any(isinstance(e, dict) and "spread" in e for e in streams.values()):
        return
    # Stessa pre-pass di ``resolve_streams``: le manopole di gruppo alimentano
    # anche ``spread.let``/``spread.over``, quindi vanno iniettate PRIMA di
    # espandere — senza, una expr di voce che nomina una manopola di gruppo
    # esplode qui, nello yaml di sola ispezione.
    streams = apply_group_let(streams)
    out = os.path.join(gen_dir(study), "yaml")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "streams_expanded.yml")
    _dump(path, expand_spreads(streams, global_spread=data.get("spread")))
    print(f"[spread] streams espansi -> {path}")


# --- comandi ---------------------------------------------------------------

def cmd_sweep(study: str, stream: str | None = None) -> int:
    from .render import write_variants

    # Attivazione per presenza: parte solo il processo il cui blocco e'
    # definito nel documento (nessun selettore mode a scegliere tra i due).
    data = _load_data(study)
    if "sweep" not in data:
        print(f"[sweep] nessun blocco 'sweep:' in {study}/study.yml — niente da fare.")
        return 0
    specs = _load_specs(study, stream)
    if not specs:
        return 1
    _write_expanded_streams(study, data)
    out = os.path.join(gen_dir(study), "yaml", "sweep")
    # Snapshot degli mtime pre-sweep: _dump non tocca i file a contenuto
    # identico, quindi "mtime cambiato o file nuovo" = variante da rirenderizzare
    # (stesso segnale usato dal render incrementale).
    before: dict[str, float] = {}
    if os.path.isdir(out):
        for root, _, files in os.walk(out):
            for fname in files:
                p = os.path.join(root, fname)
                before[p] = os.path.getmtime(p)
    written_all: set[str] = set()
    for spec in specs:
        written = write_variants(spec, out)
        written_all.update(written)
        label = f" [{spec.stream_id}]" if spec.stream_id else ""
        dirty = {p for p in written if before.get(p) != os.path.getmtime(p)}
        for mode in ("discrete", "envelope"):
            tot = [p for p in written if (os.sep + mode + os.sep) in p]
            if not tot:
                continue
            changed = sorted(p for p in dirty if (os.sep + mode + os.sep) in p)
            if changed:
                print(f"[sweep]{label} {len(tot)} varianti {mode}, {len(changed)} da rirenderizzare:")
                for p in changed:
                    print(f"    {os.path.splitext(os.path.basename(p))[0]}")
            else:
                print(f"[sweep]{label} {len(tot)} varianti {mode}, nessuna cambiata")
        if not written:
            print(f"[sweep]{label} nessuna variante generata (mode={spec.mode})")
    _warn_orphans(out, written_all, scoped=stream is not None)
    return 0


def _warn_orphans(variants_dir: str, written: set[str], scoped: bool) -> None:
    """Segnala gli YAML in ``variants_dir`` non prodotti da questo sweep.

    Sono varianti di assi/stream rimossi da study.yml: senza avviso resterebbero
    li' per sempre (il render incrementale le salta e basta). Con ``scoped``
    (sweep di una sola stream) il controllo resta nelle cartelle toccate, per
    non flaggare le stream non rigenerate. Solo avviso, nessuna cancellazione.
    """
    if scoped:
        candidates = {os.path.dirname(p) for p in written}
    else:
        candidates = {variants_dir}
    orphans = []
    for base in candidates:
        for root, _, files in os.walk(base):
            for fname in files:
                if fname.endswith((".yml", ".yaml")):
                    path = os.path.join(root, fname)
                    if path not in written:
                        orphans.append(path)
    if orphans:
        print(
            f"[sweep] ATTENZIONE: {len(orphans)} varianti orfane "
            "(non piu' generate da study.yml):",
            file=sys.stderr,
        )
        for path in sorted(orphans):
            print(f"  {path}", file=sys.stderr)
        print(
            "  Rimuovile a mano (con i relativi audio) se non servono piu'.",
            file=sys.stderr,
        )


def cmd_stack(study: str) -> int:
    from .render import write_stack

    # Stack puro: il blocco ``versions:`` non viene esercitato qui (processo
    # proprio, ``cmd_versions``). Lo stack com'e' scritto e' l'ascolto del
    # materiale di partenza — l'istanza 0 del percorso.
    data = _load_data(study)
    if "stack" not in data:
        print(f"[stack] nessun blocco 'stack:' in {study}/study.yml — niente da fare.")
        return 0
    specs = _load_specs(study)
    if not specs:
        return 1
    _write_expanded_streams(study, data)
    out = os.path.join(gen_dir(study), "yaml")
    target = os.path.join(out, "stack", "stack.yml")
    before = os.path.getmtime(target) if os.path.exists(target) else None
    written = write_stack(specs, out, samples_dir=samples_dir(specs[0].samples_dir))
    changed = before != os.path.getmtime(written[0])
    stato = "aggiornato" if changed else "invariato"
    print(f"[stack] documento multi-stream ({len(specs)} stream, {stato}) -> {written[0]}")
    return 0


def cmd_versions(study: str) -> int:
    from .render import write_versions

    # Attivazione per presenza, come sweep e stack: versions e' un processo
    # indipendente (analisi per confronto), con sottocomando e cartella propri.
    data = _load_data(study)
    if "versions" not in data:
        print(f"[versions] nessun blocco 'versions:' in {study}/study.yml — niente da fare.")
        return 0
    # Il parse per-versione avviene DOPO l'iniezione delle variabili nei let:
    # il documento grezzo puo' essere incompleto per costruzione (variabile
    # senza default nel let), quindi niente _load_specs qui.
    from .yaml_loc import load as load_with_locations

    path = os.path.join(study_dir(study), "study.yml")
    raw, locs = load_with_locations(path)
    # Il rilievo dipende dalla combinazione quando ``versions:`` muove
    # ``spread.n`` o un corredo: si controlla ogni combinazione e si deduplica.
    from .diagnostics import check_corredi_combos

    _emit(check_corredi_combos(raw, locs))
    # Manopole di documento: il riposo va iniettato PRIMA che versions muova
    # le variabili per-combo (il movimento ombreggia il riposo, non viceversa).
    raw = apply_document_let(raw, locs)
    sid = raw.get("study_id") or study
    _write_expanded_streams(study, raw)
    out = os.path.join(gen_dir(study), "yaml")
    d = os.path.join(out, "versions")
    # Un documento per valore della variabile esterna: si aggiorna solo
    # quello che cambia (mtime fermo a contenuto identico -> il render salta).
    before = {
        p: os.path.getmtime(p)
        for p in glob.glob(os.path.join(d, "*.yml"))
    }
    written = write_versions(
        raw, sid, out, locs=locs, samples_dir=samples_dir(raw.get("samples_dir"))
    )
    changed = sum(
        1 for p in written if before.get(p) != os.path.getmtime(p)
    )
    print(
        f"[versions] {len(written)} documenti ({changed} aggiornati) -> {d}"
    )
    return 0


def cmd_percorso(study: str) -> int:
    from .render import write_percorso

    # Attivazione per presenza, come gli altri processi: percorso e' il
    # quarto, indipendente (composizione per orchestrazione temporale).
    data = _load_data(study)
    if "percorso" not in data:
        print(f"[percorso] nessun blocco 'percorso:' in {study}/study.yml — niente da fare.")
        return 0
    # Come versions: il parse per-istanza avviene DOPO l'iniezione delle
    # traiettorie nei let, quindi niente _load_specs sul documento grezzo.
    from .yaml_loc import load as load_with_locations

    path = os.path.join(study_dir(study), "study.yml")
    raw, locs = load_with_locations(path)
    from .diagnostics import check_corredi

    _emit(check_corredi(raw, locs))
    # Manopole di documento: il riposo va iniettato PRIMA che il percorso muova
    # le traiettorie nei let (il movimento ombreggia il riposo, non viceversa).
    raw = apply_document_let(raw, locs)
    sid = raw.get("study_id") or study
    _write_expanded_streams(study, raw)
    out = os.path.join(gen_dir(study), "yaml")
    target = os.path.join(out, "percorso", "percorso.yml")
    before = os.path.getmtime(target) if os.path.exists(target) else None
    written = write_percorso(
        raw, sid, out, locs=locs, samples_dir=samples_dir(raw.get("samples_dir"))
    )
    changed = before != os.path.getmtime(written[0])
    stato = "aggiornato" if changed else "invariato"
    print(f"[percorso] documento percorso ({stato}) -> {written[0]}")
    return 0


def cmd_render(
    study: str, no_score: bool, force: bool = False, jobs: int | None = None,
    stem: bool = False, cache: bool = False, cache_dir: str | None = None,
) -> int:
    from .render import render_variants

    spec = _load_spec(study)
    g = gen_dir(study)
    if take_label():
        print(f"[render] modalita' take attiva: niente sovrascrittura, "
              f"l'output va in {os.path.relpath(g, REPO_ROOT)}")
    # Il render e' generico: discende yaml/ ricorsivamente (sweep/, stack/,
    # versions/, percorso/) e rispecchia i sotto-path sotto audio/ e score/.
    variant_dir = os.path.join(g, "yaml")
    if not os.path.isdir(variant_dir):
        print(f"[render] nessuno YAML: esegui prima 'sweep {study}', 'stack {study}', 'versions {study}' o 'percorso {study}'.", file=sys.stderr)
        return 1
    t0 = time.perf_counter()
    manifest = render_variants(
        variant_dir=variant_dir,
        audio_dir=os.path.join(g, "audio"),
        score_dir=None if no_score else os.path.join(g, "score"),
        samples_dir=samples_dir(spec.samples_dir),
        force=force,
        jobs=jobs,
        per_stream=stem,
        use_cache=cache,
        cache_dir=cache_dir or os.path.join(g, "cache"),
        study=study,
    )
    elapsed = time.perf_counter() - t0
    tempo = f"{elapsed:.1f}s" if elapsed < 60 else f"{int(elapsed // 60)}m{elapsed % 60:04.1f}s"
    skipped = sum(1 for e in manifest if e["skipped"])
    done = len(manifest) - skipped
    print(f"[render] {done} varianti renderizzate, {skipped} saltate (aggiornate) in {tempo} -> {g}")
    # Snapshot dello study.yml che ha prodotto questo audio. Riscritto a ogni
    # render (non alla creazione della take): cosi' e' sempre lo stato vero,
    # qualunque sia l'ordine in cui si modifica e si rigenera. E' il termine di
    # paragone del diff in ``make takes`` e del check di ``make take``.
    shutil.copy2(os.path.join(study_dir(study), "study.yml"), os.path.join(g, "study.yml"))
    return 0


def cmd_describe(study: str) -> int:
    from .curation import update_results_file
    from .sweep import generate_discrete_variants

    spec = _load_spec(study)
    g = gen_dir(study)
    # La curation lavora solo sulle varianti discrete dello sweep: l'audio sta
    # in ``audio/sweep/discrete/``; fallback sui layout precedenti
    # (``audio/discrete/``, flat) per output non ancora rigenerati.
    audio_dir = os.path.join(g, "audio", "sweep", "discrete")
    if not os.path.isdir(audio_dir):
        audio_dir = os.path.join(g, "audio", "discrete")
    if not os.path.isdir(audio_dir):
        audio_dir = os.path.join(g, "audio")
    if not os.path.isdir(audio_dir):
        print(f"[describe] nessun audio: esegui prima 'render {study}'.", file=sys.stderr)
        return 1
    params_by_name = {
        v.name: v.overrides(spec) for v in generate_discrete_variants(spec)
    }
    results_path = os.path.join(g, "results.yml")
    merged = update_results_file(results_path, audio_dir, params_by_name=params_by_name)
    print(f"[describe] {len(merged)} entry in {results_path}")
    return 0


def cmd_matrix(study: str, threshold: float) -> int:
    from .states import load_states
    from .kinship import kinship_matrix, adjacency, Weights

    states = load_states(os.path.join(study_dir(study), "states.yml"))
    kin = kinship_matrix(states, Weights())
    adj = adjacency(states, kin, threshold)
    g = gen_dir(study)
    os.makedirs(g, exist_ok=True)
    out = os.path.join(g, "kinship.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"threshold": threshold, **kin, "adjacency": adj}, fh, indent=2, ensure_ascii=False)
    print(f"[matrix] kinship di {len(states)} stati -> {out}")
    return 0


def _build_steps(study: str, comp: Dict[str, Any], states):
    from .kinship import kinship_matrix, adjacency, Weights
    from .walk import random_walk, authored_path

    mode = comp.get("mode", "walk")
    if mode == "path":
        return authored_path(states, comp["path"])
    threshold = float(comp.get("threshold", 0.5))
    kin = kinship_matrix(states, Weights())
    adj = adjacency(states, kin, threshold)
    return random_walk(
        states,
        adj,
        start=comp["start"],
        steps=int(comp.get("steps", len(states))),
        seed=int(comp.get("seed", 0)),
    )


def cmd_compose(study: str, seed: int | None, steps: int | None, start: str | None) -> int:
    from .states import load_states
    from .compose import compose_document

    spec = _load_spec(study)
    states = load_states(os.path.join(study_dir(study), "states.yml"))

    comp_path = os.path.join(study_dir(study), "composition.yml")
    if os.path.exists(comp_path):
        with open(comp_path, "r", encoding="utf-8") as fh:
            comp = yaml.safe_load(fh) or {}
    else:
        comp = {"mode": "walk"}
    # gli argomenti CLI hanno la precedenza
    if seed is not None:
        comp["seed"] = seed
    if steps is not None:
        comp["steps"] = steps
    if start is not None:
        comp["start"] = start
    if comp.get("mode", "walk") == "walk" and "start" not in comp:
        comp["start"] = states[0].id

    step_list = _build_steps(study, comp, states)
    doc = compose_document(
        step_list, states, spec.base, title=f"{study} :: composition", seed=spec.seed
    )
    g = gen_dir(study)
    os.makedirs(g, exist_ok=True)
    out = os.path.join(g, "final.yml")
    with open(out, "w", encoding="utf-8") as fh:
        yaml.safe_dump(doc, fh, sort_keys=False, allow_unicode=True)
    print(f"[compose] percorso di {len(step_list)} tappe -> {out}")
    return 0


def _cmd_sv_document(study: str, g: str, layout: str, total: list, process: str,
                     axis_paths: list | None = None) -> None:
    """Emette i .sv dei documenti multi-stream di un processo (``stack``/
    ``versions``/``percorso``): per ogni documento uno contro il mix, uno
    contro gli stem. Ogni processo vive nella propria cartella; ``versions``
    ci mette piu' documenti (uno per valore della variabile esterna), stack e
    percorso uno solo. Il prefisso degli stem e' il **basename** del
    documento (``versions__d=3__<stream>.aif``), non il nome del processo."""
    from .sv_export import stack_to_sv, stack_stems_to_sv

    variants = sorted(glob.glob(os.path.join(g, "yaml", process, "*.yml")))
    if not variants:
        print(f"[sv] nessun documento {process}: esegui prima '{process}'.", file=sys.stderr)
        return
    audio_dir = os.path.join(g, "audio", process)
    for variant in variants:
        base = os.path.splitext(os.path.basename(variant))[0]
        audio = os.path.join(audio_dir, f"{base}.aif")
        if not os.path.exists(audio):
            print(f"[sv] audio {base} mancante: esegui prima 'render'.", file=sys.stderr)
            continue
        suffix = f"_{layout}" if layout == "single" else ""
        out = os.path.join(g, "sv", process, f"{study}_{base}" + suffix + ".sv")
        stack_to_sv(variant, audio, out, layout=layout, axis_paths=axis_paths)
        total.append(out)
        print(f"[sv] {out}")

        # Un pane per stem (audio separato per stream): richiede 'render --stem'.
        stems_out = os.path.join(g, "sv", process, f"{study}_{base}_stems.sv")
        if stack_stems_to_sv(variant, audio_dir, stems_out, process=base,
                             axis_paths=axis_paths):
            total.append(stems_out)
            print(f"[sv] {stems_out}")


def cmd_sv(study: str, layout: str, markers: bool = True, stream: str | None = None,
           markers_scope: str = "all") -> int:
    from .sv_export import variant_to_sv

    data = _load_data(study)
    g = gen_dir(study)
    total: list = []

    # Processi multi-stream (stack, versions, percorso): un .sv per documento,
    # contro il suo audio sommato. Attivi per presenza del blocco (come i
    # rispettivi comandi); i flag marker/scope restano sul solo ramo sweep
    # (i marker sono plateau-di-sweep).
    if stream is None:
        processes = ("stack", "versions", "percorso")
        # I path degli assi: servono a disegnare anche gli assi *statici*
        # (numero nudo nello stream, nessun envelope) come retta a due punti.
        axis_paths = [ax.path for ax in _load_spec(study).axes]
        for process in processes:
            if process in data:
                _cmd_sv_document(study, g, layout, total, process, axis_paths)
        if any(p in data for p in processes) and "sweep" not in data:
            print(f"[sv] {len(total)} sessioni totali")
            return 0

    specs = _load_specs(study, stream)
    if not specs:
        return 1
    for spec in specs:
        sub = spec.stream_id or ""
        variant_dir = os.path.join(g, "yaml", "sweep", "envelope", sub) if sub else os.path.join(g, "yaml", "sweep", "envelope")
        audio_dir = os.path.join(g, "audio", "sweep", "envelope", sub) if sub else os.path.join(g, "audio", "sweep", "envelope")
        sv_dir = os.path.join(g, "sv", "sweep", "envelope", sub) if sub else os.path.join(g, "sv", "sweep", "envelope")

        if not os.path.isdir(variant_dir):
            print(f"[sv] [{sub or 'default'}] nessuna variante envelope: esegui prima 'sweep {study}'.", file=sys.stderr)
            continue
        if not os.path.isdir(audio_dir):
            print(f"[sv] [{sub or 'default'}] nessun audio envelope: esegui prima 'render {study}'.", file=sys.stderr)
            continue

        for fname in sorted(os.listdir(variant_dir)):
            if not fname.endswith(".yml"):
                continue
            variant_name = fname[:-4]
            # Il basename include lo studio (per distinguerlo aprendo piu' .sv
            # in Sonic Visualiser) e lo stream (per distinguere i file in SV).
            basename = f"{study}_{sub}_{variant_name}" if sub else f"{study}_{variant_name}"
            audio = os.path.join(audio_dir, basename + ".aif")
            if not os.path.exists(audio):
                print(f"[sv] {basename}: audio mancante, salto.", file=sys.stderr)
                continue
            suffix = f"_{layout}" if layout == "single" else ""
            out = os.path.join(sv_dir, basename + suffix + ".sv")
            variant_to_sv(os.path.join(variant_dir, fname), audio, out,
                          layout=layout, markers=markers, markers_scope=markers_scope)
            total.append(out)
            print(f"[sv] {out}")

    print(f"[sv] {len(total)} sessioni totali")
    return 0


def cmd_render_final(study: str) -> int:
    from . import engine_bridge

    spec = _load_spec(study)
    g = gen_dir(study)
    final_yaml = os.path.join(g, "final.yml")
    if not os.path.exists(final_yaml):
        print(f"[render-final] manca final.yml: esegui prima 'compose {study}'.", file=sys.stderr)
        return 1
    audio = os.path.join(g, "final.aif")
    sdir = samples_dir(spec.samples_dir)
    engine_bridge.render(final_yaml, audio, samples_dir=sdir)
    print(f"[render-final] {audio}")
    return 0


def cmd_where(study: str) -> int:
    """Stampa la cartella di output corrente, nient'altro.

    E' l'unica fonte di verita' sulla risoluzione di ``TAKE``: la funzione
    ``study`` in ``.zsh_completions/_study`` la interroga invece di
    ricostruirsi il path in zsh, cosi' la regola vive in un posto solo.
    """
    print(gen_dir(study))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="granstudies", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("sweep", help="genera le varianti YAML")
    sp.add_argument("study")
    sp.add_argument("--stream", default=None, help="genera solo questa stream (default: tutte)")

    stp = sub.add_parser("stack", help="genera il documento multi-stream (stack)")
    stp.add_argument("study")

    vp = sub.add_parser("versions", help="genera il documento delle versioni (prodotto cartesiano)")
    vp.add_argument("study")

    pp = sub.add_parser("percorso", help="genera il documento del percorso (orchestrazione temporale)")
    pp.add_argument("study")

    rp = sub.add_parser("render", help="renderizza audio + partitura")
    rp.add_argument("study")
    rp.add_argument("--no-score", action="store_true", help="salta i PDF di partitura")
    rp.add_argument("--force", action="store_true",
                    help="rirenderizza anche le varianti gia' aggiornate")
    rp.add_argument("--stem", "--per-stream", dest="stem", action="store_true", default=True,
                    help="STEMS mode oltre al mix: un file audio anche per stream (default: attivo)")
    rp.add_argument("--no-stem", "--no-per-stream", dest="stem", action="store_false",
                    help="disattiva la pass STEMS, genera solo il mix")
    rp.add_argument("--cache", action="store_true", default=True,
                    help="caching incrementale per-stream dell'engine (default: attivo, con --stem)")
    rp.add_argument("--no-cache", dest="cache", action="store_false",
                    help="disattiva il caching incrementale per gli stem")
    rp.add_argument("--cache-dir", default=None,
                    help="directory manifest cache (default: <study>/generated/cache)")
    rp.add_argument("--jobs", type=int, default=None,
                    help="budget totale di processi, ripartito tra varianti in "
                         "parallelo e core per singolo render (default: min(8, cpu))")

    dp = sub.add_parser("describe", help="descrittori + results.yml")
    dp.add_argument("study")

    mp = sub.add_parser("matrix", help="matrice di parentela")
    mp.add_argument("study")
    mp.add_argument("--threshold", type=float, default=0.5)

    cp = sub.add_parser("compose", help="genera final.yml")
    cp.add_argument("study")
    cp.add_argument("--seed", type=int, default=None)
    cp.add_argument("--steps", type=int, default=None)
    cp.add_argument("--start", type=str, default=None)

    fp = sub.add_parser("render-final", help="renderizza il brano finale")
    fp.add_argument("study")

    wp = sub.add_parser("where", help="stampa la cartella di output corrente")
    wp.add_argument("study")

    svp = sub.add_parser("sv", help="genera sessioni .sv per Sonic Visualiser")
    svp.add_argument("study")
    svp.add_argument("--layout", choices=["multi", "single"], default="multi",
                     help="multi: un pannello per parametro (default); single: tutti in un pannello")
    svp.add_argument("--no-markers", action="store_true",
                     help="non emette i marker di inizio plateau (confini degli stati)")
    svp.add_argument("--markers-scope", choices=["all", "waveform"], default="waveform",
                     help="waveform: marker solo nel pane della forma d'onda (default); all: marker in ogni pane")
    svp.add_argument("--stream", default=None, help="genera sv solo per questa stream (default: tutte)")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (SpecError, yaml.YAMLError):
        # Con GRANSTUDIES_DEBUG=1 il traceback completo torna utile (sviluppo);
        # altrimenti l'errore esce come blocco leggibile, senza stack Python.
        if os.environ.get("GRANSTUDIES_DEBUG"):
            raise
        return _report_error(args)


def _report_error(args) -> int:
    """Stampa l'errore corrente in forma leggibile su stderr. Exit code 2."""
    e = sys.exc_info()[1]
    study = getattr(args, "study", None)
    intro = f"[granstudies] errore nello studio '{study}'" if study else "[granstudies] errore"
    if isinstance(e, SpecError):
        print(f"{intro}\n\n{e.format_block()}\n", file=sys.stderr)
    else:  # yaml.YAMLError: i mark di posizione li porta gia' con se'
        print(f"{intro}: YAML non valido\n\n  {e}\n", file=sys.stderr)
    print("  (traceback completo con GRANSTUDIES_DEBUG=1)", file=sys.stderr)
    return 2


def _dispatch(args) -> int:
    if args.command == "sweep":
        return cmd_sweep(args.study, args.stream)
    if args.command == "stack":
        return cmd_stack(args.study)
    if args.command == "versions":
        return cmd_versions(args.study)
    if args.command == "percorso":
        return cmd_percorso(args.study)
    if args.command == "render":
        return cmd_render(args.study, args.no_score, args.force, args.jobs,
                          args.stem, args.cache, args.cache_dir)
    if args.command == "describe":
        return cmd_describe(args.study)
    if args.command == "matrix":
        return cmd_matrix(args.study, args.threshold)
    if args.command == "compose":
        return cmd_compose(args.study, args.seed, args.steps, args.start)
    if args.command == "render-final":
        return cmd_render_final(args.study)
    if args.command == "where":
        return cmd_where(args.study)
    if args.command == "sv":
        return cmd_sv(args.study, args.layout, markers=not args.no_markers, stream=args.stream,
                      markers_scope=args.markers_scope)
    return 1


if __name__ == "__main__":
    sys.exit(main())
