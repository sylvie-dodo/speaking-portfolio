"""대화문을 ElevenLabs 음성 합성으로 읽어 편마다 WAV 음원을 만들고 audio 버킷에 올린다.

화자마다 다른 목소리를 쓴다(scripts/tts_voices.json: 이름별 by_name이 우선, 없으면 화자 키 A·B·C별 voices).
대사마다 합성한 소리를 pause_sec 쉼으로 이어 붙인다. 합성 결과는 tts_cache/에 저장해 같은 대사를 다시 과금하지 않는다.
올린 음원은 data/audio.json에 기록하고, build_dialogues.py가 대사가 바뀌지 않은 편에만 음원을 연결한다.

사용: python scripts/generate_audio.py                 (전 편 합성, audio_out/에 저장)
      python scripts/generate_audio.py P1-1 P3-2       (지정한 편만)
      python scripts/generate_audio.py --upload        (합성 후 업로드, data/audio.json 갱신)
      python scripts/generate_audio.py --list-voices   (계정에서 쓸 수 있는 목소리 목록)
"""
import hashlib
import json
import os
import sys
import time
import wave
from pathlib import Path

import requests

from build_dialogues import text_hash
from common import ROOT, load_env

API = "https://api.elevenlabs.io/v1"
CONFIG = json.loads((Path(__file__).with_name("tts_voices.json")).read_text(encoding="utf-8"))
CACHE = ROOT / "tts_cache"
OUT = ROOT / "audio_out"
MANIFEST = ROOT / "data" / "audio.json"


def voice_for(unit: dict, cfg: dict = CONFIG) -> str:
    return cfg["by_name"].get(unit.get("name", ""), cfg["voices"][unit["speaker"]])


def sample_rate(cfg: dict = CONFIG) -> int:
    return int(cfg["output_format"].rsplit("_", 1)[1])


def assemble(chunks: list[bytes], rate: int, pause_sec: float) -> bytes:
    """16비트 모노 PCM 조각을 쉼으로 이어 WAV 바이트로 만든다. 앞뒤에도 짧은 쉼을 둔다."""
    import io
    gap = b"\x00\x00" * int(rate * pause_sec)
    lead = b"\x00\x00" * int(rate * 0.3)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(lead + gap.join(chunks) + lead)
    return buf.getvalue()


def api_key() -> str:
    load_env()
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit(".env에 ELEVENLABS_API_KEY 없음")
    return key


def synthesize(text: str, voice: str, key: str) -> bytes:
    tag = hashlib.sha256(f"{CONFIG['model_id']}|{CONFIG['output_format']}|{voice}|{text}".encode()).hexdigest()[:24]
    cached = CACHE / f"{tag}.pcm"
    if cached.exists():
        return cached.read_bytes()
    for attempt in range(3):
        r = requests.post(f"{API}/text-to-speech/{voice}", params={"output_format": CONFIG["output_format"]},
                          headers={"xi-api-key": key}, json={"text": text, "model_id": CONFIG["model_id"]}, timeout=120)
        if r.status_code == 200:
            CACHE.mkdir(exist_ok=True)
            cached.write_bytes(r.content)
            return r.content
        if r.status_code in (429, 500, 502, 503) and attempt < 2:
            time.sleep(5 * (attempt + 1)); continue
        raise RuntimeError(f"합성 실패 {r.status_code}: {r.text[:200]}")


def list_voices(key: str):
    r = requests.get(f"{API}/voices", headers={"xi-api-key": key}, timeout=60)
    r.raise_for_status()
    for v in r.json()["voices"]:
        labels = v.get("labels") or {}
        print(v["voice_id"], v["name"], labels.get("gender", ""), labels.get("accent", ""), labels.get("language", ""))


def main():
    args = sys.argv[1:]
    key = api_key()
    if "--list-voices" in args:
        list_voices(key); return
    upload = "--upload" in args
    only = {a for a in args if not a.startswith("--")}
    data = json.loads((ROOT / "data" / "dialogues.json").read_text(encoding="utf-8"))
    targets = [d for d in data if not only or d["id"] in only]
    if only - {d["id"] for d in targets}:
        raise SystemExit(f"없는 대화 ID: {sorted(only - {d['id'] for d in targets})}")
    OUT.mkdir(exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    bucket = None
    if upload:
        from common import service_client
        bucket = service_client().storage.from_("audio")
    for d in targets:
        chunks = [synthesize(u["text"], voice_for(u), key) for u in d["units"]]
        wav = assemble(chunks, sample_rate(), CONFIG["pause_sec"])
        name = f"{d['id']}.wav"
        (OUT / name).write_bytes(wav)
        line = f"{d['id']}: {len(d['units'])}개 대사, {len(wav) // 1024} KB → audio_out/{name}"
        if bucket is not None:
            bucket.upload(name, wav, {"content-type": "audio/wav", "upsert": "true"})
            manifest[d["id"]] = {"file": name, "text_hash": text_hash(d)}
            line += " (업로드)"
        print(line)
    if upload:
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("data/audio.json 갱신. python scripts/build_dialogues.py로 대화문에 음원을 연결하세요.")


if __name__ == "__main__":
    main()
