#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OFFSETS="0 10 21 34 45 56 65 77"

for LANG in en es; do
  if [ "$LANG" = "en" ]; then
    MASTER="$ROOT/renders/Olin_Product_Demo_EN_visual_v2.mp4"
  else
    MASTER="$ROOT/renders/Olin_Product_Demo_ES_visual_v2.mp4"
  fi
  INPUTS="-i $ROOT/assets/bgm-91.wav"
  FILTER="[0:a]volume=0.075[bg];"
  INDEX=1

  for OFFSET in $OFFSETS; do
    PAD=$(printf '%d' "$INDEX")
    if [ "$PAD" -lt 10 ]; then
      PAD="0$PAD"
    fi
    INPUTS="$INPUTS -i $ROOT/assets/voice/$LANG/vo-$PAD.wav"
    DELAY=$((OFFSET * 1000))
    FILTER="$FILTER[$INDEX:a]loudnorm=I=-16:TP=-1.5:LRA=7,adelay=${DELAY}|${DELAY}[v$INDEX];"
    INDEX=$((INDEX + 1))
  done

  FILTER="$FILTER[bg][v1][v2][v3][v4][v5][v6][v7][v8]amix=inputs=9:duration=longest:normalize=0,alimiter=limit=0.92[mix]"
  MIX="$ROOT/assets/voice/$LANG/olin-demo-$LANG-mix.wav"
  OUTPUT="$ROOT/renders/Olin_Product_Demo_$(printf '%s' "$LANG" | tr '[:lower:]' '[:upper:]').mp4"

  # shellcheck disable=SC2086
  ffmpeg -y $INPUTS -filter_complex "$FILTER" -map "[mix]" -ar 48000 -ac 2 -t 91 "$MIX"
  ffmpeg -y -i "$MASTER" -i "$MIX" \
    -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 192k -t 91 -movflags +faststart "$OUTPUT"
done

echo "English and Spanish MP4s created in renders/."
