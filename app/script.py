"""Voiceover scripts from the brief, sized to the ad's length (plain templates, no LLM)."""
import re

from .options import phrase

WORDS_PER_SECOND = 2.4  # a natural read-aloud pace
LEAD_IN_SECONDS = 1.5  # half a second before the voice starts, a beat of breathing room at the end

HOOKS = {"awareness": "Here's one to remember.", "launch": "It's finally here.", "promo": "Heads up. This one won't last.",
         "event": "Save the date."}
TIPS = [
    "Find a quiet room and turn off fans, music and notifications.",
    "Hold your phone or mic about a hand's width from your mouth, a little to the side.",
    "Smile while you talk. It comes through in your voice.",
    "Speak a touch brighter and faster than normal conversation, and pause for a beat at the end of each line.",
    "Do two or three takes and keep the best one. Headphones help you hear yourself.",
]


def word_budget(duration: int) -> int:
    return max(6, round((max(duration, 4) - LEAD_IN_SECONDS) * WORDS_PER_SECOND))


def _words(text: str) -> int:
    return len(re.findall(r"[\w'’-]+", text))


def _clause(text: str, limit: int = 14) -> str:
    first = re.split(r"(?<=[.!?])\s", text.strip())[0].strip().rstrip(".!?")
    w = first.split()
    return " ".join(w[:limit]).rstrip(",;:")


def _fit(parts: list[tuple[str, bool]], budget: int) -> str:
    """Drop optional lines (last first) until the script fits the budget. Required lines are never dropped, only shortened."""
    kept = list(parts)
    while sum(_words(t) for t, _ in kept) > budget:
        optional = [i for i, (_, req) in enumerate(kept) if not req]
        if not optional:
            break
        kept.pop(optional[-1])
    text = " ".join(t for t, _ in kept)
    words = text.split()
    return text if len(words) <= budget + 2 else " ".join(words[:budget]).rstrip(",;:") + "."


def make_scripts(brief: dict) -> dict:
    duration = int(brief.get("duration", 15))
    budget = word_budget(duration)
    brand = brief.get("brand", "us")
    desc = _clause(brief.get("description", ""))
    message = brief.get("message", "").strip()
    cta = phrase("cta", brief.get("cta", "none"))
    audience = phrase("audience", brief.get("audience", "everyone"))
    goal = brief.get("goal", "awareness")
    msg = (message.rstrip(".!?") + ".") if message else ""
    cta_line = f"{cta}." if cta else ""
    aud = f"If you're {audience}, listen up." if brief.get("audience", "everyone") != "everyone" else ""

    variants = {
        "Hook first": [(aud or HOOKS.get(goal, HOOKS["awareness"]), False), (f"{brand}: {desc}." if desc else f"This is {brand}.", True),
                       (msg, True), (cta_line, True)],
        "Story": [("Picture this.", False), (f"{desc}." if desc else "", False), (f"That's {brand}.", True), (msg, True), (cta_line, True)],
        "Straight talk": [(f"{brand}.", True), (msg, True), (f"{desc}." if desc else "", False), (cta_line, True)],
    }
    scripts = []
    for title, parts in variants.items():
        parts = [(t, r) for t, r in parts if t.strip()]
        text = _fit(parts, budget)
        n = _words(text)
        scripts.append({"title": title, "text": text, "words": n, "seconds": round(n / WORDS_PER_SECOND + LEAD_IN_SECONDS, 1)})
    return {
        "budget_words": budget, "duration": duration, "scripts": scripts, "tips": TIPS,
        "prompt": f"Read it out loud at a natural pace. Aim for about {budget} words, which fills a {duration}-second ad. "
                  "Start after a half-second of quiet.",
    }
