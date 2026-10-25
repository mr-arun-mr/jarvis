"""Local Jarvis: mic -> faster-whisper -> Ollama -> macOS `say`."""
import sys

import numpy as np
import ollama
import sounddevice as sd
import webrtcvad
from faster_whisper import WhisperModel

import speech

MODEL = "qwen2.5:14b"
RATE = 16000
FRAME_MS = 30
FRAME = RATE * FRAME_MS // 1000
SILENCE_FRAMES = 25  # ~750ms of silence ends an utterance
VOICE = "Daniel"

SYSTEM = "You are Jarvis, a concise, witty personal assistant. Keep replies to 1-3 sentences."

stt = WhisperModel("small.en", compute_type="int8")
vad = webrtcvad.Vad(2)
history = [{"role": "system", "content": SYSTEM}]


def listen() -> np.ndarray:
    """Record until the speaker pauses."""
    frames, silent, started = [], 0, False
    with sd.RawInputStream(samplerate=RATE, blocksize=FRAME, dtype="int16", channels=1) as mic:
        while True:
            data, _ = mic.read(FRAME)
            data = bytes(data)
            speech = vad.is_speech(data, RATE)
            if speech:
                started, silent = True, 0
            elif started:
                silent += 1
            if started:
                frames.append(data)
                if silent > SILENCE_FRAMES:
                    break
    pcm = np.frombuffer(b"".join(frames), dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0


def speak(text: str) -> None:
    speech.say(text, VOICE)


def main() -> None:
    text_mode = "--text" in sys.argv
    print("Jarvis online. Ctrl+C to quit.")
    while True:
        if text_mode:
            user = input("you> ").strip()
        else:
            print("listening...")
            segs, _ = stt.transcribe(listen(), language="en")
            user = " ".join(s.text for s in segs).strip()
            print(f"you> {user}")
        if not user:
            continue
        history.append({"role": "user", "content": user})
        reply = ollama.chat(model=MODEL, messages=history)["message"]["content"]
        history.append({"role": "assistant", "content": reply})
        print(f"jarvis> {reply}")
        speak(reply)


if __name__ == "__main__":
    main()
