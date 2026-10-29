"""Video model registry and the brief-driven chooser.

Every number here was measured on a real Comfy Cloud run or read from the Comfy Router schema.
status: "verified" = we ran it and it worked, "listed" = in the catalog but no adapter or no test yet.
"""
from dataclasses import dataclass

SEEDANCE_DRAFT_CREDITS_PER_SECOND = 31.2  # 249 credits for 8s, 467 for 15s (480p draft)
WAN_5S_CREDITS = 105.5  # billed for one 5s 720p clip


@dataclass(frozen=True)
class VideoModel:
    id: str
    label: str
    adapter: str | None  # key into pipeline.ADAPTERS, None when not wired
    status: str
    min_s: int | None
    max_s: int | None
    max_refs: int | None
    audio: bool
    kyc: bool  # has an identity-verified likeness route
    note: str

    def cost(self, duration: int) -> int | None:
        if self.id == "seedance-2.5-draft":
            return round(duration * SEEDANCE_DRAFT_CREDITS_PER_SECOND)
        if self.id == "wan-2.7-i2v":
            return round(WAN_5S_CREDITS)
        return None


MODELS = [
    VideoModel("seedance-2.5-draft", "Seedance 2.5 (480p draft)", "seedance", "verified", 4, 30, 20, True, False,
               "Many reference photos, up to 30s, generated sound. Draft first, cheap. Accepted real-looking photos in our runs."),
    VideoModel("wan-2.7-i2v", "Wan 2.7 image-to-video", "wan", "verified", 5, 5, 1, False, False,
               "One photo becomes a short silent clip. Verified at 5s only."),
    VideoModel("seedance-2.0-real-human", "Seedance 2.0 real-human (KYC)", None, "listed", 4, 15, None, True, True,
               "Selfie becomes a verified ByteDance asset, then is referenced as @asset_1. Template exists, adapter not written."),
    VideoModel("kling-v3-omni", "Kling v3 omni", None, "listed", None, None, None, True, False,
               "Router lists image and video inputs. Not tested."),
    VideoModel("veo-3.1", "Veo 3.1", None, "listed", None, None, None, True, False,
               "Router lists image and video inputs. Not tested."),
    VideoModel("grok-imagine-video-1.5", "Grok Imagine Video 1.5", None, "listed", None, None, None, False, False,
               "Router lists a first-frame image and reference images. Not tested."),
]
BY_ID = {m.id: m for m in MODELS}


def _checks(m: VideoModel, brief: dict, n_images: int) -> tuple[list[dict], bool]:
    """Returns (checks, eligible). A failed hard check makes the model ineligible."""
    duration = int(brief.get("duration", 15))
    checks, eligible = [], True

    def add(ok, text, hard=True):
        nonlocal eligible
        checks.append({"ok": ok, "text": text, "hard": hard})
        if hard and not ok:
            eligible = False

    add(m.adapter is not None, "Adapter is wired up" if m.adapter else "No adapter written yet")
    if m.min_s is not None and m.max_s is not None:
        add(m.min_s <= duration <= m.max_s, f"Length {duration}s fits its {m.min_s}-{m.max_s}s range" if m.min_s <= duration <= m.max_s
            else f"Length {duration}s is outside its {m.min_s}-{m.max_s}s range")
    if m.max_refs is not None:
        if n_images <= m.max_refs:
            add(True, f"Uses all {n_images} photo{'s' if n_images != 1 else ''}")
        else:
            add(False, f"Takes {m.max_refs} photo, you gave {n_images}: the rest would be ignored", hard=False)
    if brief.get("needs_audio", True):
        add(m.audio, "Generates sound" if m.audio else "No generated sound, and the brief needs it")
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
    ranking = []
    for m in MODELS:
        checks, eligible = _checks(m, brief, n_images)
        cost = m.cost(duration)
        score = 0.0
        if eligible:
            score = 100 + (10 if m.status == "verified" else 0)
            score += 20 if (m.max_refs is None or n_images <= m.max_refs) else 0
            score -= (cost or 0) / 10  # cheaper wins among models that fit
        ranking.append({"id": m.id, "label": m.label, "status": m.status, "note": m.note, "eligible": eligible,
                        "score": round(score, 1), "cost": cost, "checks": checks})
    ranking.sort(key=lambda r: (not r["eligible"], -r["score"]))
    best = ranking[0]
    if not best["eligible"]:
        return {"model": None, "label": None, "reasons": ["No model fits this brief."], "ranking": ranking, "cost": None}
    others = [r for r in ranking[1:] if r["eligible"]]
    reasons = [c["text"] for c in best["checks"] if c["ok"]]
    if others:
        reasons.append(f"Beat {others[0]['label']} on score ({best['score']} vs {others[0]['score']})")
    return {"model": best["id"], "label": best["label"], "reasons": reasons, "ranking": ranking, "cost": best["cost"]}
