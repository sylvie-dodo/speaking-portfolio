"""프랑스어 전사 결과를 대본과 정렬해 표현별 만족 여부와 점수를 계산한다."""
import json
import re
import unicodedata
from pathlib import Path

DEFAULT_CFG = json.loads((Path(__file__).with_name("scoring.json")).read_text(encoding="utf-8"))

UNITS = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
         "treize", "quatorze", "quinze", "seize"]
TENS = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}
# 복수형·이형을 한 형태로 맞춘다(quatre-vingts → vingt, deux cents → cent).
SAME = {"vingts": "vingt", "cents": "cent"}


def _below_100(n: int) -> list[str]:
    if n < 17:
        return [UNITS[n]]
    if n < 20:
        return ["dix", UNITS[n - 10]]
    if n < 70:
        tens, r = TENS[n // 10], n % 10
        return [tens] if r == 0 else [tens, "et", "un"] if r == 1 else [tens, UNITS[r]]
    if n < 80:  # 71 → soixante et onze, 75 → soixante quinze
        return ["soixante", "et", "onze"] if n == 71 else ["soixante"] + _below_100(n - 60)
    return ["quatre", "vingt"] + (_below_100(n - 80) if n > 80 else [])


def num_words(n: int) -> list[str]:
    """프랑스어 기수. 하이픈은 쓰지 않는다(canonical이 하이픈을 공백으로 나누므로)."""
    if n < 100:
        return _below_100(n)
    if n < 1000:
        h, r = divmod(n, 100)
        return (["cent"] if h == 1 else [UNITS[h], "cent"]) + (_below_100(r) if r else [])
    if n < 1_000_000:  # 1995 → mille neuf cent quatre vingt quinze
        th, r = divmod(n, 1000)
        return (["mille"] if th == 1 else num_words(th) + ["mille"]) + (num_words(r) if r else [])
    return [str(n)]


def ordinal_words(n: int) -> list[str]:
    """2e → deuxième, 21e → vingt et unième. 1er는 canonical에서 따로 처리한다."""
    w = num_words(n)
    last = w[-1]
    if last == "un":
        w[-1] = "unième"
    elif last == "cinq":
        w[-1] = "cinquième"
    elif last == "neuf":
        w[-1] = "neuvième"
    elif last.endswith("e"):
        w[-1] = last[:-1] + "ième"
    else:
        w[-1] = last + "ième"
    return w


def canonical(text: str) -> list[str]:
    t = unicodedata.normalize("NFC", text).lower()
    t = t.replace("’", "'").replace("‘", "'").replace(" ", " ").replace(" ", " ")
    t = re.sub(r"(?:(?<=\s)|^)[−–-]\s*(?=\d)", " moins ", t)          # −5 → moins 5
    t = re.sub(r"(\d+)\s*,\s*(\d+)", r"\1 virgule \2", t)              # 3,5 → 3 virgule 5
    t = re.sub(r"(\d+)\s*%", r"\1 pour cent", t)
    t = re.sub(r"€\s*(\d+)", r"\1 euros", t)
    t = re.sub(r"(\d+)\s*€", r"\1 euros", t)
    t = re.sub(r"(\d+)\s*(℃|°\s*c\b|degrés?\s+celsius)", r"\1 degrés", t)
    t = re.sub(r"(\d+)\s*h\s*(\d{2})\b", r"\1 heures \2", t)            # 14h30 → 14 heures 30
    t = re.sub(r"(\d+)\s*h\b", r"\1 heures", t)
    t = re.sub(r"\b1\s*(er)\b", " premier ", t)
    t = re.sub(r"\b1\s*(re|ère)\b", " première ", t)
    t = re.sub(r"(\d+)\s*(?:e|ème|ième|eme)\b", lambda m: " ".join(ordinal_words(int(m.group(1)))), t)
    t = re.sub(r"\d+", lambda m: " ".join(num_words(int(m.group(0)))), t)
    t = t.replace("'", " ")                                            # 엘리지옹 분리: l'ami → l ami
    t = re.sub(r"[^\w ]+|[\d_]+", " ", t)                              # 하이픈·구두점 제거, 악센트 문자는 유지
    return [SAME.get(w, w) for w in t.split()]


def align(ref: list[str], hyp: list[str]) -> list[tuple]:
    """Needleman-Wunsch. 일치 +2, 대체 -1, 삽입/삭제 -1."""
    n, m = len(ref), len(hyp)
    score = [[0] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        score[i][0] = -i; back[i][0] = "up"
    for j in range(1, m + 1):
        score[0][j] = -j; back[0][j] = "left"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diag = score[i - 1][j - 1] + (2 if ref[i - 1] == hyp[j - 1] else -1)
            up = score[i - 1][j] - 1
            left = score[i][j - 1] - 1
            best = max(diag, up, left)
            score[i][j] = best
            back[i][j] = "diag" if best == diag else ("up" if best == up else "left")
    pairs = []
    i, j = n, m
    while i > 0 or j > 0:
        b = back[i][j]
        if b == "diag":
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif b == "up":
            pairs.append((i - 1, None)); i -= 1
        else:
            pairs.append((None, j - 1)); j -= 1
    return list(reversed(pairs))


def expand_words(words: list[dict]) -> list[dict]:
    """Scribe 단어를 정규화 토큰으로 펼친다(한 단어가 여러 토큰이 되면 타임스탬프 공유)."""
    toks = []
    for w in words:
        if w.get("type", "word") != "word":
            continue
        for tok in canonical(w["text"]):
            toks.append({"tok": tok, "start": float(w["start"]), "end": float(w["end"])})
    return toks


def score_dialogue(dialogue: dict, scribe: dict, turn_offsets: list, cfg: dict) -> dict:
    hyp_all = expand_words(scribe.get("words", []))
    offsets = {o["turn"]: o for o in turn_offsets}
    results = []
    for u in dialogue["units"]:
        off = offsets[u["n"]]
        hyp = [w for w in hyp_all if off["start"] - 0.25 <= w["start"] <= off["end"] + 0.25]
        exprs = [e for e in dialogue["expressions"] if e["unit"] == u["n"]]
        ref, owner = [], []
        for e in exprs:
            toks = canonical(e["text"])
            ref += toks; owner += [e["n"]] * len(toks)
        pairs = align(ref, [w["tok"] for w in hyp])
        for e in exprs:
            idxs = {k for k, o in enumerate(owner) if o == e["n"]}
            matched = [(r, h) for r, h in pairs if r in idxs and h is not None]
            hits = sum(1 for r, h in matched if ref[r] == hyp[h]["tok"])
            aligned = sorted({h for _, h in matched})
            match_ratio = hits / len(idxs) if idxs else 0.0
            transcript = " ".join(hyp[h]["tok"] for h in aligned)
            if not aligned:
                results.append({"n": e["n"], "text": e["text"], "transcript": "", "match_ratio": 0.0,
                                "max_gap": None, "wpm": None, "ok": False, "reason": "no_words"})
                continue
            gaps = [hyp[b]["start"] - hyp[a]["end"] for a, b in zip(aligned, aligned[1:])]
            max_gap = max(gaps) if gaps else 0.0
            span = hyp[aligned[-1]]["end"] - hyp[aligned[0]]["start"]
            wpm = (len(aligned) / (span / 60)) if (span > 0 and len(aligned) > 1) else None
            reason = ""
            if match_ratio < cfg["match_ratio_min"]:
                reason = "match_ratio"
            elif max_gap > cfg["max_gap_sec"]:
                reason = "max_gap"
            elif wpm is not None and wpm < cfg["wpm_min"]:
                reason = "wpm"
            results.append({"n": e["n"], "text": e["text"], "transcript": transcript,
                            "match_ratio": round(match_ratio, 3), "max_gap": round(max_gap, 2),
                            "wpm": (round(wpm, 1) if wpm is not None else None), "ok": reason == "", "reason": reason})
    results.sort(key=lambda r: r["n"])
    satisfied = sum(1 for r in results if r["ok"])
    return {"satisfied": satisfied, "score": dialogue_score(satisfied), "expressions": results}


def dialogue_score(satisfied: int) -> int:
    if satisfied >= 9:
        return 10
    if satisfied >= 1:
        return satisfied + 1
    return 1


def final_score(scores: list[int]) -> int:
    if not scores:
        return 0
    x = sum(scores) / len(scores)
    return int(x + 0.5)
