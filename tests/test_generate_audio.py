import io
import json
import wave
from pathlib import Path

from build_dialogues import attach_audio, text_hash
from generate_audio import CONFIG, assemble, match_voice, sample_rate, tts_text, voice_for

DATA = json.loads((Path(__file__).resolve().parents[1] / "data" / "dialogues.json").read_text(encoding="utf-8"))


def test_assemble_joins_chunks_with_pauses():
    rate = 1000
    wav = assemble([b"\x01\x00" * 100, b"\x02\x00" * 50], rate, 0.5)
    with wave.open(io.BytesIO(wav)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, rate)
        assert w.getnframes() == 300 + 100 + 500 + 50 + 300  # 앞 쉼 + 대사 + 쉼 + 대사 + 뒤 쉼


def test_voices_follow_the_chosen_cast():
    by_id = {d["id"]: d for d in DATA}
    cast = lambda did: {(u["name"] or u["speaker"]): voice_for(by_id[did], u) for u in by_id[did]["units"]}
    assert cast("P1-1") == {"A": "Alice", "B": "George"}
    assert cast("P1-2") == {"A": "Alice", "B": "Daniel"}
    assert cast("P2-2")["Cécile"] == "Alice" and cast("P2-2")["La vendeuse"] == "Lily" and cast("P2-2")["Medhi"] == "Chris"
    assert set(cast("P3-1").values()) == {"Brian"} and set(cast("P3-2").values()) == {"Lily"}
    for d in DATA:
        for u in d["units"]:
            assert voice_for(d, u)
    assert sample_rate() == int(CONFIG["output_format"].split("_")[1])


def test_match_voice_prefers_exact_then_unique_prefix():
    voices = [{"name": "Victoria"}, {"name": "Paul K - narrator"}, {"name": "Jean Petit"}, {"name": "Jean Petitjean"}]
    assert match_voice("victoria", voices)["name"] == "Victoria"
    assert match_voice("Paul K", voices)["name"] == "Paul K - narrator"
    assert match_voice("Jean Petit", voices)["name"] == "Jean Petit"
    assert match_voice("Nobody", voices) is None


def test_audio_attaches_only_when_text_unchanged():
    d1, d2 = json.loads(json.dumps(DATA[:2]))
    d1["audio"] = d2["audio"] = None
    manifest = {d1["id"]: {"file": "a.wav", "text_hash": text_hash(d1)},
                d2["id"]: {"file": "b.wav", "text_hash": "old"}}
    stale = attach_audio([d1, d2], manifest)
    assert d1["audio"] == "a.wav" and d2["audio"] is None and stale == [d2["id"]]


def test_pronunciation_fixes_only_tts_input_and_keeps_capitals():
    cfg = {"pronunciation": [["quelle est", "quelle è"]]}
    assert tts_text("Quelle est votre taille ?", cfg) == "Quelle è votre taille ?"
    assert tts_text("Et vous, quelle est votre routine ?", cfg) == "Et vous, quelle è votre routine ?"
    assert tts_text("C'est cher, non ?", cfg) == "C'est cher, non ?"
