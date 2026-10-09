"""명렬 CSV(열 번호·이름)로 students를 적재하고 settings 1행을 만든다. 20번 행을 교사로 지정한다.

사용: python scripts/seed_students.py "<명렬 CSV 경로>"
"""
import csv
import sys
from pathlib import Path

from common import service_client

CLASS = 1
MAX_NUMBER = 20      # lib/number-combobox.js의 MAX_NUMBER와 같아야 한다.
TEACHER_NUMBER = 20


def read_roster(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [{"class": CLASS, "number": int(r["번호"]), "name": r["이름"].strip(),
                 "is_teacher": int(r["번호"]) == TEACHER_NUMBER}
                for r in csv.DictReader(f) if r["번호"].strip()]
    numbers = [r["number"] for r in rows]
    if bad := [n for n in numbers if not 1 <= n <= MAX_NUMBER]:
        raise SystemExit(f"번호는 1~{MAX_NUMBER}이어야 합니다: {bad}")
    if len(set(numbers)) != len(numbers):
        raise SystemExit("중복된 번호가 있습니다.")
    if TEACHER_NUMBER not in numbers:
        raise SystemExit(f"교사 행({TEACHER_NUMBER}번, 교사 이름)이 명렬에 없습니다.")
    return rows


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    rows = read_roster(Path(sys.argv[1]))
    client = service_client()
    client.table("students").upsert(rows).execute()
    client.table("settings").upsert({"class": CLASS, "exam_open": False}).execute()
    print(f"students {len(rows) - 1}명 + 교사 1명, settings 1행")


if __name__ == "__main__":
    main()
