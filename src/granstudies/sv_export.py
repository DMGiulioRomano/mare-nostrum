"""Genera file di sessione Sonic Visualiser (.sv) dai YAML di variante envelope.

Il file .sv prodotto apre direttamente SV con l'audio e i pannelli envelope
già configurati. Layout disponibili:
  multi  — un pannello per ogni parametro (Y scale indipendenti, default)
  single — tutti gli envelope in un pannello unico sotto la waveform

Con ``markers=True`` (default) aggiunge un layer ``timeinstants`` con un marker
all'inizio di ogni plateau (confine di stato), replicato in ogni pane come linea
verticale di riferimento e navigabile in SV con PgUp/PgDown.

Formato: XML bzip2, struttura <data><model/><dataset/><layer/></data><display><view/></display>.
"""
from __future__ import annotations

import bz2
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, List, Literal, Optional, Tuple

# Plot style per tipo di interpolazione dell'envelope.
# I valori sono gli interi dell'enum PlotStyle di TimeValueLayer (svgui),
# serializzati come stringa nell'attributo plotStyle del layer.
#   "3" = PlotLines         -> spezzata di segmenti retti tra i breakpoint
#   "7" = PlotCubicHermite  -> curva cubica monotona (Fritsch-Carlson)
#   "8" = Stepped           -> sample-and-hold, salto netto al breakpoint successivo
#   "9" = PlotPerBreakpoint -> interpolazione mista, per segmento: il layer legge
#                              il type dalla label di ogni <point> (vuota = linear)
# (7, 8 e 9 esistono solo nel fork DMGiulioRomano/svgui.)
_PLOT_STYLE_BY_TYPE = {
    "linear": "3",
    "cubic": "7",
    "step": "8",
}
_PLOT_STYLE_DEFAULT = "3"  # fallback prudente: segmenti retti
_PLOT_STYLE_PER_BREAKPOINT = "9"

# ponytail: toggle temporaneo per testare l'offset nativo del fork svcore
# (commit 9ae4debd, ReadOnlyWaveFileModel rispetta "start" come offset e
# pada gli zeri in memoria). Con GRANSTUDIES_SV_NATIVE_ONSET=1 lo stem non
# viene piu' paddato su disco: l'onset va nell'attributo "start" del <model>.
# Rimuovere questo toggle (e _padded_stem) quando il fork sara' la baseline.
_NATIVE_ONSET_OFFSET = os.environ.get("GRANSTUDIES_SV_NATIVE_ONSET") == "1"

_COLOURS = [
    ("#ff8800", "Orange"),
    ("#00ccff", "Bright Blue"),
    ("#00ff00", "Green"),
    ("#ff00ff", "Magenta"),
    ("#ffff00", "Yellow"),
]

def _param_colour(path: str, seen: dict) -> Tuple[str, str]:
    """Colore stabile per tipo di parametro (density, grain.duration, ...),
    non per indice di enumerazione: cosi' tutte le istanze di density in un
    pane condividono colore, invece di riceverne uno diverso a testa.
    """
    param = path.rsplit("/", 1)[-1]
    if param not in seen:
        seen[param] = _COLOURS[len(seen) % len(_COLOURS)]
    return seen[param]


Layout = Literal["multi", "single"]


# Derivato dalla mappa dei plot style: e' la stessa cosa detta una volta sola —
# un tipo esportabile e' un tipo che sa disegnarsi. Il vocabolario di parse vive
# in ``study_spec.VALID_INTERPOLATION``; che i due coincidano lo tiene fermo un
# test (``test_sv_export``), senza legare questo modulo al parser.
_ENVELOPE_TYPES = frozenset(_PLOT_STYLE_BY_TYPE)


def _split_point(point: List) -> Tuple[Any, Any, str]:
    """Normalizza un breakpoint del motore: [t, v] o [t, v, type] -> (t, v, label).

    Il motore (envelope.py) accetta punti a 3 elementi dove il type per-punto
    governa il segmento che parte dal punto; qui il type finisce nella label
    del <point>, il canale che TimeValueLayer::PlotPerBreakpoint legge. Punti
    a 2 elementi -> label vuota.
    """
    if len(point) == 3:
        return point[0], point[1], str(point[2])
    t, v = point
    return t, v, ""


def _layer_plot_style(points: List, env_type: str) -> str:
    """plotStyle del layer: misto se c'e' almeno un punto [t, v, type]."""
    if any(len(p) == 3 for p in points):
        return _PLOT_STYLE_PER_BREAKPOINT
    return _PLOT_STYLE_BY_TYPE.get(env_type, _PLOT_STYLE_DEFAULT)


def _find_envelopes(obj: Any, prefix: str = "") -> List[Tuple[str, List, str]]:
    """Walk ricorsivo: [(path_dotted, points, type)] per ogni envelope (linear o cubic)."""
    if isinstance(obj, dict):
        if obj.get("type") in _ENVELOPE_TYPES and "points" in obj:
            return [(prefix.lstrip("."), obj["points"], obj["type"])]
        results = []
        for k, v in obj.items():
            results.extend(_find_envelopes(v, f"{prefix}.{k}"))
        return results
    return []


def _dig(obj: Any, path: str) -> Any:
    """Valore di un path dotted (``grain.duration``) o ``None`` se assente."""
    for key in path.split("."):
        if not isinstance(obj, dict) or key not in obj:
            return None
        obj = obj[key]
    return obj


def _stream_envelopes(stream: Any,
                      axis_paths: Optional[List[str]] = None
                      ) -> List[Tuple[str, List, str]]:
    """Envelope di uno stream, piu' una retta per ogni asse *statico*.

    Un asse che non si muove nel documento e' un numero nudo nello stream
    (``density: 10.0``), non un nodo envelope: senza questo, il suo valore
    sparisce dal .sv e non e' piu' leggibile accanto agli assi mobili. Qui ogni
    path d'asse rimasto scalare produce un envelope sintetico a **due**
    breakpoint, ``[[0, v], [1, v]]``: SV disegna un segmento fra due punti, con
    un punto solo il layer resta vuoto — il secondo punto e' l'unico modo di
    vedere la retta. I tempi sono normalizzati come tutti gli altri envelope,
    quindi seguono onset/durata dello stream a valle.
    """
    found = _find_envelopes(stream)
    if not axis_paths:
        return found
    moving = {path for path, _pts, _t in found}
    for path in axis_paths:
        if path in moving:
            continue
        value = _dig(stream, path)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            found.append((path, [[0.0, value], [1.0, value]], "linear"))
    return found


def _merge_by_param(envelopes: List[Tuple[str, List, str, float, float]],
                    group: str = "") -> List[Tuple[str, List, str, float, float]]:
    """Un layer per parametro invece che per stream, dentro uno stesso pane.

    Gli stream che finiscono nello stesso pane (le versioni di una voce, i
    cugini accorpati) sono **consecutivi nel tempo**: i loro envelope dello
    stesso parametro non si sovrappongono, quindi diventano un'unica polilinea
    invece di N layer sovrapposti (uno per versione) tutti sullo stesso asse Y.

    I punti tornano con tempi gia' assoluti in secondi, percio' onset/durata
    dell'envelope risultante sono ``0.0``/``1.0``. Se le versioni hanno
    interpolazioni diverse (o portano gia' un type per-punto), il type va nella
    label di ogni punto e il layer passa a PlotPerBreakpoint.
    """
    groups: "dict[str, List[Tuple[List, str, float, float]]]" = {}
    for path, points, env_type, onset, duration in envelopes:
        param = path.rsplit("/", 1)[-1]
        groups.setdefault(param, []).append((points, env_type, onset, duration))

    out: List[Tuple[str, List, str, float, float]] = []
    for param, items in groups.items():
        items.sort(key=lambda it: it[2])
        types = {env_type for _pts, env_type, _o, _d in items}
        # Type per-punto solo se serve: quando le versioni fuse hanno
        # interpolazioni diverse, il type del layer non basta piu' e va scritto
        # nella label di ogni punto. Le label gia' presenti restano intatte.
        mixed = len(types) > 1
        merged: List = []
        prev_end: Optional[float] = None
        for points, env_type, onset, duration in items:
            # Buco fra due segmenti della stessa voce (un altro gruppo suona in
            # mezzo, o la voce tace): il parametro si chiude a zero invece di
            # essere interpolato attraverso il silenzio. Segmenti contigui
            # (onset == fine del precedente) restano una polilinea unica.
            if prev_end is not None and onset - prev_end > 1e-6:
                for t_gap in (prev_end, onset):
                    merged.append([t_gap, 0, "linear"] if mixed else [t_gap, 0])
            prev_end = onset + duration
            for point in points:
                t_norm, value, label = _split_point(point)
                t_abs = onset + t_norm * duration
                if mixed:
                    merged.append([t_abs, value, label or env_type])
                elif len(point) == 3:
                    merged.append([t_abs, value, label])
                else:
                    merged.append([t_abs, value])
        merged.sort(key=lambda p: p[0])
        name = f"{group}/{param}" if group and group != param else param
        out.append((name, merged, types.pop() if len(types) == 1 else "linear", 0.0, 1.0))
    return out


def _plateau_starts(envelopes: List[Tuple[str, List, str, float, float]]) -> List[float]:
    """Tempi normalizzati (ordinati, dedup) di inizio di ogni plateau.

    I breakpoint envelope arrivano in coppie ``[t_start, v], [t_end, v]`` per
    plateau (vedi ``envelope_sweep.envelope_breakpoints``): l'inizio di ogni
    plateau e' quindi il punto a indice pari, mentre gli indici dispari chiudono
    il plateau prima della transizione. Non ci si puo' basare sull'uguaglianza dei
    valori per riconoscerli, perche' plateau consecutivi possono condividere lo
    stesso valore su un asse (es. l'asse esterno del prodotto cartesiano resta
    fermo per piu' plateau). Gli envelope di una stessa variante condividono la
    griglia temporale, percio' i ``t_start`` coincidono: li uniamo e dedup.
    """
    starts = set()
    for _path, points, env_type, _onset, _dur in envelopes:
        # step: un solo punto per valore (nessun doppio punto plateau), ogni
        # punto e' un inizio-gradino. linear/cubic: breakpoint a coppie
        # ``t_start, t_end`` -> gli inizi sono agli indici pari.
        stride = 1 if env_type == "step" else 2
        for i in range(0, len(points), stride):
            starts.add(round(float(points[i][0]), 6))
    return sorted(starts)


def _sample_rate(audio_path: str) -> int:
    import soundfile as sf
    return sf.info(audio_path).samplerate


def _build_sv_xml(audio_path: str, sample_rate: int, duration_sec: float,
                  envelopes: List[Tuple[str, List, str, float, float]], layout: Layout,
                  markers: bool = True,
                  markers_scope: Literal["all", "waveform"] = "waveform",
                  group_marks: Optional[List[Tuple[float, str]]] = None) -> bytes:
    root = ET.Element("sv")
    data = ET.SubElement(root, "data")

    end_frame = round(duration_sec * sample_rate)

    ET.SubElement(data, "model", {
        "id": "0", "name": os.path.basename(audio_path),
        "sampleRate": str(sample_rate), "start": "0", "end": str(end_frame),
        "type": "wavefile", "file": audio_path, "mainModel": "true",
    })
    ET.SubElement(data, "playparameters", {
        "mute": "false", "pan": "0", "gain": "1", "clipId": "", "model": "0",
    })
    ET.SubElement(data, "layer", {
        "id": "1", "type": "timeruler", "name": "Ruler", "model": "0",
        "colourName": "White", "colour": "#ffffff", "darkBackground": "true",
    })
    ET.SubElement(data, "layer", {
        "id": "2", "type": "waveform", "name": "Waveform", "model": "0",
        "gain": "1", "showMeans": "1", "greyscale": "1", "channelMode": "0",
        "channel": "-1", "scale": "0", "middleLineHeight": "0.5",
        "aggressive": "0", "autoNormalize": "0", "oversampling": "1",
        "colourName": "Bright Blue", "colour": "#1e96ff", "darkBackground": "true",
    })
    # Spectrogram: finestra 8192, overlap 75% (windowHopLevel=3), tutti i canali
    # mixati, colore White on Black (colourScheme=2 in ColourMapper.cpp), scala
    # lineare in frequenza (frequencyScale=0).
    ET.SubElement(data, "layer", {
        "id": "3", "type": "spectrogram", "name": "Spectrogram", "model": "0",
        "channel": "-1",
        "windowSize": "8192", "windowHopLevel": "3",
        "colourScheme": "2", "colourRotation": "0",
        "gain": "1", "threshold": "-80",
        "minFrequency": "0", "maxFrequency": "0",
        "frequencyScale": "0", "binDisplay": "0",
        "normalizeColumns": "0", "normalizeVisibleArea": "0",
        "darkBackground": "true",
    })

    # Raggruppamento per *voce* (vedi il commento al display piu' sotto): la
    # parte del path prima di '/' tagliata al primo '__'. Dentro ogni gruppo gli
    # envelope si fondono per parametro (un layer density, un layer
    # grain.duration), invece di un layer per stream. Il raggruppamento e' qui e
    # non piu' a valle perche' il merge deve avvenire prima di creare i modelli.
    grouped: "dict[str, List[Tuple[str, List, str, float, float]]]" = {}
    for env in envelopes:
        key = env[0].split("/", 1)[0].split("__", 1)[0]
        grouped.setdefault(key, []).append(env)
    merged_groups = [_merge_by_param(envs, group=key) for key, envs in grouped.items()]

    # Modelli + dataset + layer per ogni envelope (post-merge)
    layer_ids: List[Tuple[str, str, str]] = []  # (layer_id, model_id, path)
    next_id = 4
    param_colours: dict = {}
    layers_by_group: List[List[Tuple[str, str, str]]] = []
    for group in merged_groups:
        group_layers: List[Tuple[str, str, str]] = []
        for path, points, env_type, onset, own_duration in group:
            model_id = str(next_id);    next_id += 1
            dataset_id = str(next_id);  next_id += 1
            layer_id = str(next_id);    next_id += 1

            ET.SubElement(data, "model", {
                "id": model_id, "name": path,
                "sampleRate": str(sample_rate), "type": "sparse",
                "dimensions": "2", "resolution": "1",
                "notifyOnAdd": "true", "dataset": dataset_id,
            })
            ds = ET.SubElement(data, "dataset", {"id": dataset_id, "dimensions": "2"})
            for point in points:
                t_norm, value, label = _split_point(point)
                frame = str(round((onset + t_norm * own_duration) * sample_rate))
                ET.SubElement(ds, "point", {"frame": frame, "value": str(value), "label": label})

            colour, colour_name = _param_colour(path, param_colours)
            plot_style = _layer_plot_style(points, env_type)
            ET.SubElement(data, "layer", {
                "id": layer_id, "type": "timevalues", "name": path, "model": model_id,
                "plotStyle": plot_style, "verticalScale": "0",
                "colourName": colour_name, "colour": colour, "darkBackground": "true",
            })
            group_layers.append((layer_id, model_id, path))
            layer_ids.append((layer_id, model_id, path))
        layers_by_group.append(group_layers)

    # Layer marker: un time instant all'inizio di ogni plateau (confini degli
    # stati). Modello 1D sparse; etichetta = indice plateau (1-based). Viene
    # poi referenziato in ogni pane, cosi' le linee verticali sono allineate su
    # waveform ed envelope e la navigazione PgUp/PgDown ci salta sopra.
    # ``group_marks``: (tempo assoluto in secondi, etichetta) — inizio di ogni
    # gruppo di stream sulla timeline. Rossi, per orientarsi fra i gruppi in
    # fila; sostituiscono i marker di plateau quando presenti.
    marker_ref: Tuple[str, str] | None = None
    plateau_starts = _plateau_starts(envelopes) if markers else []
    if group_marks:
        marker_model_id = str(next_id);    next_id += 1
        marker_dataset_id = str(next_id);  next_id += 1
        marker_layer_id = str(next_id);    next_id += 1
        ET.SubElement(data, "model", {
            "id": marker_model_id, "name": "Group starts",
            "sampleRate": str(sample_rate), "type": "sparse",
            "dimensions": "1", "resolution": "1",
            "notifyOnAdd": "true", "dataset": marker_dataset_id,
        })
        ET.SubElement(data, "playparameters", {
            "mute": "true", "pan": "0", "gain": "1",
            "clipId": "", "model": marker_model_id,
        })
        mds = ET.SubElement(data, "dataset", {"id": marker_dataset_id, "dimensions": "1"})
        for t_sec, label in group_marks:
            ET.SubElement(mds, "point", {
                "frame": str(round(t_sec * sample_rate)), "label": label,
            })
        ET.SubElement(data, "layer", {
            "id": marker_layer_id, "type": "timeinstants", "name": "Group starts",
            "model": marker_model_id, "plotStyle": "0",
            "colourName": "Red", "colour": "#ff0000", "darkBackground": "true",
        })
        marker_ref = (marker_layer_id, marker_model_id)
    elif plateau_starts:
        marker_model_id = str(next_id);    next_id += 1
        marker_dataset_id = str(next_id);  next_id += 1
        marker_layer_id = str(next_id);    next_id += 1

        ET.SubElement(data, "model", {
            "id": marker_model_id, "name": "Plateau markers",
            "sampleRate": str(sample_rate), "type": "sparse",
            "dimensions": "1", "resolution": "1",
            "notifyOnAdd": "true", "dataset": marker_dataset_id,
        })
        # Mute esplicito: un modello sparse e' audibile di default e SV
        # sintetizza un click percussivo a ogni instant durante il playback.
        # Senza questo, ogni marker produrrebbe un "click" udibile.
        ET.SubElement(data, "playparameters", {
            "mute": "true", "pan": "0", "gain": "1",
            "clipId": "", "model": marker_model_id,
        })
        mds = ET.SubElement(data, "dataset", {"id": marker_dataset_id, "dimensions": "1"})
        for idx, t_norm in enumerate(plateau_starts, start=1):
            frame = str(round(t_norm * duration_sec * sample_rate))
            ET.SubElement(mds, "point", {"frame": frame, "label": str(idx)})
        ET.SubElement(data, "layer", {
            "id": marker_layer_id, "type": "timeinstants", "name": "Plateau markers",
            "model": marker_model_id, "plotStyle": "0",  # PlotInstants
            "colourName": "White", "colour": "#ffffff", "darkBackground": "true",
        })
        marker_ref = (marker_layer_id, marker_model_id)

    # Display
    display = ET.SubElement(root, "display")
    ET.SubElement(display, "window", {"width": "1728", "height": "1057"})

    # multi: un pane per *gruppo* di envelope (v. il raggruppamento sopra). Il
    # gruppo e' la voce logica: la parte del path prima di '/' (lo stream_id,
    # presente solo negli export stack) tagliata al primo '__'. Cosi' gli assi
    # di uno stesso stream stanno in un pane unico e le versioni di una stessa
    # voce (cugini_1__d=3__g=4, cugini_1__d=6__g=4, ...) ci finiscono insieme
    # invece di aprire un pane per combinazione — lo stesso criterio per
    # nome-base gia' usato dal ramo stems (``stack_stems_to_sv``) e dal
    # post-merge del render (``merge_stems_by_base``). Per lo sweep i path non
    # hanno ne' '/' ne' '__': ogni envelope resta un gruppo a se', un pane per
    # envelope, identico a prima.
    multi_groups = layers_by_group

    n_panes = 1 + (1 if layout == "single" else len(multi_groups))
    pane_height = str(max(150, 912 // n_panes))

    def _pane(parent):
        return ET.SubElement(parent, "view", {
            "centre": "0", "zoom": "1024", "deepZoom": "1",
            "followPan": "1", "followZoom": "1", "tracking": "page",
            "type": "pane", "centreLineVisible": "1", "height": pane_height,
        })

    def _ruler_layer(pane):
        ET.SubElement(pane, "layer", {
            "id": "1", "type": "timeruler", "name": "Ruler",
            "model": "0", "visible": "true",
        })

    marker_name = "Group starts" if group_marks else "Plateau markers"

    def _marker_layer(pane, *, waveform_pane: bool = False):
        if marker_ref is None:
            return
        # I marker di gruppo servono a orientarsi in ogni pane, non solo sulla
        # waveform: lo scope ristretto vale solo per i plateau.
        if markers_scope == "waveform" and not waveform_pane and not group_marks:
            return
        layer_id, model_id = marker_ref
        ET.SubElement(pane, "layer", {
            "id": layer_id, "type": "timeinstants", "name": marker_name,
            "model": model_id, "visible": "true",
        })

    waveform_pane = _pane(display)
    _ruler_layer(waveform_pane)
    ET.SubElement(waveform_pane, "layer", {
        "id": "3", "type": "spectrogram", "name": "Spectrogram",
        "model": "0", "visible": "true",
    })
    ET.SubElement(waveform_pane, "layer", {
        "id": "2", "type": "waveform", "name": "Waveform",
        "model": "0", "visible": "true",
    })
    _marker_layer(waveform_pane, waveform_pane=True)

    if layout == "single":
        env_pane = _pane(display)
        _ruler_layer(env_pane)
        for layer_id, model_id, path in layer_ids:
            ET.SubElement(env_pane, "layer", {
                "id": layer_id, "type": "timevalues", "name": path,
                "model": model_id, "visible": "true",
            })
        _marker_layer(env_pane)
    else:  # multi: un pane per gruppo (per stream negli export stack)
        for group in multi_groups:
            pane = _pane(display)
            _ruler_layer(pane)
            for layer_id, model_id, path in group:
                ET.SubElement(pane, "layer", {
                    "id": layer_id, "type": "timevalues", "name": path,
                    "model": model_id, "visible": "true",
                })
            _marker_layer(pane)

    ET.SubElement(root, "selections")

    xml_bytes = b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE sonic-visualiser>\n'
    xml_bytes += ET.tostring(root, encoding="unicode").encode("utf-8")
    return bz2.compress(xml_bytes)


def variant_to_sv(variant_yaml_path: str, audio_path: str, out_path: str,
                  layout: Layout = "multi", markers: bool = True,
                  markers_scope: Literal["all", "waveform"] = "waveform") -> str:
    """Legge un variant YAML + audio, scrive un file .sv pronto per SV.

    Con ``markers=True`` (default) aggiunge un layer ``timeinstants`` con un
    marker all'inizio di ogni plateau. ``markers_scope`` controlla in quali
    pane appaiono: ``"all"`` (default) li replica in ogni pane, ``"waveform"``
    li mostra solo nel pane della forma d'onda.
    """
    import yaml

    with open(variant_yaml_path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)

    duration = float(doc.get("duration", 1.0))
    streams = doc.get("streams", [])
    envelopes = [(path, points, env_type, 0.0, duration)
                 for path, points, env_type in (_find_envelopes(streams[0]) if streams else [])]

    sr = _sample_rate(audio_path)
    compressed = _build_sv_xml(os.path.abspath(audio_path), sr, duration,
                               envelopes, layout, markers=markers,
                               markers_scope=markers_scope)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(compressed)
    return out_path


def _stack_envelopes(doc: Any, axis_paths: Optional[List[str]] = None
                     ) -> List[Tuple[str, List, str, float, float]]:
    """Envelope di *tutti* gli stream del documento stack, con path prefissato.

    A differenza del singolo file sweep (un solo stream), il documento stack
    collassa N stream sommati in un audio: per non confonderli nei pannelli, il
    path di ogni envelope e' prefissato dallo stream_id (``base/density``). Gli
    assi scalari non producono envelope, quindi restano fuori.

    Ogni stream porta il proprio ``onset`` e la propria ``duration`` (diversi
    dal totale dello stack quando gli stream sono concatenati, es. da
    ``versions``): i punti normalizzati [0,1] dell'envelope vanno riportati
    all'asse assoluto dello stack come ``onset + t_norm * duration``, non
    contro la durata totale del documento.
    """
    out: List[Tuple[str, List, str, float, float]] = []
    for stream in doc.get("streams", []):
        sid = stream.get("stream_id", "stream")
        onset = float(stream.get("onset", 0.0))
        stream_duration = float(stream.get("duration", doc.get("duration", 1.0)))
        for path, points, env_type in _stream_envelopes(stream, axis_paths):
            out.append((f"{sid}/{path}", points, env_type, onset, stream_duration))
    return out


def _padded_stem(audio_path: str, onset: float, padded_dir: str) -> str:
    """Copia dello stem con ``onset`` secondi di silenzio prepesi.

    Sonic Visualiser ancora ogni modello wavefile al frame 0 della sessione
    (``SVFileReader`` legge solo ``file`` e ``sampleRate``, nessun attributo
    di offset): l'unico modo di mostrare uno stem al suo onset e' cuocere
    l'offset *dentro* l'audio. Gli originali non si toccano: la copia paddata
    vive in ``padded_dir`` con lo stesso basename, rigenerata solo se
    l'originale e' piu' nuovo (stessa incrementalita' del resto della
    pipeline). Il padding rispetta canali e sample rate dell'originale.
    """
    import numpy as np
    import soundfile as sf

    out_path = os.path.join(padded_dir, os.path.basename(audio_path))
    if (os.path.exists(out_path)
            and os.path.getmtime(out_path) >= os.path.getmtime(audio_path)):
        return out_path
    data, sr = sf.read(audio_path)
    pad_frames = round(onset * sr)
    pad_shape = (pad_frames,) + data.shape[1:]
    padded = np.concatenate([np.zeros(pad_shape, dtype=data.dtype), data])
    os.makedirs(padded_dir, exist_ok=True)
    sf.write(out_path, padded, sr, format="AIFF")
    return out_path


def _build_sv_xml_stems(stems: List[Tuple[str, str, int, float, float, List[Tuple[str, List, str, float, float]]]]) -> bytes:
    """Un pane per stem: waveform + spectrogram + tutti i suoi envelope insieme.

    ``stems``: lista di (stream_id, audio_path_assoluto, sample_rate,
    onset_sec, duration_sec, envelopes). Ogni stem ha il proprio model audio,
    cosi' ognuno mantiene la propria durata e sample rate. Ogni envelope e'
    (nome, points, type, onset_sec, duration_sec): l'onset/durata sono SUOI,
    non del pane — in un pane accorpato per nome-base (issue #24) convivono
    gli envelope di piu' versioni, ognuna nella propria finestra temporale.

    L'onset NON sposta il modello audio (SV ancora ogni wavefile al frame
    0, limite del formato .sv): l'audio arriva gia' paddato col silenzio
    iniziale (``_padded_stem``) o accorpato ancorato a 0, e qui l'onset
    offsetta solo i breakpoint degli envelope, cosi' inviluppo e contenuto
    restano allineati.
    """
    root = ET.Element("sv")
    data = ET.SubElement(root, "data")

    display = ET.SubElement(root, "display")
    ET.SubElement(display, "window", {"width": "1728", "height": "1057"})

    n_panes = len(stems)
    pane_height = str(max(150, 912 // max(n_panes, 1)))

    def _pane():
        return ET.SubElement(display, "view", {
            "centre": "0", "zoom": "1024", "deepZoom": "1",
            "followPan": "1", "followZoom": "1", "tracking": "page",
            "type": "pane", "centreLineVisible": "1", "height": pane_height,
        })

    next_id = 0
    param_colours: dict = {}
    for stream_index, (stream_id, audio_path, sr, onset, duration, envelopes) in enumerate(stems):
        wave_model_id = str(next_id); next_id += 1
        spec_layer_id = str(next_id); next_id += 1
        wave_layer_id = str(next_id); next_id += 1

        # Con _NATIVE_ONSET_OFFSET l'audio non e' paddato su disco: l'onset
        # e' l'attributo "start" del model, sul fork svcore che lo rispetta.
        model_start_frame = round(onset * sr) if _NATIVE_ONSET_OFFSET else 0
        end_frame = model_start_frame + round(duration * sr)

        # SV usa il mainModel come riferimento del transport (durata, sample
        # rate, play/pausa): senza uno, la barra spaziatrice non ha nulla da
        # suonare. Il primo stem fa da main; gli altri restano playparameters
        # non mutati, cosi' vengono comunque mixati in playback.
        ET.SubElement(data, "model", {
            "id": wave_model_id, "name": os.path.basename(audio_path),
            "sampleRate": str(sr), "start": str(model_start_frame), "end": str(end_frame),
            "type": "wavefile", "file": audio_path,
            "mainModel": "true" if stream_index == 0 else "false",
        })
        ET.SubElement(data, "playparameters", {
            "mute": "false", "pan": "0", "gain": "1", "clipId": "", "model": wave_model_id,
        })
        ET.SubElement(data, "layer", {
            "id": spec_layer_id, "type": "spectrogram", "name": f"{stream_id} :: Spectrogram",
            "model": wave_model_id, "channel": "-1",
            "windowSize": "8192", "windowHopLevel": "3",
            "colourScheme": "2", "colourRotation": "0",
            "gain": "1", "threshold": "-80",
            "minFrequency": "0", "maxFrequency": "0",
            "frequencyScale": "0", "binDisplay": "0",
            "normalizeColumns": "0", "normalizeVisibleArea": "0",
            "darkBackground": "true",
        })
        ET.SubElement(data, "layer", {
            "id": wave_layer_id, "type": "waveform", "name": f"{stream_id} :: Waveform",
            "model": wave_model_id, "gain": "1", "showMeans": "1", "greyscale": "1",
            "channelMode": "0", "channel": "-1", "scale": "0", "middleLineHeight": "0.5",
            "aggressive": "0", "autoNormalize": "0", "oversampling": "1",
            "colourName": "Bright Blue", "colour": "#1e96ff", "darkBackground": "true",
        })

        pane = _pane()
        ET.SubElement(pane, "layer", {
            "id": "ruler_" + stream_id, "type": "timeruler", "name": "Ruler",
            "model": wave_model_id, "visible": "true",
        })
        ET.SubElement(pane, "layer", {
            "id": spec_layer_id, "type": "spectrogram", "name": f"{stream_id} :: Spectrogram",
            "model": wave_model_id, "visible": "true",
        })
        ET.SubElement(pane, "layer", {
            "id": wave_layer_id, "type": "waveform", "name": f"{stream_id} :: Waveform",
            "model": wave_model_id, "visible": "true",
        })

        # Un layer per parametro, non per stream: le versioni impilate sulla
        # stessa voce sono consecutive nel tempo, quindi i loro envelope di
        # density (idem grain.duration) sono una polilinea sola.
        for name, points, env_type, env_onset, env_duration in _merge_by_param(envelopes, group=stream_id):
            env_model_id = str(next_id); next_id += 1
            env_dataset_id = str(next_id); next_id += 1
            env_layer_id = str(next_id); next_id += 1

            ET.SubElement(data, "model", {
                "id": env_model_id, "name": name,
                "sampleRate": str(sr), "type": "sparse",
                "dimensions": "2", "resolution": "1",
                "notifyOnAdd": "true", "dataset": env_dataset_id,
            })
            ds = ET.SubElement(data, "dataset", {"id": env_dataset_id, "dimensions": "2"})
            for point in points:
                t_norm, value, label = _split_point(point)
                frame = str(round((env_onset + t_norm * env_duration) * sr))
                ET.SubElement(ds, "point", {"frame": frame, "value": str(value), "label": label})

            colour, colour_name = _param_colour(name, param_colours)
            plot_style = _layer_plot_style(points, env_type)
            ET.SubElement(data, "layer", {
                "id": env_layer_id, "type": "timevalues", "name": name,
                "model": env_model_id, "plotStyle": plot_style, "verticalScale": "0",
                "colourName": colour_name, "colour": colour, "darkBackground": "true",
            })
            ET.SubElement(pane, "layer", {
                "id": env_layer_id, "type": "timevalues", "name": name,
                "model": env_model_id, "visible": "true",
            })

        # Marker "Version starts": un instant a ogni onset distinto tra gli
        # envelope del pane, cioe' all'inizio di ogni versione impilata sulla
        # stessa voce (issue segnalata dall'utente: nelle versions serve un
        # riferimento visivo dove cambia la variante, non solo il colore).
        version_onsets = sorted({env_onset for _n, _p, _t, env_onset, _d in envelopes})
        if len(version_onsets) > 1:
            marker_model_id = str(next_id); next_id += 1
            marker_dataset_id = str(next_id); next_id += 1
            marker_layer_id = str(next_id); next_id += 1

            ET.SubElement(data, "model", {
                "id": marker_model_id, "name": f"{stream_id} :: Version starts",
                "sampleRate": str(sr), "type": "sparse",
                "dimensions": "1", "resolution": "1",
                "notifyOnAdd": "true", "dataset": marker_dataset_id,
            })
            ET.SubElement(data, "playparameters", {
                "mute": "true", "pan": "0", "gain": "1",
                "clipId": "", "model": marker_model_id,
            })
            mds = ET.SubElement(data, "dataset", {"id": marker_dataset_id, "dimensions": "1"})
            for idx, v_onset in enumerate(version_onsets, start=1):
                frame = str(round(v_onset * sr))
                ET.SubElement(mds, "point", {"frame": frame, "label": str(idx)})
            ET.SubElement(data, "layer", {
                "id": marker_layer_id, "type": "timeinstants",
                "name": f"{stream_id} :: Version starts",
                "model": marker_model_id, "plotStyle": "0",
                "colourName": "Red", "colour": "#ff0000", "darkBackground": "true",
            })
            ET.SubElement(pane, "layer", {
                "id": marker_layer_id, "type": "timeinstants",
                "name": f"{stream_id} :: Version starts",
                "model": marker_model_id, "visible": "true",
            })

    ET.SubElement(root, "selections")

    xml_bytes = b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE sonic-visualiser>\n'
    xml_bytes += ET.tostring(root, encoding="unicode").encode("utf-8")
    return bz2.compress(xml_bytes)


def stack_stems_to_sv(
    stack_yaml_path: str, audio_dir: str, out_path: str, process: str = "stack",
    axis_paths: Optional[List[str]] = None,
) -> str | None:
    """.sv con un pane per stem audio (un file audio per stream), non per il mix.

    A differenza di ``stack_to_sv`` (un solo pane waveform contro l'audio
    sommato), qui ogni voce ha il proprio pane con la propria waveform +
    spectrogram + tutti i suoi envelope insieme. Richiede gli stem gia'
    renderizzati (``render --stem``, attivo di default): ``{base}__{stream_id}.aif``
    accanto al mix in ``audio_dir`` (v. ``DefaultNamingStrategy``). Ritorna
    ``None`` (senza scrivere nulla) se manca anche un solo stem.

    Gli stream vengono raggruppati per nome-base (lo ``stream_id`` prima del
    primo ``__``): un gruppo con piu' stream e' una voce logica moltiplicata da
    ``versions``/``percorso`` e consuma il file accorpato ``{process}__{base}.aif``
    prodotto dal post-merge del render (issue #24) — un pane per voce, non uno
    per combinazione/istanza. Il file accorpato e' gia' ancorato al tempo 0 del
    documento, quindi niente padding; gli envelope di ogni istanza restano
    distinti nel pane, offsettati al proprio onset. I gruppi singoli consumano
    lo stem grezzo come sempre (con l'onset cotto come silenzio iniziale).

    ``process`` (default ``stack``) e' il prefisso degli stem del processo,
    cablato un tempo a ``stack`` — gli stem di ``versions``/``percorso`` (nelle
    proprie cartelle) hanno prefisso ``versions__``/``percorso__`` (issue #29).
    """
    import yaml

    with open(stack_yaml_path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)

    groups: dict = {}
    for stream in doc.get("streams", []):
        base_name = stream.get("stream_id", "stream").split("__", 1)[0]
        groups.setdefault(base_name, []).append(stream)

    stems = []
    for base_name, group in groups.items():
        if len(group) > 1:
            audio_path = os.path.join(audio_dir, f"{process}__{base_name}.aif")
            if not os.path.exists(audio_path):
                print(f"[sv] stem accorpato mancante per '{base_name}': {audio_path} (esegui 'render --stem')")
                return None
            envelopes = []
            end = 0.0
            for stream in group:
                stream_id = stream.get("stream_id", "stream")
                onset = float(stream.get("onset", 0) or 0)
                duration = float(stream.get("duration", doc.get("duration", 1.0)))
                end = max(end, onset + duration)
                for path, points, env_type in _stream_envelopes(stream, axis_paths):
                    envelopes.append((f"{stream_id}/{path}", points, env_type, onset, duration))
            stems.append((base_name, os.path.abspath(audio_path), _sample_rate(audio_path), 0.0, end, envelopes))
            continue
        stream = group[0]
        stream_id = stream.get("stream_id", "stream")
        audio_path = os.path.join(audio_dir, f"{process}__{stream_id}.aif")
        if not os.path.exists(audio_path):
            print(f"[sv] stem mancante per '{stream_id}': {audio_path} (esegui 'render --stem')")
            return None
        onset = float(stream.get("onset", 0) or 0)
        duration = float(stream.get("duration", doc.get("duration", 1.0)))
        if onset > 0 and not _NATIVE_ONSET_OFFSET:
            # SV non sa offsettare un wavefile nel .sv: l'onset si cuoce come
            # silenzio iniziale in una copia (gli stem originali non si toccano).
            audio_path = _padded_stem(
                audio_path, onset, os.path.join(audio_dir, "padded")
            )
        envelopes = [(f"{stream_id}/{path}", points, env_type, onset, duration)
                     for path, points, env_type in _stream_envelopes(stream, axis_paths)]
        stems.append((stream_id, os.path.abspath(audio_path), _sample_rate(audio_path), onset, duration, envelopes))

    compressed = _build_sv_xml_stems(stems)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(compressed)
    return out_path


def stack_to_sv(stack_yaml_path: str, audio_path: str, out_path: str,
                layout: Layout = "multi",
                axis_paths: Optional[List[str]] = None) -> str:
    """Scrive un .sv per il documento multi-stream ``stack.yml`` contro il suo audio.

    Un solo file per lo stack (gli stream sono sommati in un audio): gli envelope
    di tutti gli stream finiscono nei pannelli, path prefissato per stream. Niente
    marker di plateau: sono un concetto di sweep (griglia plateau/transition
    sincronizzata), assente in stack dove ogni asse ha la sua X.
    """
    import yaml

    with open(stack_yaml_path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)

    duration = float(doc.get("duration", 1.0))
    envelopes = _stack_envelopes(doc, axis_paths)

    # Confini dei gruppi: l'onset di ogni stream, dedup, etichettato col
    # nome-base della voce (``cugini_3__g0=5__d0=3`` -> ``cugini``). Con
    # `versions` piu' voci condividono lo stesso onset: la prima vince.
    marks: dict = {}
    for stream in doc.get("streams", []):
        t = round(float(stream.get("onset", 0) or 0), 6)
        base = stream.get("stream_id", "").split("__", 1)[0]
        marks.setdefault(t, re.sub(r"_\d+$", "", base))  # toglie l'indice di voce
    group_marks = sorted(marks.items())

    sr = _sample_rate(audio_path)
    compressed = _build_sv_xml(os.path.abspath(audio_path), sr, duration,
                               envelopes, layout, markers=False,
                               group_marks=group_marks)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(compressed)
    return out_path
