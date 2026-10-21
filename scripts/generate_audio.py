"""대화문을 ElevenLabs 음성 합성으로 읽어 편마다 WAV 음원을 만들고 audio 버킷에 올린다.

화자마다 다른 목소리를 쓴다. scripts/tts_voices.json에 ElevenLabs 목소리 이름을 적으며, 고르는 순서는
by_dialogue(편별, 화자 이름 또는 독백은 "") → by_name(화자 이름) → default(화자 키 A·B·C)다.
이름은 계정의 My Voices에서 찾고, 없으면 Voice Library에서 찾아 --add-voices일 때 My Voices에 추가한다.
합성기가 잘못 읽는 표현은 pronunciation([원문, 읽힐 철자] 목록)으로 합성 입력에서만 바꾼다(화면·채점 원문은 그대로).
대사마다 합성한 소리를 pause_sec 쉼으로 이어 붙인다. 합성 결과는 tts_cache/에 저장해 같은 대사를 다시 과금하지 않는다.
올린 음원은 data/audio.json에 기록하고, build_dialogues.py가 대사가 바뀌지 않은 편에만 음원을 연결한다.

사용: python scripts/generate_audio.py                 (전 편 합성, audio_out/에 저장)
      python scripts/generate_audio.py P1-1 P3-2       (지정한 편만)
      python scripts/generate_audio.py --upload        (합성 후 업로드, data/audio.json 갱신)
      python scripts/generate_audio.py --add-voices    (Voice Library 목소리를 My Voices에 추가하며 합성)
      python scripts/generate_audio.py --list-voices   (계정에서 쓸 수 있는 목소리 목록)
"""
import hashlib
import json
import os
import re
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


def voice_for(dialogue: dict, unit: dict, cfg: dict = CONFIG) -> str:
    """대사에 쓸 목소리 이름."""
    name = unit.get("name", "")
    per = cfg.get("by_dialogue", {}).get(dialogue["id"], {})
    for key in (name, unit["speaker"]):
        if key in per:
            return per[key]
    return cfg["by_name"].get(name) or cfg["default"][unit["speaker"]]


def match_voice(name: str, voices: list[dict]) -> dict | None:
    """이름이 정확히 같으면 그것을, 아니면 이름으로 시작하는 목소리가 하나뿐일 때 그것을 고른다."""
    exact = [v for v in voices if v["name"].casefold() == name.casefold()]
    if exact:
        return exact[0]
    prefix = [v for v in voices if v["name"].casefold().startswith(name.casefold())]
    if len(prefix) > 1:
        raise SystemExit(f"'{name}'에 맞는 목소리가 여럿입니다: {[v['name'] for v in prefix]}. tts_voices.json에 전체 이름을 적으세요.")
    return prefix[0] if prefix else None


def resolve_voices(names: set[str], key: str, add: bool) -> dict:
    """목소리 이름 → voice_id."""
    headers = {"xi-api-key": key}
    mine = requests.get(f"{API}/voices", headers=headers, timeout=60)
    mine.raise_for_status()
    mine = mine.json()["voices"]
    ids, missing = {}, []
    for name in sorted(names):
        v = match_voice(name, mine)
        if v:
            ids[name] = v["voice_id"]; continue
        r = requests.get(f"{API}/shared-voices", headers=headers, params={"search": name, "page_size": 30}, timeout=60)
        r.raise_for_status()
        shared = match_voice(name, r.json().get("voices", []))
        if not shared:
            missing.append(name); continue
        if not add:
            missing.append(f"{name}(Voice Library에 있음, --add-voices로 추가)"); continue
        added = requests.post(f"{API}/voices/add/{shared['public_owner_id']}/{shared['voice_id']}",
                              headers=headers, json={"new_name": shared["name"]}, timeout=60)
        added.raise_for_status()
        ids[name] = added.json()["voice_id"]
        print(f"My Voices에 추가: {shared['name']}")
    if missing:
        raise SystemExit("목소리를 찾지 못했습니다: " + ", ".join(missing))
    return ids


def tts_text(text: str, cfg: dict = CONFIG) -> str:
    """합성 입력용 철자 보정. 대소문자를 가리지 않고 찾아, 첫 글자가 대문자였으면 대문자로 둔다."""
    for src, dst in cfg.get("pronunciation", []):
        def repl(m, dst=dst):
            return dst[:1].upper() + dst[1:] if m.group(0)[:1].isupper() else dst
        text = re.sub(re.escape(src), repl, text, flags=re.IGNORECASE)
    return text


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
    plan = [[voice_for(d, u) for u in d["units"]] for d in targets]
    ids = resolve_voices({v for p in plan for v in p}, key, "--add-voices" in args)
    bucket = None
    if upload:
        from common import service_client
        bucket = service_client().storage.from_("audio")
    for d, names in zip(targets, plan):
        chunks = [synthesize(tts_text(u["text"]), ids[v], key) for u, v in zip(d["units"], names)]
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
