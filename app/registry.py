"""Video model registry and the brief-driven chooser.

Evidence labels:
  ran      - we ran it on real Comfy Cloud jobs
  comfy    - stated in Comfy's own docs, templates or price estimator
  blog     - a web article or forum post (often from vendors; directional only)
Nothing here is a benchmark. See docs/MODEL_RESEARCH.md for sources and caveats.
"""
from dataclasses import dataclass, field

SEEDANCE_DRAFT_CREDITS_PER_SECOND = 31.2  # ran: 249 credits for 8s, 467 for 15s (480p draft)
WAN_5S_CREDITS = 105.5  # ran: billed for one 5s 720p clip


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

    def cost(self, duration: int) -> int | None:
        if self.id == "seedance-2.5-draft":
            return round(duration * SEEDANCE_DRAFT_CREDITS_PER_SECOND)
        if self.id == "wan-2.7-i2v":
            return round(WAN_5S_CREDITS)
        return None


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
    VideoModel("seedance-2.0-real-human", "Seedance 2.0 real-human (KYC)", None, "listed", 4, 15, None, True, True,
               "ok", "no", "A selfie becomes a verified ByteDance asset, then is referenced as @asset_1.",
               price_note="About 352 credits for a 5s run (Comfy estimator).",
               evidence=(("comfy", "Needs one liveness verification per real-person portrait", SEEDANCE_DOCS),)),
]
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
    if brief.get("open_weights_only"):
        add(m.open_weights == "yes", "Open weights" if m.open_weights == "yes" else
            "Open-weights status unverified" if m.open_weights == "unverified" else "Partner API, not open weights")
    if m.min_s is not None and m.max_s is not None:
        fits = m.min_s <= duration <= m.max_s
        add(fits, f"Length {duration}s fits its {m.min_s}-{m.max_s}s range" if fits
            else f"Length {duration}s is outside its {m.min_s}-{m.max_s}s range")
    if m.max_refs is not None:
        if n_images <= m.max_refs:
            add(True, f"Uses all {n_images} photo{'s' if n_images != 1 else ''}")
        else:
            add(False, f"Takes {m.max_refs} photo, you gave {n_images}: the rest would be ignored", hard=False)
    if brief.get("needs_audio", True):
        add(m.audio, "Generates sound" if m.audio else "No generated sound, and the brief needs it")
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
            score += 5 if (subject == "product" and m.product_fit) else 0
            score += 15 if (subject != "product" and m.people == "ok") else 0
            score -= (cost or 0) / 10  # cheaper wins among models that fit
        ranking.append({"id": m.id, "label": m.label, "status": m.status, "note": m.note, "eligible": eligible,
                        "score": round(score, 1), "cost": cost, "checks": checks, "product_fit": m.product_fit,
                        "price_note": m.price_note, "open_weights": m.open_weights,
                        "evidence": [{"kind": k, "text": t, "url": u} for k, t, u in m.evidence]})
    ranking.sort(key=lambda r: (not r["eligible"], -r["score"]))
    best = ranking[0]
    if not best["eligible"]:
        return {"model": None, "label": None, "reasons": ["No model fits this brief."], "ranking": ranking, "cost": None}
    others = [r for r in ranking[1:] if r["eligible"]]
    reasons = [c["text"] for c in best["checks"] if c["ok"]]
    if others:
        reasons.append(f"Beat {others[0]['label']} on score ({best['score']} vs {others[0]['score']})")
    return {"model": best["id"], "label": best["label"], "reasons": reasons, "ranking": ranking, "cost": best["cost"]}
