# Collab Studio

A local web app where a brand describes a campaign and drops in photos, and gets a UGC-style vertical ad draft.
Built with ComfyUI (Comfy Cloud and the Comfy SDK) for the Open Source Higgsfield build night.

1. Build the campaign with buttons and dropdowns: product or people, goal, platform, length, sound, style, camera, setting, audience, call to action, budget. Text boxes are only for describing the brand, the feeling and any must-haves.
2. Drop in photos (or point at a folder). Optionally add a reference video (to copy motion or vibe) and your own music or voiceover.
3. Collab Studio scores every video model against the brief, picks one, and shows why.
4. Edit the shot plan, confirm the credit cost, and get a 9:16 draft with audio.

First working example: five street photos for Soraa in, a 15 second ad out.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # paste your Comfy API key after COMFY_API_KEY=
.venv/bin/python -m app.server
```

Open http://localhost:8000. Make a key at https://platform.comfy.org/profile/api-keys in a workspace that has credits.

Try it without spending anything: `COLLAB_MOCK=1 .venv/bin/python -m app.server` replays a saved clip. A badge at the top of the page always says MOCK or LIVE.

Tests: `.venv/bin/python -m unittest discover -s tests -t .`

## How the model gets chosen

`app/registry.py` checks every model against the brief and returns a pass or fail for each rule:
adapter wired up, open weights (if asked), length range, how many photos it can use, sound, real faces (people ads only), identity-verified likeness, credit budget.
Product-only ads (a perfume, an oil) skip the likeness rules entirely.
Models that pass are ranked (verified over untested, uses all photos, cheaper first). The page shows the full scorecard.

| Model | Status | Fits |
|---|---|---|
| Seedance 2.5 (480p draft) | verified | many photos, 4-30s, sound, about 31 credits per second |
| Wan 2.7 image-to-video | verified | one photo, 5s, silent, about 106 credits |
| MiniMax H3 (open weights), LTX-2.5, Kling 4.0, Veo 3.1, Pruna P-Video 2, FLUX 3 Max, Grok Imagine Lite, HeyGen, Seedance 2.0 real-human (KYC) | listed | not wired up yet |

Prices for the two wired models come from real billing records. The listed models show Comfy's estimator figures and the evidence behind them.
See `docs/MODEL_RESEARCH.md` for sources, caveats and how the scores are weighted.

## What is in the box

- `app/planner.py` turns the brief into a shot-by-shot prompt (plain templates, no LLM).
- `app/options.py` is the one list of buttons and dropdowns. The page builds itself from it and the server validates against it.
- `app/registry.py` is the model list, the evidence and the chooser.
- `app/pipeline.py` has one adapter per model, saves job history to `outputs/`, and turns provider errors into plain messages.
- `app/server.py` is a standard-library web server with input validation, so nothing else to install.

Safety: photos must be real JPG, PNG or WebP under 12 MB; generating needs a permission checkbox and an exact credit confirmation;
each job has a credit limit (`COLLAB_MAX_CREDITS`, default 600); the server only listens on localhost.

## Reference video and music

- Your music is mixed into the finished video by Collab Studio (ffmpeg, looped and faded to fit), so it works with every model.
- Models that also accept audio or video references (Seedance 2.5 takes up to 6 videos and 6 audio clips) get them as references for motion, style and rhythm.
- A reference video rules out models that cannot take one. The scorecard shows this.
- Mixing is tested. Sending video and audio to Seedance is built from the node spec but has not been run live yet.

## Likeness

The form requires confirmation that you own the photos or have permission from everyone shown.
Seedance also has a verified-likeness route (a selfie becomes a verified ByteDance asset, then is used as `@asset_1`).
The checkbox exists, but that route is not wired up yet, so ticking it tells you no model fits.

## Limits

- Draft quality only (480p for Seedance). A 1080p final from the draft is not built yet.
- Seedance and Wan are partner APIs through Comfy, so this build is not open-weights.
- Only two models have adapters. The rest are listed so the chooser can explain why they are out.
- MiniMax H3 has open weights, but a third-party analysis says its license excludes the US. Check the license before relying on it.

MIT licensed.
