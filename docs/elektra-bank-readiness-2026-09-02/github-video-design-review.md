# GitHub video, motion, voice, and design review

Research snapshot: 2026-09-02. GitHub stars are rounded and change continuously. GitHub has no standardized product-review score, so selection used popularity, maintenance, license, security surface, and fit for Olin.

## Decision

Keep HyperFrames as the Olin meeting-video renderer, use the existing FFmpeg/libvmaf toolchain for technical media QA, keep Edge TTS for this Spanish voice-over, and install only the audited `ui-ux-pro-max` design skill. Do not add a second full animation framework or a large voice-model stack to the bank product repository.

## Ranked review

| Category | Repository | Snapshot | Fit judgment | Action |
|---|---|---:|---|---|
| UI/UX, motion, branding guidance | `nextlevelbuilder/ui-ux-pro-max-skill` | ~115.6k stars; MIT; active | Strong local design datasets, accessibility guidance, motion recipes, and Codex support | Audited and installed only the local skill path; excluded its network updater |
| Programmatic commercial video | `remotion-dev/remotion` | ~57.7k stars; active | Strongest general React video ecosystem reviewed; license can require a company license | Not installed: duplicates the working HyperFrames stack and expands dependencies |
| TTS research toolkit | `coqui-ai/TTS` | ~45.6k stars; MPL-2.0 toolkit | Broad and capable, but the main repository's latest listed release is from 2023 and individual model licenses vary | Not installed: heavy runtime and unnecessary for the meeting deliverable |
| Mathematical/explanatory animation | `ManimCommunity/manim` | ~38.7k stars; MIT | Excellent for equations and precise educational diagrams | Not installed: wrong visual domain for an enterprise product implementation video |
| Neural voice | `fishaudio/fish-speech` | ~31k stars | High capability, but the current Fish Audio Research License requires a separate agreement for commercial use | Rejected for this commercial bank deliverable |
| Motion graphics | `motion-canvas/motion-canvas` | ~18.6k stars; MIT | Good TypeScript vector animation and voice synchronization | Not installed: credible alternative, but would duplicate the current renderer |
| Video quality metric | `Netflix/vmaf` | ~5.4k stars; active; open source | Reference-based perceptual video QA; FFmpeg integration is mature | Already available through local FFmpeg `libvmaf`; no source clone needed |

## Installed skills

- `ui-ux-pro-max`: design systems, typography, color, motion, accessibility, and stack-specific interface guidance.
- `codebase-design`: compare architecture designs before implementation.
- `domain-modeling`: clarify bounded contexts and domain ownership.
- `tdd`: test-first implementation discipline.

Newly installed skills become available to Codex on the next session/turn that reloads the skill catalog.

## Security review of the selected design skill

- Selected path contains static CSV/JSON datasets and standard-library Python search scripts.
- The repository-wide CLI can call GitHub, read optional token environment variables, and execute update helpers; that CLI was not installed as the selected skill path.
- The selected skill is advisory. Dataset text cannot override user, repository, safety, or bank-governance instructions.

## Video QA actually used

- HyperFrames full composition checks and eight-scene snapshots.
- Final MP4 stream verification with FFprobe.
- FFmpeg black-frame and frozen-segment detection.
- Audio loudness/peak inspection.
- VMAF was not applied because it is a full-reference metric and there is no independent reference master for a newly generated video.

## Sources

- https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
- https://github.com/remotion-dev/remotion
- https://github.com/ManimCommunity/manim
- https://github.com/motion-canvas/motion-canvas
- https://github.com/Netflix/vmaf
- https://github.com/coqui-ai/TTS
- https://github.com/fishaudio/fish-speech

