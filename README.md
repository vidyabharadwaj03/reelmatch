# Reelmatch ♡

Describe your campaign with a few taps, drop in photos, and press one button to get a vertical UGC-style ad draft.
Reelmatch picks the video model for you behind the scenes and renders the draft through Comfy Cloud.
If you are curious, "Why this model?" shows how every model scored, and you can switch to any model that can do the job.

Built for the Comfy "Open Source Higgsfield" build night. Themed after Soraa, with a little game on top.

## What you can do

- **Two simple steps**: your campaign, then your photos. A bar at the bottom always shows the model that was picked and about what it will cost.
- **Build a campaign with buttons**: product-only or people ads, goal, platform, length, sound, style, camera, setting, audience, call to action, coin budget. Text boxes are only for describing things.
- **Add media**: photos (the cast), a reference video, your own music, and your own voice.
- **Get a script** sized to your ad length, then read it aloud into the built-in recorder (or upload a recording). Your voice becomes the ad's voiceover, with music ducking underneath it.
- **Extend or edit a clip** you already have (Seedance 2.5).
- **See why a model was chosen, and change it**: every model has a card with its rules and evidence, and models that cannot do the job say why.

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
| Seedance 2.5 (480p draft) | tested, 5 photos and 15s | many photos, 4-30s, sound, reference video and audio, extend and edit, about 31 credits per second |
| MiniMax H3 (open weights) | tested, 2 photos and 5s | up to 9 photos as cuts, 2-15s, sound, runs on Comfy GPUs |
| LTX-2.5 (open weights) | tested, 1 photo and 5s | one photo, 2-20s, sound, runs on Comfy GPUs |
| Grok Imagine 1.5 Lite | tested, 1 photo and 5s | one photo, 1-15s, sound, about 10 credits per second |
| Pruna P-Video 2 | tested, 1 photo and 5s | two photos (first and last frame), 1-20s, sound, about 5 credits per second |
| FLUX 3 Max | tested, 1 photo and 5s | up to 10 photos as keyframes, 5-20s, sound, about 13 credits per second |
| HeyGen Video 1.0 | tested, 1 photo and 5s | up to 9 photos, 5-15s, sound, about 6 credits per second at 480p |
| Veo 3.1 Fast | tested, 1 photo and 4s | one photo, 4-8s, sound, about 21 credits per second |
| Wan 2.7 | tested, 1 photo and 5s | one photo, 5s, silent, about 106 credits |
| Kling 4.0 | wired, not tested | up to 10 keyframes, 3-30s, sound, about 47 credits per second |
| Seedance with a verified person | wired, not run | a person verifies once, then appears as themselves |

A model is only picked automatically when the brief is inside what we have actually tested. You can still choose any other model that fits from "Why this model?".
Prices come from real billing records. Kling's is Comfy's estimate until it is tested, and the open-weights models run on Comfy's GPUs, so their credit cost is a rough estimate (a 5 second clip used 18 to 47 GPU-seconds). See `docs/MODEL_RESEARCH.md` for sources, caveats and how scores are weighted.

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

The form requires confirmation that you own the photos, or everyone shown has agreed to their use.

For a real person who must look like themselves, use **verified people** (Seedance with ByteDance's real-person check):
1. In step 2, open "Put a verified person in your ad" and press Verify a person.
2. Choose a clear photo of their face and confirm the consent box. The photo is sent to Comfy, and from there to ByteDance.
3. You get a link. The person opens it on their own phone and does a short liveness check. Reelmatch never sees that video.
4. Two ids come back and are saved on your computer only (`outputs/likeness.json`, never committed). The person never has to verify again.

Tick a verified person in any ad and the app routes to Seedance with that identity attached (`@asset_1` in the prompt).
Verification needs live mode. This route has been wired and tested offline, but a real verification has not been run end to end yet.

## Honest limits

- Drafts only (480p for Seedance). A 1080p final from the draft is not built.
- Seedance and Wan are partner APIs through Comfy, so this build is not open-weights. MiniMax H3 has open weights, but a third-party analysis says its license excludes the US. Check the license.
- Kling 4.0 is wired but not yet run, and verified people has not been run end to end with a real verification.
- Open weights: LTX-2.5 and MiniMax H3 run from model files on Comfy's GPUs with no partner API. H3's license reportedly excludes the US, and LTX's license has not been reviewed. Check both before relying on them.
- The chooser prefers open-weights models by a small margin when quality looks comparable.
- Run live and tested: generating from photos. Built from the node spec but **not yet run live**: sending reference video or audio to Seedance, extend and edit.
  Mixing, stitching, scripts and the recorder's WAV conversion are tested offline. The microphone itself needs a human and a browser permission.

The look follows Soraa's own site: plum, cream and lime, with Syne and Inter loaded from Google Fonts (they fall back to system fonts offline).
Icons are inline line icons in the Lucide style (ISC license). No emojis.

MIT licensed.
