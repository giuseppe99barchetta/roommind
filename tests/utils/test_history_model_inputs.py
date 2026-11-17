"""The model input columns survive the history files and its compaction only when replayable."""

from custom_components.roommind.utils.history_store import MODEL_INPUT_FIELDS, HistoryStore

FULL = {"model_power": 0.5, "model_solar": 1.0, "model_residual": 0.0, "model_occupancy": 0.2}


def _row(ts, **inputs):
    return {"timestamp": str(ts), "mode": "heating", "room_temp": "20", **{k: str(v) for k, v in inputs.items()}}


def test_record_writes_the_columns_and_blanks_missing_ones(tmp_path):
    hs = HistoryStore(str(tmp_path))
    hs.record("a", {"room_temp": 20.0, "mode": "heating", **FULL}, timestamp=1000.0)
    hs.record("a", {"room_temp": 20.0, "mode": "heating"}, timestamp=1180.0)
    first, second = hs.read_detail("a")
    assert [float(first[k]) for k in MODEL_INPUT_FIELDS] == [0.5, 1.0, 0.0, 0.2]
    assert all(second[k] == "" for k in MODEL_INPUT_FIELDS)


def test_compaction_averages_a_bucket_of_complete_same_mode_rows(tmp_path):
    hs = HistoryStore(str(tmp_path))
    rows = [_row(0, **FULL), _row(180, **{**FULL, "model_power": 0.7})]
    (bucket,) = hs._downsample(rows, 300)
    assert bucket["model_power"] == 0.6
    assert bucket["model_solar"] == 1.0


def test_compaction_blanks_a_bucket_with_an_unusable_row(tmp_path):
    hs = HistoryStore(str(tmp_path))
    (bucket,) = hs._downsample([_row(0, **FULL), _row(180)], 300)
    assert all(bucket[k] == "" for k in MODEL_INPUT_FIELDS)


def test_compaction_blanks_a_bucket_mixing_modes(tmp_path):
    hs = HistoryStore(str(tmp_path))
    rows = [_row(0, **FULL), _row(180, **{**FULL, "model_power": 0.0})]
    (bucket,) = hs._downsample(rows, 300)
    assert all(bucket[k] == "" for k in MODEL_INPUT_FIELDS)
    rows = [_row(0, **FULL), _row(180, **{**FULL, "model_power": -0.4})]
    (bucket,) = hs._downsample(rows, 300)
    assert bucket["model_power"] == ""


def test_an_old_file_gets_the_new_columns(tmp_path):
    """A detail file written before the columns is migrated on the next write."""
    import csv

    from custom_components.roommind.utils import history_store as mod

    hs = HistoryStore(str(tmp_path))
    old_fields = [f for f in mod.DETAIL_FIELDS if f not in MODEL_INPUT_FIELDS and f != "target_reason"]
    hs._ensure_dir()
    with open(hs._detail_path("a"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=old_fields)
        writer.writeheader()
        writer.writerow({"timestamp": "1000", "room_temp": "20", "mode": "idle"})
    hs.record("a", {"room_temp": 20.5, "mode": "idle", **FULL}, timestamp=1180.0)
    rows = hs.read_detail("a")
    assert len(rows) == 2
    assert rows[0]["model_power"] == "" and float(rows[1]["model_power"]) == 0.5
