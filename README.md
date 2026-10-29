# Reelmatch ♡

Describe your campaign with a few taps, drop in photos, and get a vertical UGC-style ad draft. Reelmatch scores every video model
against your brief, picks the one that fits, shows its reasoning, and renders the draft through Comfy Cloud.

Built for the Comfy "Open Source Higgsfield" build night. Themed after Soraa, with a little game on top.

## What you can do

- **Build a campaign with buttons**: product-only or people ads, goal, platform, length, sound, style, camera, setting, audience, call to action, coin budget. Text boxes are only for describing things.
- **Add media**: photos (the cast), a reference video, your own music, and your own voice.
- **Get a script** sized to your ad length, then read it aloud into the built-in recorder (or upload a recording). Your voice becomes the ad's voiceover, with music ducking underneath it.
- **Extend or edit a clip** you already have (Seedance 2.5).
- **See why a model was chosen**: every model gets a card with rules, evidence and a lock if it cannot do the job.
- **Play along**: Ad Power meter, unlockable badges, a four-level quest track and confetti when a draft finishes.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # paste your Comfy API key after COMFY_API_KEY=
.venv/bin/python -m app.server
```

Open http://localhost:8000. Make a key at https://platform.comfy.org/profile/api-keys in a workspace that has credits.

**Try it free:** `REELMATCH_MOCK=1 .venv/bin/python -m app.server` runs the whole flow without calling Comfy. A badge at the top always says MOCK or LIVE.

**Tests:** `.venv/bin/python -m unittest discover -s tests -t .`

## How the model gets chosen

`app/registry.py` checks every model against the brief and returns a pass or fail per rule: adapter wired up, open weights (if asked), length range,
photo count, sound, real faces (people ads only), identity-verified likeness, reference video and what to do with it, credit budget.
Models that pass are ranked (verified over untested, uses all photos, cheaper first). Product-only ads skip the likeness rules.

| Model | Status | Fits |
|---|---|---|
| Seedance 2.5 (480p draft) | verified | many photos, 4-30s, sound, reference video and audio, extend and edit, about 31 coins per second |
| Wan 2.7 image-to-video | verified | one photo, 5s, silent, about 106 coins |
| MiniMax H3 (open weights), LTX-2.5, Kling 4.0, Veo 3.1, Pruna P-Video 2, FLUX 3 Max, Grok Imagine Lite, HeyGen, Seedance 2.0 real-human (KYC) | listed | not wired up yet |

Prices for the two wired models come from real billing records. See `docs/MODEL_RESEARCH.md` for sources, caveats and how scores are weighted.

## Voice, music and video

- Your voiceover and music are mixed into the finished video with ffmpeg (bundled via `imageio-ffmpeg`), so they work with every model.
  With both, the music ducks while you speak. The voice is padded so the music never cuts off.
- Models that accept reference video or audio (Seedance 2.5) also receive them as references for motion, style and rhythm. Reference clips are trimmed to 15 seconds.
- Scripts are plain templates sized to your ad length (about 2.4 words per second). No AI service or extra key is needed.
- Recording happens in your browser and needs microphone permission.

## What is in the box

- `app/options.py`: the one list of buttons and dropdowns. The page builds itself from it and the server validates against it.
- `app/registry.py`: models, evidence and the chooser. `app/planner.py`: shot plans. `app/script.py`: voiceover scripts.
- `app/media.py`: file checks, trimming, mixing and stitching. `app/pipeline.py`: one adapter per model, job history, plain-English errors.
- `app/server.py`: a standard-library web server on localhost with input validation. `app/static/index.html`: the whole UI.

Safety: uploads must be real JPG/PNG/WebP, MP4/MOV/WebM or MP3/WAV/M4A of sensible size; generating needs a rights checkbox and an exact coin confirmation;
each job has a credit limit (`REELMATCH_MAX_CREDITS`, default 600); the server only listens on localhost.

## Likeness

The form requires confirmation that you own the photos, or everyone shown has agreed to their use. Seedance also has a verified-likeness route
(a selfie becomes a verified ByteDance asset). The checkbox exists, but that route is not wired up yet, so ticking it tells you no model fits.

## Honest limits

- Drafts only (480p for Seedance). A 1080p final from the draft is not built.
- Seedance and Wan are partner APIs through Comfy, so this build is not open-weights. MiniMax H3 has open weights, but a third-party analysis says its license excludes the US. Check the license.
- Only Seedance 2.5 and Wan 2.7 have adapters. The rest are listed so the chooser can explain why they are out.
- Run live and tested: generating from photos. Built from the node spec but **not yet run live**: sending reference video or audio to Seedance, extend and edit.
  Mixing, stitching, scripts and the recorder's WAV conversion are tested offline. The microphone itself needs a human and a browser permission.

MIT licensed.
