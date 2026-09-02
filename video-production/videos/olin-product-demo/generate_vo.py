#!/usr/bin/env python3
"""Generate the Spanish female voiceover for Olin's end-to-end product demo."""
import asyncio
import subprocess
import os

VOICE = "es-MX-DaliaNeural"
RATE = "+4%"
ASSETS = os.path.join(os.path.dirname(__file__), "assets")

SCRIPTS = [
    ("vo-01", "Así pasa una solicitud realista por Olin, desde el primer mensaje hasta la decisión de una institución. El caso y el dinero que verás son simulados."),
    ("vo-02", "La dueña explica para qué necesita el financiamiento. Antes de consultar datos, el canal registra su autorización y conserva el texto exacto del consentimiento."),
    ("vo-03", "Con autorización, el expediente reúne identidad, Círculo, flujo bancario, ventas con terminal y evidencia operativa. Cada fuente conserva su referencia y las ausencias siguen visibles."),
    ("vo-04", "Olin crea el caso y ejecuta una política versionada. Devuelve una recomendación, un nivel de confianza y razones revisables. Nunca promete aprobación."),
    ("vo-05", "El expediente entra a la fila del equipo de crédito. El analista revisa capacidad de pago, estrés, cobertura, identidad y la contribución de cada señal."),
    ("vo-06", "Olin recomienda. La institución decide. Para cerrar el caso, el analista debe registrar la decisión oficial y su justificación."),
    ("vo-07", "Después del contrato y de los controles del socio, la institución puede ordenar el depósito. Esta pantalla es una simulación: Olin no mueve dinero ni reemplaza el proceso legal."),
    ("vo-08", "El resultado queda ligado al expediente original. Así Olin puede medir cobertura, tiempo, desacuerdos y, con casos reales del socio, aprender de los pagos. El siguiente paso es un piloto en paralelo."),
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
