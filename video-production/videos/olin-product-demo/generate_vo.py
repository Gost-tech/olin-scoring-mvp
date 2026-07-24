#!/usr/bin/env python3
"""Generate voiceover WAV files for olin-product-demo using edge-tts."""
import asyncio
import subprocess
import os

VOICE = "en-US-AndrewMultilingualNeural"
RATE = "+15%"
ASSETS = os.path.join(os.path.dirname(__file__), "assets")

SCRIPTS = [
    ("vo-01", "Follow one case through Olin — the real analyst workflow, synthetic data."),
    ("vo-02", "Every case starts with evidence. Bureau, bank flow, P.O.S., suppliers, tenure, and operations — assembled before scoring."),
    ("vo-03", "Score 63.6. Tier 10. DSCR 2.67. No bureau file — routed to committee."),
    ("vo-04", "At 25,000 pesos: committee. Drop to 12,000 and the model clears it. Counter-offer from observed cash flow."),
    ("vo-05", "Olin surfaces the recommendation. The analyst records their decision — rationale required before any approval or decline."),
    ("vo-06", "Disbursement and repayment stay linked to the original recommendation and decision. This case: paid on time."),
    ("vo-07", "Run 10 cases. No money movement. Shadow mode measures coverage, speed, disagreement, and evidence gaps."),
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
