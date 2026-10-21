import json
from pathlib import Path

import pytest

from scoring import align, canonical, dialogue_score, final_score, score_dialogue, DEFAULT_CFG

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "dialogues.json"
BY_ID = {d["id"]: d for d in json.loads(DATA_PATH.read_text(encoding="utf-8"))} if DATA_PATH.exists() else {}
needs_data = pytest.mark.skipif(not BY_ID, reason="data/dialogues.json 없음: scripts/build_dialogues.py 실행 필요")


def words_from(text_units, offsets, wpm=120):
    """단위별 텍스트를 균등 간격 단어 타임스탬프로 만든다."""
    words = []
    for unit_text, off in zip(text_units, offsets):
        toks = unit_text.split()
        step = 60 / wpm
        t = off["start"]
        for tok in toks:
            words.append({"text": tok, "start": round(t, 3), "end": round(t + step * 0.8, 3), "type": "word"})
            t += step
    return {"text": " ".join(text_units), "words": words}


def offsets_for(d, unit_sec=12.0, gap=0.5, wpm=120):
    """단위 창은 unit_sec 이상, 긴 대사는 wpm 속도로 다 읽을 만큼 늘린다."""
    out, t = [], 0.0
    for u in d["units"]:
        sec = max(unit_sec, len(u["text"].split()) * 60 / wpm + 1)
        out.append({"turn": u["n"], "start": t, "end": t + sec}); t += sec + gap
    return out


@pytest.mark.parametrize("src,expected", [
    ("Bonjour, ça va ?", ["bonjour", "ça", "va"]),
    ("J'ai visité l'école.", ["j", "ai", "visité", "l", "école"]),
    ("J’ai visité l’école.", ["j", "ai", "visité", "l", "école"]),
    ("Qu'est-ce que tu fais ?", ["qu", "est", "ce", "que", "tu", "fais"]),
    ("ÉCOLE", ["école"]),
    ("J'ai 21 ans.", ["j", "ai", "vingt", "et", "un", "ans"]),
    ("J'ai vingt et un ans.", ["j", "ai", "vingt", "et", "un", "ans"]),
    ("71", ["soixante", "et", "onze"]),
    ("80", ["quatre", "vingt"]),
    ("quatre-vingts", ["quatre", "vingt"]),
    ("97", ["quatre", "vingt", "dix", "sept"]),
    ("quatre-vingt-dix-sept", ["quatre", "vingt", "dix", "sept"]),
    ("200", ["deux", "cent"]),
    ("deux cents", ["deux", "cent"]),
    ("en 1995", ["en", "mille", "neuf", "cent", "quatre", "vingt", "quinze"]),
    ("le 1er mai", ["le", "premier", "mai"]),
    ("la 2e fois", ["la", "deuxième", "fois"]),
    ("le 21e siècle", ["le", "vingt", "et", "unième", "siècle"]),
    ("le 5ème étage", ["le", "cinquième", "étage"]),
    ("à 14h30", ["à", "quatorze", "heures", "trente"]),
    ("à 8 h", ["à", "huit", "heures"]),
    ("15 €", ["quinze", "euros"]),
    ("−5 °C", ["moins", "cinq", "degrés"]),
    ("3,5 %", ["trois", "virgule", "cinq", "pour", "cent"]),
])
def test_canonical(src, expected):
    assert canonical(src) == expected


def test_align_substitution_and_deletion():
    pairs = align(["a", "b", "c", "d"], ["a", "x", "d"])
    assert (0, 0) in pairs and (3, 2) in pairs
    ref_idx = [r for r, h in pairs if r is not None]
    assert sorted(ref_idx) == [0, 1, 2, 3]


def by_unit(d, unit_n):
    return [e for e in d["expressions"] if e["unit"] == unit_n]


@needs_data
def test_perfect_reading_scores_ten():
    d = BY_ID["P1-1"]
    offs = offsets_for(d)
    scribe = words_from([u["text"] for u in d["units"]], offs)
    r = score_dialogue(d, scribe, offs, DEFAULT_CFG)
    assert r["satisfied"] == r["total"] == len(d["expressions"]) and r["score"] == 10
    assert all(e["ok"] for e in r["expressions"])


@needs_data
def test_every_dialogue_perfect_reading_scores_ten():
    for d in BY_ID.values():
        offs = offsets_for(d)
        r = score_dialogue(d, words_from([u["text"] for u in d["units"]], offs), offs, DEFAULT_CFG)
        assert r["satisfied"] == r["total"] and r["score"] == 10, (d["id"], [e for e in r["expressions"] if not e["ok"]])


@needs_data
def test_one_silent_unit_fails_only_its_expressions():
    d = BY_ID["P1-1"]
    offs = offsets_for(d)
    texts = [u["text"] for u in d["units"]]
    texts[2] = ""
    r = score_dialogue(d, words_from(texts, offs), offs, DEFAULT_CFG)
    silent = {e["n"] for e in by_unit(d, 3)}
    assert {e["n"] for e in r["expressions"] if not e["ok"]} == silent
    assert all(e["reason"] == "no_words" for e in r["expressions"] if e["n"] in silent)
    assert r["score"] == dialogue_score(r["total"] - len(silent), r["total"])


@needs_data
def test_split_expressions_scored_separately():
    d = BY_ID["P1-1"]  # 단위 1이 문장 2개로 나뉨
    first, second = by_unit(d, 1)
    offs = offsets_for(d)
    texts = [u["text"] for u in d["units"]]
    texts[0] = first["text"]  # 뒷 문장 누락
    r = score_dialogue(d, words_from(texts, offs), offs, DEFAULT_CFG)
    ok = {e["n"]: e["ok"] for e in r["expressions"]}
    assert ok[first["n"]] is True and ok[second["n"]] is False and r["satisfied"] == r["total"] - 1


@needs_data
def test_long_pause_fails_fluency():
    d = BY_ID["P1-1"]
    target = by_unit(d, 2)[0]
    offs = offsets_for(d)
    scribe = words_from([u["text"] for u in d["units"]], offs)
    # 단위 2의 셋째 단어부터 3개를 3초 뒤로 민다
    idx = [i for i, w in enumerate(scribe["words"]) if w["start"] >= offs[1]["start"]][2]
    for w in scribe["words"][idx:idx + 3]:
        w["start"] += 3.0; w["end"] += 3.0
    r = score_dialogue(d, scribe, offs, DEFAULT_CFG)
    hit = next(e for e in r["expressions"] if e["n"] == target["n"])
    assert hit["ok"] is False and hit["reason"] == "max_gap"


@needs_data
def test_gap_between_units_not_counted():
    d = BY_ID["P1-1"]
    offs = offsets_for(d, gap=5.0)  # 단위 사이 5초
    r = score_dialogue(d, words_from([u["text"] for u in d["units"]], offs), offs, DEFAULT_CFG)
    assert r["satisfied"] == r["total"]


@needs_data
def test_slow_speech_fails_wpm():
    # 한 단어 표현은 WPM을 잴 수 없어 일치만으로 만족 처리되므로 모든 표현이 여러 단어인 편을 쓴다.
    d = BY_ID["P1-1"]
    assert all(len(e["text"].split()) >= 3 for e in d["expressions"])
    offs = offsets_for(d, unit_sec=60.0, wpm=30)
    scribe = words_from([u["text"] for u in d["units"]], offs, wpm=30)
    r = score_dialogue(d, scribe, offs, DEFAULT_CFG)
    assert r["satisfied"] == 0 and r["score"] == 1
    assert {e["reason"] for e in r["expressions"]} == {"wpm"}


@needs_data
def test_one_word_expression_satisfied_by_match_alone():
    d = BY_ID["P2-2"]
    one = [e for e in d["expressions"] if len(canonical(e["text"])) == 1]
    assert one, "한 단어 표현이 있는 편이어야 한다"
    offs = offsets_for(d, unit_sec=60.0, wpm=30)
    r = score_dialogue(d, words_from([u["text"] for u in d["units"]], offs, wpm=30), offs, DEFAULT_CFG)
    hits = {x["n"]: x for x in r["expressions"]}
    for e in one:
        assert hits[e["n"]]["ok"] and hits[e["n"]]["wpm"] is None, e["text"]


@needs_data
def test_empty_transcript_scores_one():
    d = BY_ID["P1-1"]
    r = score_dialogue(d, {"text": "", "words": []}, offsets_for(d), DEFAULT_CFG)
    assert r["satisfied"] == 0 and r["score"] == 1


def test_numbers_as_digits_or_words_both_match():
    d = {"units": [{"n": 1, "speaker": "A", "text": "Le musée a ouvert en 1995."}],
         "expressions": [{"n": 1, "unit": 1, "text": "Le musée a ouvert en 1995."}]}
    offs = offsets_for(d)
    for spoken in ("Le musée a ouvert en 1995.", "Le musée a ouvert en mille neuf cent quatre-vingt-quinze."):
        r = score_dialogue(d, words_from([spoken], offs), offs, DEFAULT_CFG)
        assert r["expressions"][0]["match_ratio"] == 1.0, spoken


@pytest.mark.parametrize("n,s", [(10, 10), (9, 10), (8, 9), (5, 6), (1, 2), (0, 1)])
def test_dialogue_score_table(n, s):
    assert dialogue_score(n) == s


@pytest.mark.parametrize("n,total,s", [(7, 7, 10), (6, 7, 9), (4, 7, 6), (1, 7, 2), (0, 7, 1),
                                        (17, 17, 10), (16, 17, 10), (15, 17, 9), (0, 0, 1)])
def test_dialogue_score_scales_with_expression_count(n, total, s):
    assert dialogue_score(n, total) == s


@pytest.mark.parametrize("scores,final", [([10, 9], 10), ([9, 8], 9), ([8, 7], 8), ([1, 1], 1), ([10, 0], 5), ([0, 0], 0)])
def test_final_score_round_half_up(scores, final):
    assert final_score(scores) == final
