"""Turns a campaign brief into an editable shot plan (plain templates, no LLM)."""

GOAL_BEATS = {
    "launch": ["introduce the product in real use", "show the key feature up close", "a delighted reaction"],
    "promo": ["show the product with the offer on screen", "a social-proof moment", "a quick before-and-after feel"],
    "awareness": ["show the brand's people in their world", "a moment that shows what the brand stands for", "a warm, human reaction"],
    "event": ["show the venue and the crowd arriving", "a standout moment from the event", "friends reacting together"],
}


def make_plan(brief: dict, n_images: int) -> str:
    dur = int(brief.get("duration", 15))
    n = max(3, min(6, round(dur / 3)))
    cuts = [round(i * dur / n) for i in range(n + 1)]
    middle = GOAL_BEATS.get(brief.get("goal", "awareness"), GOAL_BEATS["awareness"])
    brand = brief.get("brand", "the brand")
    message = brief.get("message", "").strip()

    beats = ["an attention-grabbing opening shot that makes people stop scrolling"]
    beats += [middle[i % len(middle)] for i in range(n - 2)]
    beats.append(f"end card: the word {brand} on screen" + (f" with the line \"{message.rstrip('.')}\"" if message else ""))

    lines = [
        f"Vertical 9:16 {brief.get('platform', 'TikTok')} ad for {brand}. Tone: {brief.get('tone', 'playful and confident')}. "
        "Use the reference photos for the people, products, outfits and locations, and keep them consistent."
    ]
    for i, beat in enumerate(beats):
        ref = f" Draw on reference photo {i % n_images + 1}." if n_images else ""
        stop = "" if beat.endswith((".", '"')) else "."
        lines.append(f"Shot {i + 1} ({cuts[i]}-{cuts[i + 1]}s): {beat}{stop}{ref}")
    if brief.get("include"):
        lines.append(f"Must include: {brief['include'].strip()}.")
    if brief.get("avoid"):
        lines.append(f"Avoid: {brief['avoid'].strip()}.")
    lines.append("Handheld, candid, flash-photo film grain, quick cuts, upbeat music.")
    return "\n".join(lines)
