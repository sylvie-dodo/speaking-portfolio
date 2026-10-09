"""학급 입장 열기(모의·본 평가). 사용: python scripts/open.py [반 ...]  (인자 없으면 1반)"""
import sys
from common import service_client

classes = [int(a) for a in sys.argv[1:]] or [1]
c = service_client()
for cls in classes:
    c.table("settings").upsert({"class": cls, "exam_open": True}).execute()
print("열림:", classes)
