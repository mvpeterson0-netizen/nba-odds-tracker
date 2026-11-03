import json
import re
from pathlib import Path


REGISTRY = Path(__file__).resolve().parents[1] / "data" / "research" / "theses.json"


def test_thesis_registry_schema_and_ids():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["id_prefix"] == "NBA-TH"
    entries = data["entries"]
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"NBA-TH-\\d{3}", i) for i in ids)
    required = {"id", "title", "question", "created", "origin", "status", "scope", "data_needs", "notes"}
    for e in entries:
        assert required.issubset(e)
        assert e["title"].strip()
        assert e["question"].strip()
