"""Video model registry and the brief-driven chooser.

Evidence labels:
  ran      - we ran it on real Comfy Cloud jobs
  comfy    - stated in Comfy's own docs, templates or price estimator
  blog     - a web article or forum post (often from vendors; directional only)
Nothing here is a benchmark. See docs/MODEL_RESEARCH.md for sources and caveats.
"""
from dataclasses import dataclass, field, replace

SEEDANCE_DRAFT_CREDITS_PER_SECOND = 31.2  # ran: 249 credits for 8s, 467 for 15s (480p draft)
WAN_5S_CREDITS = 105.5  # ran: billed for one 5s 720p clip
# Credits per second of output. Seedance is billed. The rest are Comfy's estimator for our exact settings, assumed linear in length.
PER_SECOND = {"seedance-2.5-draft": SEEDANCE_DRAFT_CREDITS_PER_SECOND, "grok-imagine-1.5-lite": 9.66, "pruna-p-video-2": 4.53,
              "flux-3-max-i2v": 12.82, "kling-4-i2v": 47.4, "heygen-video-1-r2v": 6.03, "veo-3.1": 21.1,
              "ltx-2.5-i2v": 1.0, "minimax-h3-r2v": 2.0,
              "seedance-2.0-real-human": SEEDANCE_DRAFT_CREDITS_PER_SECOND}  # assumed same price as the normal Seedance draft until run  # LTX runs on Comfy GPUs: 18 GPU-seconds for 5s, credits not itemized, so this is a rough estimate


@dataclass(frozen=True)
class VideoModel:
    id: str
    label: str
    adapter: str | None  # key into pipeline.ADAPTERS, None when not wired
    status: str  # "verified" (we ran it) or "listed"
    min_s: int | None
    max_s: int | None
    max_refs: int | None
    audio: bool
    kyc: bool  # has an identity-verified likeness route
    people: str  # real faces: "ok" (worked in our runs), "unknown", "reported-strict"
    open_weights: str  # "yes", "unverified", "no"
    note: str
    product_fit: str = ""
    price_note: str = ""
    evidence: tuple = field(default_factory=tuple)  # (label, text, url)
    video_refs: int = 0  # reference videos it accepts
    audio_refs: int = 0  # reference audio clips it accepts
    video_modes: tuple = ()  # what it can do with a reference video: reference, extend, edit
    tested_refs: int = 1  # most photos we have run it with
    tested_s: int = 5  # longest clip we have run
    taste: int = 0  # our judgement of output quality from our own runs, -5 to +15

    def cost(self, duration: int) -> int | None:
        if self.id == "wan-2.7-i2v":
            return round(WAN_5S_CREDITS)
        rate = PER_SECOND.get(self.id)
        if rate is None:
            return None
        if self.id == "veo-3.1":  # Veo renders 4, 6 or 8 second clips
            duration = min((4, 6, 8), key=lambda s: abs(s - duration))
        return round(duration * rate)


COMFY_BLOG_H3 = "https://blog.comfy.org/p/minimax-h3-day-0-support-in-comfyui"
NYU_H3 = "https://rits.shanghai.nyu.edu/ai/minimax-ships-h3-weights-with-the-us-and-eu-excluded/"
PIXO = "https://pixo.video/blog/best-ai-video-generators"
VO3 = "https://www.vo3ai.com/blog/seedance-20-vs-kling-vs-sora-vs-veo3-which-ai-video-model-wins-for-ugc-ad-produc-2026-03-08"
ZEELY = "https://zeely.ai/blog/?p=7620"
MAGIC_HOUR = "https://magichour.ai/blog/kling-30-vs-veo-31"
SEEDANCE_DOCS = "https://docs.comfy.org/tutorials/partner-nodes/bytedance/seedance-2-0"
VEO_FORUM = "https://discuss.ai.google.dev/t/request-allowlist-access-for-veo-3-1-project-wodi-f6640/171329"

MODELS = [
    VideoModel("seedance-2.5-draft", "Seedance 2.5 (480p draft)", "seedance", "verified", 4, 30, 20, True, False,
               "ok", "no", "Many reference photos, up to 30s, generated sound. Draft first, then approve.",
               product_fit="Up to 20 reference photos can hold a product's shape. Blogs call Seedance strong for commercial and lifestyle ads.",
               price_note="About 31 credits per second at 480p (measured).",
               evidence=(("ran", "Accepted five real-person photos and kept outfits and sign text across 15s", ""),
                         ("blog", "Pixo calls Seedance 2.0 the best model for commercial content", PIXO),
                         ("blog", "Vo3 reports low distortion and good motion consistency on character scenes (Seedance 2.0)", VO3))),
    VideoModel("wan-2.7-i2v", "Wan 2.7 image-to-video", "wan", "verified", 5, 5, 1, False, False,
               "unknown", "no", "One photo becomes a short silent clip. Verified at 5s only.",
               product_fit="Single first frame, so the product stays as photographed. Silent.",
               price_note="About 106 credits for a 5s 720p clip (measured).",
               evidence=(("ran", "Animated a generated still into a 5s clip in about 30 seconds", ""),)),
    VideoModel("minimax-h3-r2v", "MiniMax H3 reference-to-video", None, "listed", None, None, 9, True, False,
               "unknown", "yes", "Up to nine reference images, three videos and three audio clips. Runs on Comfy GPUs.",
               product_fit="Multi-reference with open weights, the one route to a multi-photo ad under the Open Weights Only prize.",
               price_note="No API credits. GPU time is billed separately and not estimated here.",
               evidence=(("comfy", "Open weights released Aug 3, 2026 with native ComfyUI support; open release is the 768p base model", COMFY_BLOG_H3),
                         ("blog", "License reportedly excludes the US, EU, UK and South Korea. Read the license before relying on it", NYU_H3),
                         ("comfy", "Most-used video template on Comfy Cloud (about 7.9k runs for reference-to-video)", ""))),
    VideoModel("ltx-2.5-i2v", "LTX-2.5 image-to-video", None, "listed", None, 20, 1, True, False,
               "unknown", "unverified", "One photo in, up to 20s on the Fast tier. Runs on Comfy GPUs without an API node.",
               product_fit="Single first frame. Template advertises multishot consistency.",
               price_note="No API credits. GPU time is billed separately and not estimated here.",
               evidence=(("comfy", "Template runs with no partner API node, which suggests local weights. Not confirmed", ""),)),
    VideoModel("kling-4-i2v", "Kling 4.0 image-to-video", None, "listed", None, None, 1, True, False,
               "unknown", "no", "Animates one still into a five-second clip with three cuts.",
               product_fit="Reviews say Kling holds product copy and suits ecommerce ads. No head-to-head test found.",
               price_note="About 237 credits for the template default (Comfy estimator).",
               evidence=(("blog", "Magic Hour recommends Kling 3.0 for fast, consistent ad and UGC clips", MAGIC_HOUR),
                         ("blog", "Zeely suggests starting with Kling for most ecommerce advertisers", ZEELY))),
    VideoModel("veo-3.1", "Veo 3.1", None, "listed", 4, 8, 1, True, False,
               "reported-strict", "no", "Clips of 4, 6 or 8 seconds. Polished hero shots with camera control.",
               product_fit="Blogs favour Veo for close-up detail and hero shots, but it is pricey for volume.",
               price_note="Not priced by Comfy's estimator here. Blogs describe it as the priciest option for volume (unverified).",
               evidence=(("comfy", "Durations of 4, 6 or 8 seconds; 4k on two tiers", ""),
                         ("blog", "Zeely suggests starting with Veo for brand campaigns", ZEELY),
                         ("blog", "A creator reported a usage-guidelines rejection on a consenting founder's photos", VEO_FORUM))),
    VideoModel("pruna-p-video-2", "Pruna P-Video 2", None, "listed", 1, 20, 1, False, False,
               "unknown", "no", "Quality-focused image-to-video, 1-20s, 720p or 1080p.",
               product_fit="Template says it excels at identity consistency and subtle, natural motion.",
               price_note="About 38 credits for the template default (Comfy estimator).",
               evidence=(("comfy", "Template description and estimator", ""),)),
    VideoModel("flux-3-max-i2v", "FLUX 3 Max image-to-video", None, "listed", None, None, 1, True, False,
               "unknown", "no", "Animates one still, built for product shots and portraits.",
               product_fit="Template says it is ideal for bringing product shots to life.",
               price_note="About 64 credits for the template default (Comfy estimator).",
               evidence=(("comfy", "Template description and estimator", ""),)),
    VideoModel("grok-imagine-1.5-lite", "Grok Imagine Video 1.5 Lite", None, "listed", None, 15, 1, True, False,
               "unknown", "no", "Fast, low-cost image-to-video, up to 15s and 1080p.",
               product_fit="Cheap way to test hooks before spending on a polished model.",
               price_note="About 33 credits for the template default (Comfy estimator).",
               evidence=(("comfy", "Template description and estimator", ""),)),
    VideoModel("heygen-video-1-r2v", "HeyGen Video 1.0 reference-to-video", None, "listed", 5, 15, 9, True, False,
               "unknown", "no", "Dialogue and sound from a prompt plus up to nine images.",
               product_fit="",
               price_note="About 45 credits for the template default (Comfy estimator).",
               evidence=(("comfy", "Template description and estimator", ""),)),
    VideoModel("seedance-2.0-real-human", "Seedance with a verified person", None, "listed", 4, 15, None, True, True,
               "ok", "no", "A person verifies once with ByteDance (a short liveness check on their phone), then can appear in any ad as @asset_1.",
               price_note="About 352 credits for a 5s run (Comfy estimator).",
               evidence=(("comfy", "Needs one liveness verification per real-person portrait", SEEDANCE_DOCS),)),
]
# Reference video and audio inputs. Comfy's Seedance 2.5 template says 6 clips each, third-party docs for Seedance 2.0 say 3.
# We cap at 3 until confirmed. Edit and extend come from the Seedance node's task_type.
_MEDIA = {
    "seedance-2.5-draft": (3, 3, ("reference", "extend", "edit"),
                           ("comfy", "Reference-to-video takes images, video clips and audio clips; node task types are reference, edit and extend. Comfy's template says 6 clips each, other docs say 3, so we send at most 3", "")),
    "minimax-h3-r2v": (0, 0, ("reference",), ("comfy", "Template takes up to 3 videos and 3 audio clips; our adapter does not send them yet", "")),
    "heygen-video-1-r2v": (0, 0, ("reference",), ("comfy", "Node takes up to 3 videos and 3 audio clips; our adapter does not send them yet", "")),
}
MODELS = [replace(m, video_refs=_MEDIA[m.id][0], audio_refs=_MEDIA[m.id][1], video_modes=_MEDIA[m.id][2], evidence=m.evidence + (_MEDIA[m.id][3],))
          if m.id in _MEDIA else m for m in MODELS]
# Results of our live runs: same photo, same prompt, 5s (Veo 4s). One run each, so treat as a first look, not a benchmark.
_RAN = {
    "grok-imagine-1.5-lite": dict(audio=True, taste=8, evidence=(("ran", "Followed the prompt best: the friends leaned in and laughed and the sign stayed readable. 37s to render, billed 48.3 credits", ""),)),
    "pruna-p-video-2": dict(taste=-3, evidence=(("ran", "Cheapest at 22.6 credits and 27s, but the sign was lost when the friends turned away", ""),)),
    "flux-3-max-i2v": dict(taste=3, evidence=(("ran", "Most faithful to the photo with only gentle motion. 21s to render, billed 64.1 credits", ""),)),
    "veo-3.1": dict(taste=2, tested_s=4, evidence=(("ran", "Re-imagined the street and framing noticeably; sign stayed readable. 4s clip, 53s to render, billed 84.4 credits", ""),)),
    "ltx-2.5-i2v": dict(taste=6, evidence=(("ran", "Open weights on Comfy GPUs. Vertical, lively, and the sign text stayed readable. 26s to render, about 18 GPU-seconds, credits not itemized", ""),)),
    "minimax-h3-r2v": dict(taste=6, tested_refs=2, evidence=(("ran", "Open weights on Comfy GPUs. Two photos became two cuts (friends with the sign, then the man with the newspaper) with people kept consistent; small text came out garbled. 59s to render, about 47 GPU-seconds", ""),)),
    "heygen-video-1-r2v": dict(taste=0, evidence=(("ran", "Capped at 480p here, 86s to render, billed 30.2 credits. The sign shrank mid-clip and returned at the end", ""),)),
}

# Wired in this build. Ranges and photo counts come from Comfy's node specs. Status stays "listed" until a live run succeeds.
_WIRED = {
    "grok-imagine-1.5-lite": dict(adapter="grok", min_s=1, max_s=15, max_refs=1, audio=False),
    "pruna-p-video-2": dict(adapter="pruna", min_s=1, max_s=20, max_refs=2, audio=True),
    "flux-3-max-i2v": dict(adapter="flux3", min_s=5, max_s=20, max_refs=10, audio=True),
    "kling-4-i2v": dict(adapter="kling4", min_s=3, max_s=30, max_refs=10, audio=True),
    "heygen-video-1-r2v": dict(adapter="heygen", min_s=5, max_s=15, max_refs=9, audio=True),
    "veo-3.1": dict(adapter="veo", min_s=4, max_s=8, max_refs=1, audio=True),
    "ltx-2.5-i2v": dict(adapter="ltx25", min_s=2, max_s=20, max_refs=1, audio=True, open_weights="yes"),
    "seedance-2.0-real-human": dict(adapter="seedance", min_s=4, max_s=30, max_refs=20),
    "minimax-h3-r2v": dict(adapter="h3", min_s=2, max_s=15, max_refs=9, audio=True, open_weights="yes"),
}
MODELS = [replace(m, **_WIRED[m.id]) if m.id in _WIRED else m for m in MODELS]
MODELS = [replace(m, status="verified", people="ok", **{k: v for k, v in _RAN[m.id].items() if k != "evidence"}, evidence=(("ran", "Accepted a real-person photo", ""),) + _RAN[m.id]["evidence"] + m.evidence)
          if m.id in _RAN else m for m in MODELS]
# What the first two verified models were tested with.
MODELS = [replace(m, tested_refs=5, tested_s=15, taste=15) if m.id == "seedance-2.5-draft" else m for m in MODELS]
BY_ID = {m.id: m for m in MODELS}


def _checks(m: VideoModel, brief: dict, n_images: int) -> tuple[list[dict], bool]:
    """Returns (checks, eligible). A failed hard check makes the model ineligible."""
    duration = int(brief.get("duration", 15))
    subject = brief.get("subject", "people")
    checks, eligible = [], True

    def add(ok, text, hard=True):
        nonlocal eligible
        checks.append({"ok": ok, "text": text, "hard": hard})
        if hard and not ok:
            eligible = False

    add(m.adapter is not None, "Adapter is wired up" if m.adapter else "No adapter written yet")
    if m.status == "verified" and m.adapter:
        if n_images > m.tested_refs:
            add(False, f"Only tested with up to {m.tested_refs} photo{'s' if m.tested_refs != 1 else ''}, you gave {n_images}", hard=False)
        if duration > m.tested_s:
            add(False, f"Only tested up to {m.tested_s}s, you asked for {duration}s", hard=False)
    if brief.get("open_weights_only"):
        add(m.open_weights == "yes", "Open weights" if m.open_weights == "yes" else
            "Open-weights status unverified" if m.open_weights == "unverified" else "Partner API, not open weights")
    if m.min_s is not None and m.max_s is not None:
        fits = m.min_s <= duration <= m.max_s
        add(fits, f"Length {duration}s fits its {m.min_s}-{m.max_s}s range" if fits
            else f"Length {duration}s is outside its {m.min_s}-{m.max_s}s range")
    if m.max_refs is not None and n_images > 0:
        if n_images <= m.max_refs:
            add(True, f"Uses all {n_images} photo{'s' if n_images != 1 else ''}")
        else:
            add(False, f"Takes {m.max_refs} photo, you gave {n_images}: the rest would be ignored", hard=False)
    n_videos, n_audio, n_voice = int(brief.get("n_videos", 0)), int(brief.get("n_audio", 0)), int(brief.get("n_voice", 0))
    mixing = (n_audio > 0 and brief.get("soundtrack", True)) or n_voice > 0
    if n_voice:
        add(True, "Your voiceover is mixed in after rendering", hard=False)
    if n_audio and brief.get("soundtrack", True):
        add(True, "Your music is mixed in as the soundtrack after rendering")
    if mixing:
        pass
    elif brief.get("needs_audio", True):
        add(m.audio, "Generates sound" if m.audio else "No generated sound, and the brief needs it")
    vmode = brief.get("video_mode", "reference")
    base = "extend" if vmode.startswith("extend") else vmode
    if n_videos and base != "reference":
        add(base in m.video_modes, f"Can {base} your video" if base in m.video_modes else f"Cannot {base} a video")
    if n_videos:
        if m.video_refs >= n_videos:
            add(True, f"Takes your reference video{'s' if n_videos > 1 else ''} (up to {m.video_refs})")
        elif m.video_refs:
            add(False, f"Takes up to {m.video_refs} reference videos, you gave {n_videos}: the rest would be ignored", hard=False)
        else:
            add(False, "Cannot take a reference video")
    if n_audio and m.audio_refs:
        add(True, "Also uses your audio as a rhythm and sound reference", hard=False)
    if subject == "product":
        add(True, "No people on screen, so likeness rules do not apply", hard=False)
    else:
        if m.people == "ok":
            add(True, "Accepted real-person photos in our runs", hard=False)
        elif m.people == "reported-strict":
            add(False, "Reported to reject real-person photos (unverified report)", hard=False)
        else:
            add(False, "Not tested with real-person photos", hard=False)
    if brief.get("verified_likeness"):
        add(m.kyc, "Has an identity-verified likeness route" if m.kyc else "No identity-verified likeness route")
    elif m.kyc:
        add(False, "Needs a verified person to be selected")
    budget = brief.get("budget")
    cost = m.cost(duration)
    if budget and cost is not None:
        add(cost <= int(budget), f"About {cost} credits, within your {budget} budget" if cost <= int(budget)
            else f"About {cost} credits, over your {budget} budget")
    return checks, eligible


def choose(brief: dict, n_images: int) -> dict:
    duration = int(brief.get("duration", 15))
    subject = brief.get("subject", "people")
    ranking = []
    for m in MODELS:
        checks, eligible = _checks(m, brief, n_images)
        cost = m.cost(duration)
        score = 0.0
        if eligible:
            score = 100 + (10 if m.status == "verified" else 0)
            score += 20 if (m.max_refs is None or n_images <= m.max_refs) else 0
            if m.max_refs is not None and n_images > m.max_refs:  # photos that would be ignored defeat the brief
                score -= min(50, 10 * (n_images - m.max_refs))
            score += 5 if (subject == "product" and m.product_fit) else 0
            score += 3 if (int(brief.get("n_audio", 0)) and m.audio_refs) else 0
            score += m.taste
            score += 4 if m.open_weights == "yes" else 0  # prefer open weights when quality is comparable
            score -= 30 if (m.status == "verified" and n_images > m.tested_refs) else 0
            score -= 15 if (m.status == "verified" and duration > m.tested_s) else 0
            score += 15 if (subject != "product" and m.people == "ok") else 0
            score -= (cost or 0) / 10  # cheaper wins among models that fit
        ranking.append({"id": m.id, "label": m.label, "status": m.status, "note": m.note, "eligible": eligible,
                        "score": round(score, 1), "cost": cost, "checks": checks, "product_fit": m.product_fit,
                        "price_note": m.price_note, "open_weights": m.open_weights,
                        "evidence": [{"kind": k, "text": t, "url": u} for k, t, u in m.evidence]})
    # Models we have actually run come first. An untested model is never picked automatically while a tested one fits.
    # It can still be chosen by hand, and it joins the automatic pool once a live run has succeeded.
    def tier(r):  # 0: tested and inside what we tested, 1: tested but outside it, 2: untested
        m = BY_ID[r["id"]]
        if m.status != "verified":
            return 2
        return 0 if (n_images <= m.tested_refs and duration <= m.tested_s) else 1

    ranking.sort(key=lambda r: (not r["eligible"], tier(r), -r["score"]))
    best = ranking[0]
    if not best["eligible"]:
        return {"model": None, "label": None, "reasons": ["No model fits this brief."], "ranking": ranking, "cost": None,
                "auto_model": None, "overridden": False}
    others = [r for r in ranking[1:] if r["eligible"]]
    reasons = [c["text"] for c in best["checks"] if c["ok"]]
    if best["status"] != "verified":
        reasons.append("No tested model fits, so this untested one was picked")
    elif tier(best) == 1:
        reasons.append("No model has been tested this far, so this is the closest tested one")
    elif others and others[0]["status"] == "verified":
        reasons.append(f"Beat {others[0]['label']} on score ({best['score']} vs {others[0]['score']})")
    elif others:
        reasons.append("Models we have run are preferred over untested ones")
    return {"model": best["id"], "label": best["label"], "reasons": reasons, "ranking": ranking, "cost": best["cost"],
            "auto_model": best["id"], "overridden": False}


def apply_override(choice: dict, model_id: str | None) -> dict:
    """Let a user switch to any model that can do the job. Models that cannot are refused with the reason."""
    if not model_id or model_id == choice["model"]:
        return choice
    r = next((x for x in choice["ranking"] if x["id"] == model_id), None)
    if r is None:
        raise ValueError("Unknown model.")
    if not r["eligible"]:
        why = next((c["text"] for c in r["checks"] if not c["ok"] and c["hard"]), "it cannot do this brief")
        raise ValueError(f"{r['label']} cannot be used here: {why}.")
    out = dict(choice)
    out.update(model=r["id"], label=r["label"], cost=r["cost"], overridden=True,
               reasons=[c["text"] for c in r["checks"] if c["ok"]] + ["You picked this model"])
    return out
