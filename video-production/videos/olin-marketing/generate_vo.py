#!/usr/bin/env python3
"""Generate a natural Mexican Spanish female voiceover for Olin marketing."""
import asyncio
import subprocess
import os

VOICE = "es-MX-DaliaNeural"
RATE = "+12%"
ASSETS = os.path.join(os.path.dirname(__file__), "assets")

SCRIPTS = [
    ("vo-01", "Ventas y depósitos viven separados. La actividad existe; la evidencia está fragmentada."),
    ("vo-02", "Olin selecciona la evidencia correcta: inventario, terminal punto de venta, flujo bancario o una ruta híbrida."),
    ("vo-03", "Cada expediente conserva propósito, consentimiento, identidad y una referencia recuperable para cada fuente verificada."),
    ("vo-04", "Olin no adivina quién pagará. Reduce incertidumbre mostrando capacidad, confianza, faltantes y la regla que produjo la recomendación."),
    ("vo-05", "Olin recomienda. La institución decide. Una razón obligatoria convierte acuerdos y diferencias en datos."),
    ("vo-06", "Diez expedientes en paralelo, sin mover dinero. Revisemos un caso, no una promesa."),
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
