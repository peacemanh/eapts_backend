import pyttsx3
import os

engine = pyttsx3.init()
engine.setProperty("rate", int(os.getenv("TTS_RATE", 150)))
engine.setProperty("volume", float(os.getenv("TTS_VOLUME", 1.0)))


def speak(text: str):
    print("🔊", text)
    engine.say(text)
    engine.runAndWait()
