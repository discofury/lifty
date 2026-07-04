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
2. The server extracts up to 16 evenly spaced frames with `ffmpeg` and downsizes them.
3. The frames — labelled with timestamps — go to **Claude Opus 4.8** together with a coaching system prompt and a lift-specific technical checklist.
4. Feedback streams back to your phone as it's written, formatted for reading during a rest period.
5. The app remembers the last feedback per lift for your browser session, so the next analysis checks whether you actually acted on the previous cue.

No database, no accounts — one Python process.

## Requirements

- An **Anthropic API key** ([get one here](https://platform.claude.com/)) exported as `ANTHROPIC_API_KEY`
- **Python 3.10+** and **ffmpeg** (or just Docker, which bundles both)

---

## Deploying

### Option 1 — Run locally, use from your phone over Wi-Fi (simplest)

Works when your phone and the machine running Lifty are on the same network (home gym, or a laptop you bring to the gym).

```bash
git clone <this-repo> && cd lifty
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# macOS: brew install ffmpeg   |   Debian/Ubuntu: sudo apt install ffmpeg

export ANTHROPIC_API_KEY=sk-ant-...
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Find your machine's LAN IP (`ipconfig getifaddr en0` on macOS, `hostname -I` on Linux), then on your iPhone open:

```
http://<your-lan-ip>:8000
```

Tap the share button in Safari → **Add to Home Screen** to make it feel like an app. Video upload via the file picker works fine over plain HTTP — no certificate needed.

### Option 2 — Docker

```bash
docker build -t lifty .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... lifty
```

Then open `http://<host-ip>:8000` on your phone.

### Option 3 — Home server + Tailscale (use it at any gym, over cellular)

The best setup for a commercial gym: run Lifty on a machine at home and reach it securely from your phone anywhere, with zero exposed ports.

1. Run Lifty on the home machine (Option 1 or 2).
2. Install [Tailscale](https://tailscale.com) on that machine and on your iPhone, signed into the same account.
3. On your phone open `http://<machine-tailscale-name>:8000`.

This keeps your API key at home and needs no public hosting.

### Option 4 — Cloud host (Fly.io / Railway / any VPS)

The repo's Dockerfile deploys anywhere that runs containers.

**Fly.io:**

```bash
fly launch --no-deploy          # accept defaults; it detects the Dockerfile
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly deploy
```

**Railway:** create a project from the repo, set the `ANTHROPIC_API_KEY` variable, and it builds from the Dockerfile automatically.

**Any VPS:** run the Docker image behind a reverse proxy (Caddy gives you automatic HTTPS in two lines of config).

> ⚠️ A public deployment has **no authentication** — anyone with the URL can upload videos billed to your API key. Put it behind basic auth in your reverse proxy, restrict it to your IP, or prefer the Tailscale option.

### Verifying the deployment

Open `http://<host>:8000/api/health` — it reports whether `ffmpeg` is on the PATH and which model is configured. Then upload a test clip.

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
| `LIFTY_MODEL` | `claude-opus-4-8` | Claude model used for analysis. |
| `LIFTY_MAX_FRAMES` | `16` | Max frames extracted per video. |
| `LIFTY_FRAME_EDGE` | `896` | Long-edge pixel size of extracted frames. |
| `LIFTY_MAX_TOKENS` | `16000` | Response cap per analysis (cost ceiling). |

## Cost

With the defaults (16 frames at ~896 px), one analysis is roughly 10–15 k input tokens and 1–3 k output/thinking tokens — about **$0.10–0.25 per set** on Claude Opus 4.8. Fewer/smaller frames (`LIFTY_MAX_FRAMES`, `LIFTY_FRAME_EDGE`) reduce cost at the expense of temporal/spatial detail.

## Adding a lift

Add an entry to `LIFTS` in [`app/prompts.py`](app/prompts.py) with a `label` and a `standard` (the technical checklist the model assesses against). It appears in the UI automatically.
