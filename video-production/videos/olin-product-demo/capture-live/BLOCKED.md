# Capture Failed

Capture failed: Failed to launch the browser process:  Code: null

stderr:
dyld[25620]: Symbol not found: (_kVTCompressionPropertyKey_ReferenceBufferCount)
  Referenced from: '/Users/pc/.cache/hyperframes/chrome/chrome-headless-shell/mac-152.0.7928.2/chrome-headless-shell-mac-x64/chrome-headless-shell'
  Expected in: '/System/Library/Frameworks/VideoToolbox.framework/Versions/A/VideoToolbox'

TROUBLESHOOTING: https://pptr.dev/troubleshooting


URL: http://127.0.0.1:8080

## What to try

- Re-run with a longer timeout: `--timeout 60000`
- The site may block headless browsers (anti-bot protection)
- Try capturing a different page on the same domain
