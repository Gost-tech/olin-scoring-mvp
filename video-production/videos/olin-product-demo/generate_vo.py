#!/usr/bin/env python3
"""Generate voiceover WAV files for olin-product-demo using edge-tts."""
import asyncio
import subprocess
import os

VOICE = "en-US-JennyNeural"
RATE = "+5%"
ASSETS = os.path.join(os.path.dirname(__file__), "assets")

SCRIPTS = [
    ("vo-01", "This is Olin's analyst workflow. We will follow one synthetic merchant case from intake to outcome."),
    ("vo-02", "First, the analyst connects the merchant. Consent is recorded, then bank flow, bureau, point of sale, and supplier evidence are linked to the case."),
    ("vo-03", "Olin assembles the signals into an explainable recommendation. This case scores sixty-three point six, Tier ten, and routes to committee because the bureau file is missing."),
    ("vo-04", "The analyst can inspect every signal, confidence range, and reason before deciding. The requested amount and the repayment capacity stay visible together."),
    ("vo-05", "Olin recommends. The partner decides. A rationale is required before the case can move to approval, review, or decline."),
    ("vo-06", "The decision, disbursement, and repayment outcome stay linked in one audit trail. This paid-on-time status is synthetic demonstration data."),
    ("vo-07", "The safe next step is ten authorized shadow cases. No money moves. Partners measure coverage, speed, disagreement, and missing evidence."),
]

async def generate(name: str, text: str):
    mp3_path = os.path.join(ASSETS, f"{name}.mp3")
    wav_path = os.path.join(ASSETS, f"{name}.wav")

    import edge_tts
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    await communicate.save(mp3_path)

    # Convert to WAV with ffmpeg
    subprocess.run(
        ["ffmpeg", "-y", "-i", mp3_path, "-ar", "44100", "-ac", "1", wav_path],
        check=True, capture_output=True
    )
    os.remove(mp3_path)
    duration = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", wav_path]
    ).decode().strip())
    print(f"  {name}.wav → {duration:.2f}s")

async def main():
    for name, text in SCRIPTS:
        print(f"Generating {name}...")
        await generate(name, text)
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
