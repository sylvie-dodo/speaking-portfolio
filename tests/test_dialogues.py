import json
from pathlib import Path

import pytest

from scoring import canonical

DATA = Path(__file__).resolve().parents[1] / "data" / "dialogues.json"
IDS = ["P1-1", "P1-2", "P1-3", "P1-4", "P1-5", "P2-1", "P2-2", "P2-3"]

pytestmark = pytest.mark.skipif(not DATA.exists(), reason="data/dialogues.json 없음: scripts/build_dialogues.py 실행 필요")


def load():
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_ids_parts_and_order():
    data = load()
    assert [d["id"] for d in data] == IDS
    assert [d["part"] for d in data] == [1] * 5 + [2] * 3


def test_expressions_numbered_and_mapped_to_units():
    for d in load():
        unit_ns = {u["n"] for u in d["units"]}
        assert d["expressions"], d["id"]
        assert all(e["unit"] in unit_ns for e in d["expressions"]), d["id"]
        assert [e["n"] for e in d["expressions"]] == list(range(1, len(d["expressions"]) + 1))


def test_expressions_concatenate_to_unit_text():
    for d in load():
        for u in d["units"]:
            parts = [e["text"] for e in d["expressions"] if e["unit"] == u["n"]]
            assert " ".join(parts) == u["text"], (d["id"], u["n"])


def test_every_expression_has_scorable_words():
    for d in load():
        for e in d["expressions"]:
            assert canonical(e["text"]), (d["id"], e["text"])


def test_speakers_keep_one_key_per_name_within_a_part():
    keys = {}
    for d in load():
        for u in d["units"]:
            assert u["speaker"] in {"A", "B", "C"} and u["name"] and u["text"]
            assert keys.setdefault((d["part"], u["name"]), u["speaker"]) == u["speaker"], (d["id"], u["name"])


def test_no_markdown_leftovers():
    for d in load():
        for u in d["units"]:
            assert "**" not in u["text"] and "\\" not in u["text"], (d["id"], u["n"])
