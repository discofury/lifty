# Lifty 🏋️

Between-sets technique feedback for Olympic weightlifting, powered by Claude's vision model.

Film a set on your iPhone, upload it from your browser, and get coach-style feedback — one priority cue, what's working, what to fix — before your next set starts.

**Supported lifts:**

- Clean pull to below-knee (shin)
- Clean pull to knee
- Clean pull to mid-thigh (power position)
- Full clean pull (full extension)
- Front squat
- Romanian deadlift

## How it works

1. You record a short clip (5–30 s) of a set on your phone and upload it via the web page.
2. The server profiles the clip's motion with `ffmpeg`, trims off the idle time before and after the set (walking up, standing around), and extracts up to 12 evenly spaced frames from just the movement.
3. The frames — labelled with timestamps — go to **Claude Sonnet 5** together with a coaching system prompt and a lift-specific technical checklist.
4. Feedback streams back to your phone as it's written, formatted for reading during a rest period.
5. The app remembers the last feedback per lift for your browser session, so the next analysis checks whether you actually acted on the previous cue.

No database, no accounts — one Python process.

## Requirements

- An **Anthropic API key** ([get one here](https://platform.claude.com/)) exported as `ANTHROPIC_API_KEY`
- **Python 3.10+** and **ffmpeg** (or just Docker, which bundles both)

---

## Deploying

### Option 1 — Cloud host (recommended: works from any gym, phone only)

Deploy Lifty to a container host and use it from your phone over cellular — no laptop, no home server. The repo's Dockerfile deploys anywhere that runs containers, and these hosts give you HTTPS automatically.

Set **two** secrets: your Anthropic API key, and a `LIFTY_ACCESS_KEY` of your choosing. The access key is what stops strangers who find the URL from uploading videos billed to your API key — the first time you open the app on your phone it asks for the key, then remembers it.

**Fly.io:**

```bash
fly launch --no-deploy          # accept defaults; it detects the Dockerfile
fly secrets set ANTHROPIC_API_KEY=sk-ant-... LIFTY_ACCESS_KEY=<pick-a-long-random-string>
fly deploy
```

**Railway:** create a project from the repo, set the `ANTHROPIC_API_KEY` and `LIFTY_ACCESS_KEY` variables, and it builds from the Dockerfile automatically.

**Any VPS:** run the Docker image behind a reverse proxy with HTTPS (Caddy does this in two lines of config), with both environment variables set.

Then on your iPhone: open the app's URL in Safari, enter the access key when prompted, and tap share → **Add to Home Screen** to make it feel like a native app.

> ⚠️ Don't set `LIFTY_ACCESS_KEY` on a plain-HTTP deployment — the key would travel unencrypted. Fly.io and Railway serve HTTPS out of the box, so this only matters on a bare VPS.

### Option 2 — Home server + Tailscale (no public hosting)

If you have an always-on machine at home: run Lifty there and reach it securely from your phone anywhere, with zero exposed ports and no access key needed.

1. Run Lifty on the home machine (Option 3 or Docker, below).
2. Install [Tailscale](https://tailscale.com) on that machine and on your iPhone, signed into the same account.
3. On your phone open `http://<machine-tailscale-name>:8000`.

### Option 3 — Run locally, use over Wi-Fi (home gym)

Works when your phone and the machine running Lifty are on the same network.

```bash
git clone <this-repo> && cd lifty
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# macOS: brew install ffmpeg   |   Debian/Ubuntu: sudo apt install ffmpeg

export ANTHROPIC_API_KEY=sk-ant-...
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Find your machine's LAN IP (`ipconfig getifaddr en0` on macOS, `hostname -I` on Linux), then on your iPhone open `http://<your-lan-ip>:8000`. Video upload via the file picker works fine over plain HTTP — no certificate needed.

**Docker equivalent:**

```bash
docker build -t lifty .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... lifty
```

### Verifying the deployment

Open `https://<host>/api/health` — it reports whether `ffmpeg` is on the PATH, which model is configured, and whether access-key auth is on (`"auth": "access_key"`) or off (`"auth": "open"`). Then upload a test clip.

---

## Using it at the gym

- **Framing:** whole body **and** the full bar path in frame; film from the side or a 45° front angle, ~3–5 m away. The coach will tell you if the angle prevented an assessment.
- **Length:** trim to just the set. Clips over 2 minutes are rejected.
- **Notes:** the notes field goes straight to the coach — weight on the bar, RPE, what you were trying to fix.
- **Set-over-set:** feedback is remembered per lift for your browser session, so consecutive uploads get "did you fix the last cue?" continuity.

## Configuration

Everything is optional, set via environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** Your Anthropic API key. |
| `LIFTY_ACCESS_KEY` | *(unset — no auth)* | Shared access key. When set, every API request must present it; the web page asks once and remembers it. Set this on any public deployment. |
| `LIFTY_MODEL` | `claude-sonnet-5` | Claude model used for analysis. |
| `LIFTY_MAX_FRAMES` | `12` | Max frames extracted per video. |
| `LIFTY_FRAME_EDGE` | `768` | Long-edge pixel size of extracted frames. Image tokens scale with pixel area. |
| `LIFTY_EFFORT` | `medium` | Thinking/output spend: `low`, `medium`, or `high`. `medium` reviews a set well; `high` digs deeper at higher cost. |
| `LIFTY_TRIM` | `1` | Motion-trim the clip before frame extraction. Set `0` to always sample the whole clip. |
| `LIFTY_MAX_TOKENS` | `16000` | Response cap per analysis (cost ceiling). |

## Cost

With the defaults (motion trim + 12 frames at ~768 px + `medium` effort), one analysis is roughly 6–9 k input tokens and 1–2 k output/thinking tokens — about **$0.03–0.06 per set** on Claude Sonnet 5 ($3/$15 per Mtok; introductory $2/$10 pricing through 2026-08-31 makes it cheaper still).

Tuning knobs, in order of impact:

- **Trim your clips** (or let motion trim do it) — frames spent on walking up to the bar are pure waste.
- `LIFTY_FRAME_EDGE` — token cost per frame scales with pixel **area**, so 640 px costs ~30% less than 768 px.
- `LIFTY_MAX_FRAMES` — fewer frames, less temporal detail across the reps.
- `LIFTY_EFFORT=low` — cheapest feedback; fine for quick checks.
- `LIFTY_MODEL=claude-opus-4-8` — the other direction: a stronger, pricier model tier ($5/$25 per Mtok) if you want the deepest analysis.

## Adding a lift

Add an entry to `LIFTS` in [`app/prompts.py`](app/prompts.py) with a `label` and a `standard` (the technical checklist the model assesses against). It appears in the UI automatically.
