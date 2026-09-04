from granstudies.curation import merge_results, kept_entries


def test_merge_preserves_manual_fields():
    existing = [
        {
            "name": "v1",
            "kept": True,
            "tags": ["denso"],
            "notes": "bello",
            "descriptors": {"rms": 0.1},
            "params": {},
        }
    ]
    fresh = [
        {
            "name": "v1",
            "kept": None,
            "tags": [],
            "notes": "",
            "descriptors": {"rms": 0.9},  # ricalcolato
            "params": {"density": 50},
        }
    ]
    merged = merge_results(existing, fresh)
    assert len(merged) == 1
    m = merged[0]
    assert m["kept"] is True            # campo manuale preservato
    assert m["tags"] == ["denso"]
    assert m["notes"] == "bello"
    assert m["descriptors"]["rms"] == 0.9  # descrittore aggiornato
    assert m["params"] == {"density": 50}


def test_merge_drops_removed_and_adds_new():
    existing = [{"name": "old", "kept": True, "tags": [], "notes": ""}]
    fresh = [
        {"name": "new", "kept": None, "tags": [], "notes": "", "descriptors": {}, "params": {}}
    ]
    merged = merge_results(existing, fresh)
    names = {m["name"] for m in merged}
    assert names == {"new"}             # 'old' rimosso, 'new' aggiunto


def test_kept_entries():
    entries = [
        {"name": "a", "kept": True},
        {"name": "b", "kept": False},
        {"name": "c", "kept": None},
    ]
    assert [e["name"] for e in kept_entries(entries)] == ["a"]
