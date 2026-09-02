#!/usr/bin/env python3
"""Generate an offline macOS voice track for the Olin demo."""
import os
import subprocess

from generate_vo import ASSETS, SCRIPTS

VOICE = "Paulina"
RATE = "188"


def generate(name: str, text: str) -> None:
    aiff_path = os.path.join(ASSETS, f"{name}.aiff")
    wav_path = os.path.join(ASSETS, f"{name}.wav")
    subprocess.run(
        ["say", "-v", VOICE, "-r", RATE, text, "-o", aiff_path],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", aiff_path, "-ar", "44100", "-ac", "1", wav_path],
        check=True,
        capture_output=True,
    )
    duration = float(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                wav_path,
            ]
        )
        .decode()
        .strip()
    )
    print(f"{name}.wav -> {duration:.2f}s")


if __name__ == "__main__":
    for segment, script in SCRIPTS:
        generate(segment, script)
