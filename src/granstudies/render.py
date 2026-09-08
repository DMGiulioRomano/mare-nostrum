"""Batch: scrittura varianti YAML e rendering audio + partitura PDF.

Le due responsabilita' sono separate apposta: ``write_variants`` materializza
gli YAML (che l'utente puo' ispezionare/modificare a mano), ``render_variants``
li renderizza in audio e partitura. Cosi' il loop di studio resta trasparente.
"""
from __future__ import annotations

import glob
import os
import warnings
from typing import Any, Dict, List

import yaml

from . import engine_bridge
from .study_spec import StudySpec
from .sweep import generate_discrete_variants
from .envelope_sweep import EnvelopeVariant, generate_envelope_variants
from .stack import generate_stack_document
from .yaml_builder import build_document


class _Dumper(yaml.SafeDumper):
    pass


def _list_representer(dumper: yaml.SafeDumper, data: list) -> yaml.Node:
    flow = bool(data and isinstance(data[0], list))
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


_Dumper.add_representer(list, _list_representer)


def _dump(path: str, doc: Dict[str, Any]) -> None:
    """Scrive lo YAML solo se il contenuto e' cambiato.

    L'mtime del file resta fermo quando la variante e' identica: e' il segnale
    che ``render_variants`` usa per saltare i render gia' aggiornati.
    """
    text = yaml.dump(doc, Dumper=_Dumper, sort_keys=False, allow_unicode=True)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            if fh.read() == text:
                return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _write_discrete(spec: StudySpec, out_dir: str, *, output_sr: int = 48000) -> List[str]:
    """Scrive le varianti statiche (una per combinazione) in ``out_dir``."""
    variants = generate_discrete_variants(spec)
    if variants and spec.duration is None and "duration" not in spec.base:
        warnings.warn(
            "mode discrete/both senza 'base.duration': i file discrete non "
            "avranno durata definita."
        )
    os.makedirs(out_dir, exist_ok=True)
    written: List[str] = []
    for v in variants:
        path = os.path.join(out_dir, f"{v.name}.yml")
        _dump(path, v.to_document(spec, output_sr=output_sr))
        written.append(path)
    return written


def _envelope_document(
    spec: StudySpec, ev: EnvelopeVariant, *, output_sr: int = 48000
) -> Dict[str, Any]:
    """Documento YAML di un ``EnvelopeVariant``: stream dinamico normalizzato.

    La ``base.duration`` statica (valida solo per i file discrete) viene
    sostituita dalla durata *calcolata* da ``plateau``/``transition``: e' anche
    il fattore che scala i tempi normalizzati degli envelope. Tutti i file
    envelope girano in ``time_mode: normalized`` e gli assi mossi diventano
    envelope.
    """
    duration = ev.duration(spec)
    base = dict(spec.base)
    base.setdefault("stream_id", "stream")
    base["time_mode"] = "normalized"
    base["duration"] = duration
    return build_document(
        base,
        ev.overrides(spec, output_sr=output_sr),
        title=f"{spec.study_id} :: {ev.name}",
        seed=spec.seed,
        duration=duration,
        envelope_time_mode="normalized",
        envelope_types=ev.envelope_types(spec),
    )


def _write_envelope(spec: StudySpec, out_dir: str, *, output_sr: int = 48000) -> List[str]:
    """Scrive le varianti envelope (una per combinazione di assi) in ``out_dir``."""
    variants = generate_envelope_variants(spec)
    os.makedirs(out_dir, exist_ok=True)
    written: List[str] = []
    for ev in variants:
        path = os.path.join(out_dir, f"{ev.name}.yml")
        _dump(path, _envelope_document(spec, ev, output_sr=output_sr))
        written.append(path)
    return written


def write_stack(
    specs: List[StudySpec],
    out_dir: str,
    *,
    output_sr: int = 48000,
    samples_dir: str | None = None,
) -> List[str]:
    """Scrive il documento multi-stream del processo stack.

    Un solo file (``out_dir/stack/stack.yml``): stack collassa gli stream, non
    enumera varianti. Stessa scrittura incrementale di ``_dump`` (mtime fermo a
    contenuto identico -> il render salta i documenti gia' aggiornati).
    ``output_sr`` deve combaciare con quello usato in ``render_variants``,
    altrimenti il floor di ``grain.duration`` clampato qui non e' quello che
    l'engine applichera' in render.
    """
    doc = generate_stack_document(
        specs, output_sr=output_sr, samples_dir=samples_dir
    )
    d = os.path.join(out_dir, "stack")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "stack.yml")
    _dump(path, doc)
    return [path]


def write_versions(
    data: dict,
    study_id: str,
    out_dir: str,
    *,
    locs=None,
    output_sr: int = 48000,
    samples_dir: str | None = None,
) -> List[str]:
    """Scrive i documenti delle versioni (blocco ``versions:``).

    Cartella propria del processo (``out_dir/versions/``): versions e' un
    processo indipendente come sweep e stack — ``yaml/stack/stack.yml`` resta
    il materiale com'e' scritto, senza repliche. Riceve il documento *grezzo*
    (non gli spec): il parse per-versione avviene dopo l'iniezione delle
    variabili negli scope let.

    Un file per valore della variabile esterna (``versions__d=3.yml``, v.
    ``generate_versions_documents``): il prodotto cartesiano intero in un
    documento solo diventa un audio da decine di minuti che nessun visualizer
    apre volentieri. I file di una run precedente che non appartengono piu'
    alla griglia vengono rimossi, altrimenti il render continuerebbe a
    trascinarseli.
    """
    from .versions import generate_versions_documents

    docs = generate_versions_documents(
        data, study_id, locs, output_sr=output_sr, samples_dir=samples_dir
    )
    d = os.path.join(out_dir, "versions")
    os.makedirs(d, exist_ok=True)
    written = []
    for label, doc in docs:
        path = os.path.join(d, f"versions__{label}.yml")
        _dump(path, doc)
        written.append(path)
    for stale in set(glob.glob(os.path.join(d, "*.yml"))) - set(written):
        os.remove(stale)
    return written


def write_percorso(
    data: dict,
    study_id: str,
    out_dir: str,
    *,
    locs=None,
    output_sr: int = 48000,
    samples_dir: str | None = None,
) -> List[str]:
    """Scrive il documento delle istanze del percorso (blocco ``percorso:``).

    File proprio del processo (``out_dir/percorso/percorso.yml``), quarto
    accanto a sweep/stack/versions. Riceve il documento *grezzo* come
    ``write_versions``: il parse per-istanza avviene dopo l'iniezione delle
    traiettorie negli scope let. Con ``samples_dir`` risolto e il blocco
    ``gain_compensation:`` presente, gli stream del percorso ricevono l'offset
    di ``volume`` (v. ``gainmap``).
    """
    from .percorso import generate_percorso_document

    doc = generate_percorso_document(
        data, study_id, locs, output_sr=output_sr, samples_dir=samples_dir
    )
    d = os.path.join(out_dir, "percorso")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "percorso.yml")
    _dump(path, doc)
    return [path]


def write_variants(spec: StudySpec, out_dir: str, *, output_sr: int = 48000) -> List[str]:
    """Genera lo sweep e scrive i file YAML in sotto-cartelle per modalita'.

    A seconda di ``spec.mode`` materializza ``out_dir/discrete/`` (varianti
    statiche), ``out_dir/envelope/`` (stream dinamici) o entrambi (``both``).

    Returns: lista dei path YAML scritti (discrete prima, poi envelope).
    """
    sub = spec.stream_id or ""
    written: List[str] = []
    if spec.mode in ("discrete", "both"):
        d = os.path.join(out_dir, "discrete", sub) if sub else os.path.join(out_dir, "discrete")
        written += _write_discrete(spec, d, output_sr=output_sr)
    if spec.mode in ("envelope", "both"):
        e = os.path.join(out_dir, "envelope", sub) if sub else os.path.join(out_dir, "envelope")
        written += _write_envelope(spec, e, output_sr=output_sr)
    return written


def merge_stems_by_base(
    yaml_path: str, mix_path: str, stem_paths: List[str]
) -> List[str]:
    """Post-merge degli stem per nome-base (issue #24).

    ``versions`` genera uno stream per combinazione (``fermo__d=1``,
    ``fermo__d=2``, ...): in STEMS mode l'engine scrive un file per ognuno e
    Sonic Visualiser finirebbe con un pane per combinazione. Qui gli stem che
    condividono il nome-base (lo ``stream_id`` prima del primo ``__``) vengono
    sommati in un unico file per voce logica via overlay-add (con clip di
    protezione): con le versioni concatenate equivale a una concatenazione,
    e con le chiavi riservate ``onset``/``duration`` di ``versions`` (issue
    #26) gestisce anche versioni sovrapposte o distanziate.

    Gli stem dell'engine hanno onset RELATIVO (il buffer parte dall'onset
    dello stream, vedi ``_relative_n_total`` nel renderer NumPy): ogni stem
    viene posizionato al proprio ``onset`` letto dal documento, e il file
    accorpato risulta ancorato al tempo 0 dello stack — niente padding a valle.

    Solo i gruppi con almeno 2 stem vengono accorpati (uno stream suffissato
    ma solo nel suo gruppo resta consumabile com'e'); gli stream senza ``__``
    nello ``stream_id`` non sono versioni e restano fuori. Uno stem suffissato
    il cui ``stream_id`` non esiste nel documento e' un errore (``ValueError``):
    un default silenzioso a onset 0 lo sommerebbe sopra audio che non deve
    coesistere nello stesso istante.

    Incrementale: il file accorpato si rigenera se uno dei suoi stem — o il
    documento stesso — e' piu' recente. Il documento fa parte del check perche'
    la composizione del gruppo deriva solo da li' (un gruppo che si riduce non
    tocca gli stem superstiti, ma riscrive lo YAML: ``_dump`` ne muove l'mtime
    a ogni cambio di contenuto).

    Returns: lista dei path accorpati (``{mix}__{base}.aif``), anche se gia'
    aggiornati; vuota se non c'e' nessun gruppo da accorpare.
    """
    with open(yaml_path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    onsets = {
        s.get("stream_id", "stream"): float(s.get("onset", 0) or 0)
        for s in doc.get("streams", [])
    }
    prefix = os.path.splitext(os.path.basename(mix_path))[0] + "__"
    groups: Dict[str, List[tuple]] = {}
    for path in stem_paths:
        name = os.path.splitext(os.path.basename(path))[0]
        if not name.startswith(prefix):
            continue
        stream_id = name[len(prefix):]
        if "__" not in stream_id:
            continue
        base_name = stream_id.split("__", 1)[0]
        if stream_id not in onsets:
            raise ValueError(
                f"merge stem: lo stream_id '{stream_id}' (da {os.path.basename(path)}) "
                f"non esiste in {yaml_path} — naming engine/YAML disallineato?"
            )
        groups.setdefault(base_name, []).append((onsets[stream_id], path))

    merged: List[str] = []
    for base_name, members in groups.items():
        if len(members) < 2:
            continue
        out_path = os.path.join(
            os.path.dirname(members[0][1]), f"{prefix}{base_name}.aif"
        )
        merged.append(out_path)
        sources = [p for _o, p in members] + [yaml_path]
        if os.path.exists(out_path) and all(
            os.path.getmtime(out_path) >= os.path.getmtime(p) for p in sources
        ):
            continue
        import numpy as np
        import soundfile as sf

        buffers = []
        sr = None
        for onset, path in members:
            data, this_sr = sf.read(path, always_2d=True)
            sr = sr or this_sr
            buffers.append((round(onset * this_sr), data))
        n_total = max(start + len(data) for start, data in buffers)
        out = np.zeros((n_total, buffers[0][1].shape[1]), dtype=np.float64)
        for start, data in buffers:
            out[start:start + len(data)] += data
        # Le versioni possono sovrapporsi (onset liberi, issue #26): il clip
        # protegge la somma dal fuori scala; il subtype degli stem sorgente si
        # conserva (stessa risoluzione dell'engine, niente quantizzazione
        # aggiuntiva).
        np.clip(out, -1.0, 1.0, out=out)
        subtype = sf.info(members[0][1]).subtype
        sf.write(out_path, out, sr, format="AIFF", subtype=subtype)
    return merged


def _render_one(
    yaml_path: str,
    audio_path: str,
    pdf_path: str | None,
    samples_dir: str,
    output_sr: int,
    per_stream: bool = False,
    use_cache: bool = False,
    cache_dir: str | None = None,
    jobs: int = 1,
) -> Dict[str, Any]:
    """Renderizza una singola variante (worker per il pool di processi).

    Il mix (``audio_path``) viene sempre prodotto: e' quello che ``sv``
    consuma (l'engine non esporta SV in modalita' stem, v1). Se
    ``per_stream``, viene fatta ANCHE una seconda pass in STEMS mode (con
    caching incrementale se ``use_cache``): doppio lavoro sull'engine, ma
    lascia intatto il resto della pipeline.

    ``jobs`` e' il parallelismo INTERNO dell'engine, che si applica a entrambe
    le pass: in MIX spezza i grani in chunk, in STEMS distribuisce gli stream
    (e con un solo stream ricade comunque sul chunk path).
    """
    mix = engine_bridge.render(
        yaml_path, audio_path, samples_dir=samples_dir, output_sr=output_sr,
        jobs=jobs,
    )
    if pdf_path:
        engine_bridge.score_pdf(yaml_path, pdf_path, samples_dir=samples_dir)
    result: Dict[str, Any] = {"audio": mix[0] if mix else audio_path}
    if per_stream:
        stems = engine_bridge.render(
            yaml_path, audio_path, samples_dir=samples_dir, output_sr=output_sr,
            per_stream=True, use_cache=use_cache, cache_dir=cache_dir,
            jobs=jobs,
        )
        result["stems"] = stems
        # Post-merge per nome-base (issue #24): le versioni di una stessa voce
        # logica vengono accorpate in un unico file, cosi' l'export SV apre un
        # pane per voce e non uno per combinazione. Gli stem originali restano.
        merged = merge_stems_by_base(yaml_path, audio_path, stems)
        if merged:
            result["stems_merged"] = merged
    return result


def _is_up_to_date(target: str, source: str) -> bool:
    return os.path.exists(target) and os.path.getmtime(target) >= os.path.getmtime(source)


def _split_jobs(budget: int, n_pending: int) -> tuple[int, int]:
    """Ripartisce ``budget`` processi tra i due livelli di parallelismo.

    Ci sono due pool annidabili: quello di ``render_variants`` (una variante
    per worker) e quello interno all'engine (chunk di grani, vedi
    ``numpy_parallel``). Con molte varianti brevi conviene tutto al primo; con
    una variante lunga sola — il caso di uno studio a un asse, dove lo sweep
    collassa in un unico file da decine di minuti — il primo pool e' degenere
    e senza questa ripartizione la macchina resterebbe ferma a un core.

    Il prodotto ``workers * engine_jobs`` non supera mai il budget, quindi i
    pool annidati non sovraccaricano la macchina.

    Returns: ``(workers, engine_jobs)``, entrambi >= 1.
    """
    workers = max(1, min(budget, n_pending))
    return workers, max(1, budget // workers)


def render_variants(
    variant_dir: str,
    audio_dir: str,
    score_dir: str | None,
    samples_dir: str,
    output_sr: int = 48000,
    force: bool = False,
    jobs: int | None = None,
    per_stream: bool = False,
    use_cache: bool = False,
    cache_dir: str | None = None,
    study: str | None = None,
) -> List[Dict[str, Any]]:
    """Renderizza ogni YAML in ``variant_dir`` -> audio (e PDF se ``score_dir``).

    Incrementale: una variante il cui audio (e PDF) e' piu' recente dello YAML
    viene saltata (``force=True`` per rirenderizzare tutto).

    ``jobs`` e' il budget TOTALE di processi (default min(8, cpu)), ripartito
    da ``_split_jobs`` tra le varianti in parallelo e il parallelismo interno
    dell'engine: con molte varianti vince il primo, con una variante lunga sola
    tutto il budget finisce all'engine invece di lasciare la macchina ferma a
    un core. ``jobs=1`` resta sequenziale su entrambi i livelli.

    ``per_stream``: STEMS mode, un file per stream invece del MIX unico —
    ``entry["audio"]`` diventa una lista di path. In questo caso il file di
    base non viene mai scritto, quindi lo skip per mtime a livello di
    variante non e' applicabile: ogni variante passa sempre dall'engine, che
    con ``use_cache=True`` applica il proprio caching incrementale
    per-stream (skip interno dei soli stream invariati, vedi
    ``StreamCacheManager``).

    Returns: manifest, una entry per variante con i path prodotti e il flag
    ``skipped``.
    """
    os.makedirs(audio_dir, exist_ok=True)
    if score_dir:
        os.makedirs(score_dir, exist_ok=True)

    # Discende ricorsivamente: ``variant_dir`` puo' contenere ``discrete/`` e
    # ``envelope/`` (vedi ``write_variants``). I sotto-path vengono rispecchiati
    # nelle cartelle audio/score, cosi' i due set restano separati.
    yaml_files: List[str] = []
    for root, _, files in os.walk(variant_dir):
        for fname in files:
            # streams_expanded.yml e' un artefatto di sola ispezione (dict
            # streams espanso da spread), non una variante da renderizzare.
            if fname == "streams_expanded.yml":
                continue
            if fname.endswith((".yml", ".yaml")):
                yaml_files.append(os.path.join(root, fname))
    yaml_files.sort()

    manifest: List[Dict[str, Any]] = []
    pending: List[tuple] = []
    for yaml_path in yaml_files:
        rel = os.path.relpath(yaml_path, variant_dir)
        name = os.path.splitext(rel)[0]
        # Se lo YAML sta in una sotto-cartella di stream della modalita'
        # (.../{discrete|envelope}/<stream_id>/<variante>), aggiungo il nome
        # dello stream al basename per distinguerli in SV. La regola e'
        # relativa alla cartella di modalita', cosi' vale sia per il layout
        # yaml/sweep/... sia per directory di varianti passate direttamente;
        # i documenti dei processi (stack/versions/percorso) restano senza
        # prefisso. Con ``study`` le varianti di modalita' prendono anche il
        # prefisso dello studio: e' il basename che ``cmd_sv`` si aspetta
        # ({study}_{stream}_{variante}), vedi PR #30.
        parts = name.split(os.sep)
        audio_basename = parts[-1]
        for i, p in enumerate(parts[:-1]):
            if p in ("discrete", "envelope"):
                if len(parts) - i >= 3:
                    audio_basename = f"{parts[-2]}_{parts[-1]}"
                if study:
                    audio_basename = f"{study}_{audio_basename}"
                break
        audio_path = os.path.join(audio_dir, *parts[:-1], audio_basename + ".aif")
        pdf_path = os.path.join(score_dir, f"{name}.pdf") if score_dir else None

        entry: Dict[str, Any] = {"name": name, "yaml": yaml_path, "audio": audio_path}
        if pdf_path:
            entry["score"] = pdf_path

        # Se e' la prima volta che questa variante passa per gli stem (nessun
        # manifest cache per lei) lo skip a mtime del mix non basta: gli stem
        # non esistono ancora anche se il mix e' aggiornato.
        stems_never_built = per_stream and not os.path.exists(
            os.path.join(cache_dir or "cache", f"{os.path.splitext(os.path.basename(yaml_path))[0]}.json")
        )
        entry["skipped"] = (
            not force
            and not stems_never_built
            and _is_up_to_date(audio_path, yaml_path)
            and (pdf_path is None or _is_up_to_date(pdf_path, yaml_path))
        )
        manifest.append(entry)
        if entry["skipped"]:
            continue
        os.makedirs(os.path.dirname(os.path.abspath(audio_path)), exist_ok=True)
        if pdf_path:
            os.makedirs(os.path.dirname(os.path.abspath(pdf_path)), exist_ok=True)
        pending.append((
            entry,
            (yaml_path, audio_path, pdf_path, samples_dir, output_sr,
             per_stream, use_cache, cache_dir),
        ))

    if pending:
        # ponytail: cap a 8 processi, una variante lunga puo' tenere in RAM
        # l'intero buffer audio; alzare con jobs= se la memoria lo consente.
        budget = jobs or min(8, os.cpu_count() or 1)
        workers, engine_jobs = _split_jobs(budget, len(pending))
        if workers == 1:
            for entry, args in pending:
                entry.update(_render_one(*args, engine_jobs))
        else:
            from concurrent.futures import ProcessPoolExecutor, as_completed

            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_render_one, *args, engine_jobs): entry
                    for entry, args in pending
                }
                for fut in as_completed(futures):
                    futures[fut].update(fut.result())
    return manifest
