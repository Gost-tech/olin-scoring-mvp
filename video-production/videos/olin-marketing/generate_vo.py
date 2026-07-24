#!/usr/bin/env python3
"""Generate voiceover WAV files for olin-marketing using edge-tts."""
import asyncio
import subprocess
import os

VOICE = "en-US-AndrewMultilingualNeural"
RATE = "+20%"
ASSETS = os.path.join(os.path.dirname(__file__), "assets")

# Scene windows: f1=7s, f2=7s, f3=8s, f4=8s, f5=7s, f6=8s
SCRIPTS = [
    ("vo-01", "54 million micro-businesses in Mexico. Only 10 percent with bank access. Can this business repay this loan?"),
    ("vo-02", "Olin assembles six merchant signals into one auditable credit case before any scoring begins."),
    ("vo-03", "Olin is not a black box. Observe sources and gaps, decide with a recommendation, collect repayment events, learn from each outcome."),
    ("vo-04", "Repayment capacity changes the offer. At 25,000 pesos the model counters with 12,000 — aligned to observed cash flow."),
    ("vo-05", "Olin surfaces the recommendation. Your analyst records their decision — rationale required before any approval or decline."),
    ("vo-06", "10 shadow cases, no money movement. Measure coverage, speed, analyst disagreement, and evidence gaps before deploying real credit."),
]

async def generate(name: str, text: str):
    mp3_path = os.path.join(ASSETS, f"{name}.mp3")
    wav_path = os.path.join(ASSETS, f"{name}.wav")

    import edge_tts
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    await communicate.save(mp3_path)

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
