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
    granstudies where    STUDY      stampa le cartelle di output correnti

STUDY e' il nome della cartella sotto ``studies/`` (es. base).

Con un blocco ``for_each:`` ogni comando gira una volta **per combinazione**
(vedi ``granstudies.for_each``): il documento viene patchato e l'output va in
``generated/<study>/<label>/``. L'env ``COMBO`` restringe il giro a una sola
combinazione, per non rirenderizzare sei varianti da venti minuti per
sentirne una.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from typing import Any, Dict

import yaml

from . import for_each
from .document_let import apply_document_let
from .engine_bridge import REPO_ROOT
from .errors import SpecError


# --- layout dei path -------------------------------------------------------

def study_dir(study: str) -> str:
    return os.path.join(REPO_ROOT, "studies", study)


# Combinazione corrente: la imposta ``_dispatch``, che gira il comando una volta
# per ogni combinazione dichiarata in ``for_each:``. E' un contesto di processo,
# non un parametro: i ``cmd_*`` non sanno che esistono gli assi esterni, e i due
# punti che li vedono sono ``gen_dir`` (dove si scrive) e ``_read_study`` (cosa
# si legge).
_COMBO: for_each.Combo = for_each.EMPTY


def combo() -> for_each.Combo:
    return _COMBO


def gen_dir(study: str) -> str:
    """Cartella di output dello studio, per la combinazione corrente.

    Senza ``for_each:`` (o con la combinazione vuota) e' ``generated/<study>/``,
    identica a uno studio senza assi esterni; con gli assi esterni scende di un
    livello, ``generated/<study>/<label>/``, e sotto ha lo stesso albero
    (``yaml/``, ``audio/``, ``sv/``, ``cache/``, ``score/``).
    """
    parts = [REPO_ROOT, "generated", study]
    if _COMBO.label:
        parts.append(_COMBO.label)
    return os.path.join(*parts)


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


def _read_study(study: str) -> tuple[Dict[str, Any], Any]:
    """Il documento dello studio, patchato con la combinazione corrente.

    E' l'unico punto in cui ``study.yml`` viene letto: da qui in giu' il
    documento e' uno studio normale, senza blocco ``for_each:``. Le posizioni
    restano quelle del file sorgente — una chiave patchata riporta la riga
    dov'e' dichiarata nel documento, non quella dell'asse esterno che l'ha
    mossa, ed e' comunque il posto giusto dove andare a guardare.
    """
    from .yaml_loc import load as load_with_locations

    raw, locs = load_with_locations(os.path.join(study_dir(study), "study.yml"))
    return for_each.apply(raw, _COMBO, locs), locs


def _load_data(study: str) -> Dict[str, Any]:
    return _read_study(study)[0]


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

    data, locs = _read_study(study)
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
    raw, locs = _read_study(study)
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
    raw, locs = _read_study(study)
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
    # Snapshot dello study.yml che ha prodotto questo audio, riscritto a ogni
    # render: e' il documento **patchato**, quindi dice da se' i valori della
    # combinazione invece di rimandare al blocco ``for_each:``. Con la
    # combinazione vuota e' una copia dello study.yml.
    with open(os.path.join(g, "study.yml"), "w", encoding="utf-8") as fh:
        yaml.safe_dump(_read_study(study)[0], fh, sort_keys=False, allow_unicode=True)
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


def sv_combo_suffix() -> str:
    """Suffisso del basename dei ``.sv`` quando lo studio ha assi esterni.

    Sonic Visualiser identifica una sessione dal nome del file: due
    combinazioni dello stesso studio producono ``.sv`` omonimi, e se una e' gia'
    aperta l'altra non si apre — proprio il confronto fra combinazioni, che e' il
    motivo per cui esistono. La label le distingue.
    """
    return f"__{_COMBO.label}" if _COMBO.label else ""


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
        suffix = (f"_{layout}" if layout == "single" else "") + sv_combo_suffix()
        out = os.path.join(g, "sv", process, f"{study}_{base}" + suffix + ".sv")
        stack_to_sv(variant, audio, out, layout=layout, axis_paths=axis_paths)
        total.append(out)
        print(f"[sv] {out}")

        # Un pane per stem (audio separato per stream): richiede 'render --stem'.
        stems_out = os.path.join(
            g, "sv", process, f"{study}_{base}_stems" + sv_combo_suffix() + ".sv")
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
            # ponytail: l'export SV vive sul ramo envelope (i marker sono i
            # plateau dello sweep). In `mode: discrete` non c'e' niente da
            # marcare per variante: la navigazione e' `graph`. Se servira' un
            # .sv anche per i file discreti, e' qui che va aggiunto il ramo.
            if _load_spec(study).mode == "discrete":
                print(f"[sv] [{sub or 'default'}] lo studio e' in 'mode: discrete': "
                      f"l'export SV copre le varianti envelope. Per navigare i file "
                      f"discreti usa 'graph {study}'.", file=sys.stderr)
            else:
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
            # in Sonic Visualiser) e lo stream (per distinguere i file in SV);
            # con gli assi esterni ci si aggiunge la label della combinazione,
            # ragione (vedi ``sv_combo_suffix``). L'audio resta senza: il suo
            # nome lo cerca ``cmd_sv``, ed e' gia' unico per cartella.
            basename = f"{study}_{sub}_{variant_name}" if sub else f"{study}_{variant_name}"
            audio = os.path.join(audio_dir, basename + ".aif")
            if not os.path.exists(audio):
                print(f"[sv] {basename}: audio mancante, salto.", file=sys.stderr)
                continue
            suffix = (f"_{layout}" if layout == "single" else "") + sv_combo_suffix()
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


def cmd_graph(study: str) -> int:
    """Scrive la rete navigabile delle varianti discrete: una pagina per studio.

    Legge i nomi dei file audio, non lo YAML: le coordinate sono gia' nel nome
    (``o2__grain.duration=0.001__pitch.ratio=0.447``) e cosi' la pagina mostra
    esattamente cio' che e' stato renderizzato, non cio' che sarebbe da
    renderizzare. Per la stessa ragione gira **una volta sola** e non una per
    combinazione (vedi ``_dispatch``): gli assi esterni sono selettori dentro
    la pagina, non file diversi, e ``COMBO`` ha gia' fatto il suo filtro a
    monte decidendo cosa renderizzare.
    """
    from .graph import write_graph

    gen_root = os.path.join(REPO_ROOT, "generated", study)
    out = os.path.join(gen_root, "graph.html")
    n_combos, n_nodes = write_graph(study, gen_root, out, _axis_orders(study))
    if not n_combos:
        print(f"[graph] nessun audio discrete in {gen_root}: esegui prima "
              f"'render {study}' (serve sweep.mode: discrete).", file=sys.stderr)
        return 1
    print(f"[graph] {out}  ({n_nodes} nodi in {n_combos} combinazioni)")
    return 0


def _axis_orders(study: str) -> dict:
    """label -> ordine degli assi dello spec, una voce per combinazione.

    Con ``for_each:`` gli assi interni li dichiara la combinazione, quindi lo
    spec del documento base puo' non averne nessuno: si carica uno spec per
    label, impostando il contesto come fa ``_dispatch``. Le combinazioni che
    non caricano (studio a meta', spec invalido) si saltano — al massimo la
    griglia esce con gli assi in ordine alfabetico.
    """
    global _COMBO
    was = _COMBO
    orders = {}
    try:
        for c in _combos(study):
            _COMBO = c
            try:
                orders[c.label] = [ax.name for ax in _load_spec(study).axes]
            except (SpecError, yaml.YAMLError):
                continue
    finally:
        _COMBO = was
    return orders


def cmd_where(study: str) -> int:
    """Stampa la cartella di output della combinazione corrente, nient'altro.

    Girando dentro il loop delle combinazioni ne stampa una per riga, filtro
    ``COMBO`` compreso: e' l'unica fonte di verita' su dove si scrive, e la
    funzione ``study`` in ``.zsh_completions/_study`` la interroga invece di
    ricostruirsi i path in zsh.
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

    gp = sub.add_parser("graph", help="rete navigabile delle varianti discrete (HTML)")
    gp.add_argument("study")

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


def _combos(study: str) -> list:
    """Le combinazioni da girare: quelle dichiarate, ristrette da ``COMBO``.

    ``COMBO`` e' un filtro di sessione, non un interruttore di modalita': senza,
    si fa tutto. Serve a non rirenderizzare decine di varianti da venti minuti
    per sentirne una, e a non aprire decine di sessioni di Sonic Visualiser
    insieme.
    """
    from .yaml_loc import load as load_with_locations

    path = os.path.join(study_dir(study), "study.yml")
    if not os.path.isfile(path):
        return [for_each.EMPTY]          # l'errore lo da' il comando, con contesto
    raw, locs = load_with_locations(path)
    combos = for_each.parse(raw, locs)
    voluta = os.environ.get("COMBO", "").strip()
    if not voluta:
        return combos
    # Filtro per **fetta**, non per combinazione singola: i vincoli sono
    # segmenti di label (``distribution=0.3``), e passa chi li contiene tutti.
    # Con quattro assi esterni le combinazioni sono decine e la label intera e'
    # lunga da scrivere, mentre la domanda vera e' quasi sempre parziale —
    # "tutte le dispersioni a distribution 0.3". Il match e' per segmento
    # intero, quindi ``distribution=0`` non prende ``distribution=0.3``.
    vincoli = [v for v in voluta.split("__") if v]
    scelte = [c for c in combos if set(vincoli) <= set(c.label.split("__"))]
    if not scelte:
        disponibili = "\n  ".join(c.label for c in combos if c.label) or "nessuna"
        raise SpecError(
            f"COMBO='{voluta}' non seleziona nessuna combinazione di '{study}'.",
            key=(for_each.BLOCK,),
            hint=f"i vincoli sono segmenti di label, in and fra loro. "
                 f"Combinazioni dichiarate:\n  {disponibili}\n"
                 "Togli COMBO dall'ambiente per girarle tutte.",
            source=path,
        )
    return scelte


def _dispatch(args) -> int:
    """Esegue il comando una volta per combinazione di ``for_each:``.

    Il loop sta qui e non nei ``cmd_*``: la combinazione e' un contesto (dove si
    scrive, cosa si legge), non un argomento che dodici comandi dovrebbero
    passarsi. ``make sweep`` e ``make render`` sono processi distinti e rifanno
    il giro ognuno per conto suo — combacia perche' le combinazioni si leggono
    dallo stesso ``study.yml``, non da uno stato per sessione.
    """
    global _COMBO
    # ``graph`` guarda tutto l'output dello studio in un colpo solo: girarlo per
    # combinazione riscriverebbe la stessa pagina N volte.
    if args.command == "graph" or not getattr(args, "study", None):
        combos = [for_each.EMPTY]
    else:
        combos = _combos(args.study)
    rc = 0
    try:
        for i, c in enumerate(combos, 1):
            _COMBO = c
            if c.label and args.command != "where":
                print(f"[for_each] {c.label}  ({i}/{len(combos)})")
            rc = _run(args) or rc
    finally:
        _COMBO = for_each.EMPTY
    return rc


def _run(args) -> int:
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
    if args.command == "graph":
        return cmd_graph(args.study)
    if args.command == "where":
        return cmd_where(args.study)
    if args.command == "sv":
        return cmd_sv(args.study, args.layout, markers=not args.no_markers, stream=args.stream,
                      markers_scope=args.markers_scope)
    return 1


if __name__ == "__main__":
    sys.exit(main())
