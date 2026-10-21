r"""대화문 원문 Markdown으로 data/dialogues.json을 만든다.

원문 형식: 파트는 `---` 줄로 나눈다. 각 대화는 번호만 있는 줄(`**1**`, `6`)로 시작하고,
대사는 `화자 : 대사` 꼴이다. 굵게 표시(`**`)와 Markdown 이스케이프(`\!`)는 지운다.
한 줄에 다른 화자의 대사가 붙어 있으면(`... ? Medhi : ...`) 나눈다.
채점 표현은 대사를 문장 단위(. ! ? … 뒤)로 나눈 것이다.

사용: python scripts/build_dialogues.py [원문 경로]   (기본 data/dialogues.md)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PART_TITLES = {1: "La routine du matin", 2: "Dans une boutique"}
SPEAKER_KEYS = "ABC"

NUMBER_RE = re.compile(r"^\s*(\d+)\s*$")
LINE_RE = re.compile(r"^([^\s:][^:]{0,24}?)\s*:\s*(.+)$")


def clean(line: str) -> str:
    line = line.replace("**", "").replace("\u00a0", " ")
    line = re.sub(r"\\([!?.*_#()\[\]-])", r"\1", line)
    line = line.replace("\t", " ")
    return re.sub(r"\s+", " ", line).strip()


def sentences(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?…])\s+", text)
    out = []
    for p in pieces:
        if out and not re.search(r"\w", p):   # "Trente-huit. !"의 "!"처럼 글자 없는 조각은 앞 문장에 붙인다.
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def parse_section(lines: list[str], keys: dict) -> list[dict]:
    """keys: 파트 안에서 화자 이름 → 표시 키(A·B·C). 같은 인물은 파트 내내 같은 색을 쓴다."""
    raw = [m.groups() for m in (LINE_RE.match(l) for l in lines) if m]
    if len(raw) != len(lines):
        bad = [l for l in lines if not LINE_RE.match(l)]
        raise SystemExit(f"화자를 찾을 수 없는 줄: {bad}")
    names = list(dict.fromkeys(name for name, _ in raw))
    inline = re.compile(r"\s+(?=(?:" + "|".join(map(re.escape, names)) + r")\s*:)")
    units = []
    for name, text in raw:
        first, *rest = inline.split(text)
        for speaker, t in [(name, first)] + [LINE_RE.match(r).groups() for r in rest]:
            units.append({"speaker": speaker, "text": t.strip()})
    for u in units:
        if u["speaker"] not in keys:
            if len(keys) == len(SPEAKER_KEYS):
                raise SystemExit(f"한 파트의 화자가 {len(SPEAKER_KEYS)}명보다 많습니다: {u['speaker']}")
            keys[u["speaker"]] = SPEAKER_KEYS[len(keys)]
    return [{"n": i + 1, "speaker": keys[u["speaker"]], "name": u["speaker"], "text": u["text"]}
            for i, u in enumerate(units)]


def build(md_path: Path) -> list[dict]:
    parts = re.split(r"(?m)^\s*-{3,}\s*$", md_path.read_text(encoding="utf-8"))
    out = []
    for part_no, part in enumerate(parts, start=1):
        sections, current, keys = [], None, {}
        for line in map(clean, part.splitlines()):
            if not line:
                continue
            if m := NUMBER_RE.match(line):
                current = (int(m.group(1)), []); sections.append(current)
            elif current is None:
                raise SystemExit(f"파트 {part_no}: 대화 번호 앞에 내용이 있습니다: {line}")
            else:
                current[1].append(line)
        for k, (number, lines) in enumerate(sections, start=1):
            units = parse_section(lines, keys)
            expressions = []
            for u in units:
                for s in sentences(u["text"]):
                    expressions.append({"n": len(expressions) + 1, "unit": u["n"], "text": s})
            out.append({"id": f"P{part_no}-{k}", "part": part_no,
                        "title": f"{PART_TITLES.get(part_no, f'Partie {part_no}')} ({k})",
                        "source": f"Partie {part_no} / Dialogue {number}", "audio": None,
                        "units": units, "expressions": expressions})
    return out


def main():
    if len(sys.argv) > 2:
        raise SystemExit(__doc__)
    src = Path(sys.argv[1]) if len(sys.argv) == 2 else ROOT / "data" / "dialogues.md"
    data = build(src)
    target = ROOT / "data" / "dialogues.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    by_part = {}
    for d in data:
        by_part.setdefault(d["part"], []).append(f"{d['id']}({len(d['units'])}턴/{len(d['expressions'])}문장)")
    for p, items in by_part.items():
        print(f"파트 {p}: {', '.join(items)}")
    print(f"{len(data)}편 → {target}")


if __name__ == "__main__":
    main()
