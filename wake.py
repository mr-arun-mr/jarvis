"""Wake-word listener: say "Hey Jarvis", then your request. Runs without the browser.

mic -> openWakeWord ("hey_jarvis") -> record until you pause -> faster-whisper -> brain -> macOS `say`.
Run:  .venv/bin/python wake.py     (add --test to just print wake scores)
"""
import subprocess
import sys

import numpy as np
import sounddevice as sd
import webrtcvad
from faster_whisper import WhisperModel
from openwakeword.model import Model

import brain
import config
import notify

RATE = 16000
CHUNK = 1280              # 80 ms, what openWakeWord expects
THRESHOLD = 0.5
VOICE = "Daniel"
TAMIL_VOICE = "Vani"   # macOS has no Malayalam voice; Malayalam replies are shown as a notification instead
MAX_UTTERANCE_S = 15
SILENCE_S = 0.9
HISTORY_TURNS = 8

vad = webrtcvad.Vad(2)


def say(text: str, lang: str = "en") -> None:
    if lang == "ml":
        notify.notify("Jarvis", text)
        return
    subprocess.run(["say", "-v", TAMIL_VOICE if lang == "ta" else VOICE, text])


def ping() -> None:
    subprocess.Popen(["afplay", "/System/Library/Sounds/Tink.aiff"])


def record_utterance(mic: sd.InputStream) -> np.ndarray:
    """Record after the wake word until the speaker pauses (or the time limit)."""
    frame = RATE * 30 // 1000
    frames, silent, started = [], 0, False
    for _ in range(int(MAX_UTTERANCE_S * 1000 / 30)):
        data, _ = mic.read(frame)
        pcm = data[:, 0].tobytes()
        if vad.is_speech(pcm, RATE):
            started, silent = True, 0
        elif started:
            silent += 1
        if started:
            frames.append(data[:, 0].copy())
            if silent * 30 / 1000 > SILENCE_S:
                break
        elif len(frames) == 0 and _ > 200:  # nothing said within ~6s
            break
    if not frames:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(frames).astype(np.float32) / 32768.0


def main() -> None:
    test = "--test" in sys.argv
    oww = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
    cfg = config.load()
    # English only by default. For Malayalam/Tamil set "wake_stt_model": "large-v3-turbo" and "wake_language": "ml" (or "auto").
    stt = None if test else WhisperModel(cfg.get("wake_stt_model", "small.en"), compute_type="int8")
    forced = cfg.get("wake_language", "en")
    history: list[dict] = []
    print("Listening for 'Hey Jarvis'..." if not test else "Test mode: printing wake scores. Say 'Hey Jarvis'.", flush=True)
    with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK) as mic:
        while True:
            data, _ = mic.read(CHUNK)
            score = max(oww.predict(data[:, 0]).values())
            if test:
                if score > 0.1:
                    print(f"score {score:.2f}", flush=True)
                continue
            if score < THRESHOLD:
                continue
            oww.reset()
            ping()
            audio = record_utterance(mic)
            if audio.size == 0:
                continue
            segs, info = stt.transcribe(audio, language=None if forced == "auto" else forced)
            text = " ".join(s.text for s in segs).strip()
            lang = info.language if forced == "auto" else forced
            if not text:
                continue
            print(f"you> {text}", flush=True)
            history.append({"role": "user", "content": text})
            answer = brain.reply(history[-HISTORY_TURNS:], lang)
            history.append({"role": "assistant", "content": answer})
            print(f"jarvis> {answer}", flush=True)
            say(answer, lang)
            mic.read(mic.read_available)  # drop audio captured while speaking
            oww.reset()


if __name__ == "__main__":
    main()
