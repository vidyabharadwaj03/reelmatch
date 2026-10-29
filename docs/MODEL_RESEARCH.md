# Model research

How the chooser's rules were set, what each claim rests on, and how far to trust it.
Researched Oct 28, 2026. Reddit was not reachable from the search tool, so no Reddit threads are included.
If you have a good thread, add it here.

## Evidence labels

| Label | Meaning |
|---|---|
| ran | We ran it on a real Comfy Cloud job and looked at the output. |
| comfy | Stated in Comfy's docs, templates, model catalog or credit estimator. |
| blog | A web article or forum post. Many are written by companies that sell these models. Directional only. |

## What we measured (ran)

| Model | Result | Cost |
|---|---|---|
| Seedance 2.5 draft, reference-to-video | Accepted five real-person photos. Outfits, props and sign text held across 15s, with sound. | 249 credits for 8s, 467 for 15s (480p) |
| Wan 2.7 image-to-video | Animated one generated still into a 5s 720p clip. Silent. | 105.5 credits |
| FLUX 3 image | Multi-reference still from five photos. | 14.5 credits |

Seedance refused the same photos when called directly through the Router with a first frame, and Comfy's template route accepted them.
Treat any single refusal as route-specific, not as a model-wide rule.

## What Comfy says (comfy)

- Seedance 2.0/2.5 reference-to-video templates take plain photos. A separate `real_human` route needs one liveness check per real-person portrait.
- Veo 3.1 durations are 4, 6 or 8 seconds. LTX 2.5 Fast reaches 20s. Kling durations run 3-15s. Seedance 2.5 reaches 30s.
- Estimator prices for template defaults (not per-second): Grok Imagine 1.5 Lite 33, Pruna P-Video 2 38, HeyGen reference-to-video 45, FLUX 3 Max image-to-video 64, Kling 4.0 237, Seedance 2.0 real-human 352.
- MiniMax H3 and LTX-2.5 templates run on Comfy GPUs with no partner API node, and are the most-used video templates on Comfy Cloud.
  H3 reference-to-video takes up to nine images, three videos and three audio clips.

## What the web says (blog), and the caveats

- Kling: recommended first for ecommerce ads and consistent clips (Magic Hour, Zeely).
- Veo 3.1: favoured for hero shots and close-up detail, but expensive for testing many hooks (Zeely and others).
- Seedance 2.0: called best for commercial content, with low distortion on character scenes (Pixo, Vo3). Accepts the most reference images.
- No head-to-head test of label-text or perfume-bottle fidelity was found. For a product ad, run the same brief through two or three models and check that the shape, label and color hold across frames.
- Real faces: every provider restricts real-person photos. Seedance has a verification route. One forum thread reports Veo rejecting a consenting founder's photos.
  A claim that Kling has a face-model feature could not be confirmed.

## Video and audio inputs

- Seedance 2.5 reference-to-video: up to 20 images, 6 video clips and 6 audio clips (Comfy template description). The node spec shows `model.reference_videos.video_N` and `model.reference_audios.audio_N` slots, and a `task_type` of reference, edit or extend.
  Edit and extend are not used yet, but they would let a brand change or lengthen a clip it already has.
- MiniMax H3 and HeyGen reference-to-video: up to 3 videos and 3 audio clips (Comfy template descriptions).
- Audio references steer rhythm and sound. They do not guarantee a specific song appears, so Collab Studio mixes the brand's own track into the finished video itself.
- Not yet checked: the size, length and resolution limits Seedance puts on reference videos.

## MiniMax H3 and the Open Weights Only prize

- Open weights were released Aug 3, 2026 with native ComfyUI support. The open release is the 768p base model, not the 2K API version.
- A third-party analysis (NYU Shanghai RITS) says the license excludes the US, EU, UK and South Korea from its grant of rights.
  That has not been checked against the license text. Read the LICENSE in the model repo before building a submission on it.

## How the chooser uses this

Hard rules (a model is out if it fails): adapter exists, open-weights if requested, length range, sound if needed, verified-likeness route if requested, credit budget.
Soft rules (shown, and they nudge the score): how many photos it can use, whether it handled real faces in our runs, product-fit notes.
Score: 100, +10 if we ran it, +20 if it uses every photo, +5 for a product-fit note on product ads, +15 for accepting real faces on people ads, minus cost/10.
These weights are judgment calls from thin evidence. They are meant to be changed as more models are tested.

## Sources

- Comfy Seedance 2.0 docs: https://docs.comfy.org/tutorials/partner-nodes/bytedance/seedance-2-0
- Comfy blog, MiniMax H3: https://blog.comfy.org/p/minimax-h3-day-0-support-in-comfyui
- NYU Shanghai RITS on the H3 license: https://rits.shanghai.nyu.edu/ai/minimax-ships-h3-weights-with-the-us-and-eu-excluded/
- Magic Hour, Kling 3.0 vs Veo 3.1: https://magichour.ai/blog/kling-30-vs-veo-31
- Zeely: https://zeely.ai/blog/?p=7620
- Pixo: https://pixo.video/blog/best-ai-video-generators
- Vo3: https://www.vo3ai.com/blog/seedance-20-vs-kling-vs-sora-vs-veo3-which-ai-video-model-wins-for-ugc-ad-produc-2026-03-08
- Google AI forum, Veo 3.1 real-person rejection: https://discuss.ai.google.dev/t/request-allowlist-access-for-veo-3-1-project-wodi-f6640/171329
