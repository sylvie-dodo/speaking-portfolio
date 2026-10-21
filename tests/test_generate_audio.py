import io
import json
import wave
from pathlib import Path

from build_dialogues import attach_audio, text_hash
from generate_audio import CONFIG, assemble, sample_rate, voice_for

DATA = json.loads((Path(__file__).resolve().parents[1] / "data" / "dialogues.json").read_text(encoding="utf-8"))


def test_assemble_joins_chunks_with_pauses():
    rate = 1000
    wav = assemble([b"\x01\x00" * 100, b"\x02\x00" * 50], rate, 0.5)
    with wave.open(io.BytesIO(wav)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, rate)
        assert w.getnframes() == 300 + 100 + 500 + 50 + 300  # 앞 쉼 + 대사 + 쉼 + 대사 + 뒤 쉼


def test_every_speaker_has_a_voice_and_named_speakers_differ():
    for d in DATA:
        for u in d["units"]:
            assert voice_for(u)
    shop = {u["name"]: voice_for(u) for d in DATA if d["part"] == 2 for u in d["units"]}
    assert len(set(shop.values())) == len(shop) == 3
    assert sample_rate() == int(CONFIG["output_format"].split("_")[1])


def test_audio_attaches_only_when_text_unchanged():
    d1, d2 = json.loads(json.dumps(DATA[:2]))
    manifest = {d1["id"]: {"file": "a.wav", "text_hash": text_hash(d1)},
                d2["id"]: {"file": "b.wav", "text_hash": "old"}}
    stale = attach_audio([d1, d2], manifest)
    assert d1["audio"] == "a.wav" and d2["audio"] is None and stale == [d2["id"]]
