#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const project = resolve(new URL("..", import.meta.url).pathname);
const audioMetaPath = resolve(project, "audio_meta.json");

function seconds(value) {
  const match = value.match(/(\d+):(\d+):(\d+),(\d+)/);
  if (!match) throw new Error(`Invalid SRT timestamp: ${value}`);
  return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]) + Number(match[4]) / 1000;
}

function wordsFromSrt(path) {
  const blocks = readFileSync(path, "utf8").trim().split(/\r?\n\r?\n+/);
  const words = [];
  for (const block of blocks) {
    const lines = block.split(/\r?\n/);
    const timing = lines[1]?.match(/(.+?)\s+-->\s+(.+)/);
    if (!timing) continue;
    const start = seconds(timing[1]);
    const end = seconds(timing[2]);
    const tokens = lines.slice(2).join(" ").trim().split(/\s+/).filter(Boolean);
    const step = (end - start) / Math.max(tokens.length, 1);
    tokens.forEach((text, index) => {
      words.push({
        id: `w${words.length}`,
        text,
        start: Number((start + step * index).toFixed(3)),
        end: Number((start + step * (index + 1)).toFixed(3)),
      });
    });
  }
  return words;
}

const previous = existsSync(audioMetaPath)
  ? JSON.parse(readFileSync(audioMetaPath, "utf8"))
  : { sfx: [] };

const voices = [];
for (let frame = 1; frame <= 6; frame += 1) {
  const id = String(frame).padStart(2, "0");
  const media = resolve(project, `assets/voice/${id}.mp3`);
  const subtitle = resolve(project, `assets/voice/${id}.srt`);
  const duration = Number(
    execFileSync("ffprobe", [
      "-v", "error",
      "-show_entries", "format=duration",
      "-of", "default=nw=1:nk=1",
      media,
    ], { encoding: "utf8" }).trim(),
  );
  voices.push({
    frame,
    path: `assets/voice/${id}.mp3`,
    duration_s: Number(duration.toFixed(3)),
    words: wordsFromSrt(subtitle),
  });
}

const output = {
  bgm: null,
  bgm_pending: false,
  voices,
  sfx: previous.sfx ?? [],
};

writeFileSync(audioMetaPath, `${JSON.stringify(output, null, 2)}\n`);
console.log(`wrote ${audioMetaPath} with ${voices.reduce((sum, voice) => sum + voice.words.length, 0)} timed words`);
