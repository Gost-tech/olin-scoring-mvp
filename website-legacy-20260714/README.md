# Olin public website

This is a dependency-free static website. It is intentionally separate from the protected analyst application.

## Local preview

```bash
python3 -m http.server 8001 --bind 127.0.0.1 --directory website
```

Open `http://127.0.0.1:8001/`.

## Demo URL configuration

`config.js` is ignored so each environment can point to its own analyst demo without changing the public source.

Create it from the example:

```bash
cp website/config.example.js website/config.js
```

Then set:

```js
const OLIN_DEMO_URL = "https://your-authenticated-demo.example";
```

If `config.js` is absent or the URL is invalid, the website stays usable and changes the demo CTA into a link to the illustrative decision explorer.

Do not publish a raw local or unauthenticated analyst server. Use an authenticated HTTPS gateway and a demo database with fictional records only.

## Current preview assets

- `olin-public-desktop-v2.png`
- `olin-public-mobile-v2.png`
- `olin-console-desktop-v2.png`

These are visual QA captures, not merchant or performance evidence.
