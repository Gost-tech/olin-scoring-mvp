#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h}"
PROJECT="${ROOT:h}"
FFMPEG="$PROJECT/node_modules/.pnpm/ffmpeg-static@5.3.0/node_modules/ffmpeg-static/ffmpeg"
SEGMENTS="$ROOT/segments"
OUTPUT="$PROJECT/public/media"

mkdir -p "$SEGMENTS" "$OUTPUT"

build_scene() {
  local id="$1"
  local image="$2"
  local audio="$3"
  local duration="$4"
  local fade_out="$5"

  "$FFMPEG" -y \
    -loop 1 -framerate 30 -i "$ROOT/$image" \
    -i "$ROOT/$audio" \
    -filter_complex "[0:v]zoompan=z='min(max(zoom,pzoom)+0.00007,1.018)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1440x810:fps=30,fade=t=in:st=0:d=0.22,fade=t=out:st=$fade_out:d=0.25[v];[1:a]apad=pad_dur=1.2,afade=t=in:st=0:d=0.12,afade=t=out:st=$fade_out:d=0.25[a]" \
    -map "[v]" -map "[a]" -t "$duration" \
    -c:v libx264 -preset medium -crf 24 -pix_fmt yuv420p \
    -c:a aac -b:a 128k -ar 44100 \
    -movflags +faststart "$SEGMENTS/$id.mp4"
}

build_scene "01" "scenes/video-01-evidence.png" "narration/01.aiff" "8.60" "8.35"
build_scene "02" "scenes/video-02-organize.png" "narration/02.aiff" "5.85" "5.60"
build_scene "03" "scenes/video-03-decision.png" "narration/03.aiff" "8.90" "8.65"
build_scene "04" "scenes/video-04-control.png" "narration/04.aiff" "7.70" "7.45"
build_scene "05" "scenes/video-05-pilot.png" "narration/05.aiff" "10.05" "9.80"

"$FFMPEG" -y \
  -i "$SEGMENTS/01.mp4" \
  -i "$SEGMENTS/02.mp4" \
  -i "$SEGMENTS/03.mp4" \
  -i "$SEGMENTS/04.mp4" \
  -i "$SEGMENTS/05.mp4" \
  -filter_complex "[0:v][0:a][1:v][1:a][2:v][2:a][3:v][3:a][4:v][4:a]concat=n=5:v=1:a=1[v][a]" \
  -map "[v]" -map "[a]" \
  -c:v libx264 -preset medium -crf 24 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -ar 44100 \
  -movflags +faststart "$OUTPUT/olin-demo.mp4"

cp "$ROOT/subtitles-es.vtt" "$OUTPUT/olin-demo-es.vtt"

"$FFMPEG" -y \
  -i "$ROOT/scenes/video-01-evidence.png" \
  -c:v libwebp -quality 84 "$OUTPUT/olin-demo-poster.webp"

echo "Created $OUTPUT/olin-demo.mp4"
