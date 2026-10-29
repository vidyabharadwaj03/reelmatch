"""Turns a campaign brief into an editable shot plan (plain templates, no LLM)."""
from .options import phrase

GOAL_BEATS = {
    "launch": ["introduce it in real use", "show the key feature up close", "a delighted reaction"],
    "promo": ["show it with the offer in mind", "a social-proof moment", "a quick before-and-after feel"],
    "awareness": ["show it in its world", "a moment that shows what the brand stands for", "a warm, human moment"],
    "event": ["show the venue and the crowd arriving", "a standout moment from the event", "friends reacting together"],
}
PRODUCT_BEATS = {
    "launch": ["slow reveal of the product", "a close-up of the label and material", "the product in a real setting"],
    "promo": ["the product front and center", "a detail shot that shows quality", "the product in use"],
    "awareness": ["a beautiful hero shot of the product", "a close-up of texture and detail", "the product in its world"],
    "event": ["the product at the event", "a close-up of detail", "the product in hands"],
}


def make_plan(brief: dict, n_images: int) -> str:
    dur = int(brief.get("duration", 15))
    subject = brief.get("subject", "people")
    n = max(3, min(6, round(dur / 3)))
    cuts = [round(i * dur / n) for i in range(n + 1)]
    goal = brief.get("goal", "awareness")
    middle = (PRODUCT_BEATS if subject == "product" else GOAL_BEATS).get(goal, GOAL_BEATS["awareness"])
    brand = brief.get("brand", "the brand")
    message = brief.get("message", "").strip().rstrip(".")
    cta = phrase("cta", brief.get("cta", "none"))

    end = f"end card: the word {brand} on screen"
    if message:
        end += f" with the line \"{message}\""
    if cta:
        end += f" and the call to action \"{cta}\""
    beats = ["an attention-grabbing opening shot that makes people stop scrolling"]
    beats += [middle[i % len(middle)] for i in range(n - 2)]
    beats.append(end)

    look = [phrase("style", s) for s in brief.get("style", []) if phrase("style", s)]
    cam = [phrase("camera", c) for c in brief.get("camera", []) if phrase("camera", c)]
    head = f"Vertical 9:16 {brief.get('platform', 'TikTok')} ad for {brand}"
    if brief.get("description"):
        head += f" ({brief['description'].strip().rstrip('.')})"
    lines = [head + f". {phrase('subject', subject).capitalize()}."]
    if subject == "product":
        lines.append("Keep the product's shape, color, label and text exactly as in the reference photos. No people on screen.")
    else:
        lines.append("Use the reference photos for the people, outfits, props and locations, and keep them consistent.")
    if phrase("setting", brief.get("setting")):
        lines.append(f"Setting: {phrase('setting', brief['setting'])}.")
    if brief.get("audience") and brief["audience"] != "everyone":
        lines.append(f"Made for {phrase('audience', brief['audience'])}.")
    if brief.get("feel"):
        lines.append(f"Viewers should feel: {brief['feel'].strip().rstrip('.')}.")
    for i, beat in enumerate(beats):
        stop = "" if beat.endswith(".") else "."
        ref = f" Draw on reference photo {i % n_images + 1}." if n_images else ""
        lines.append(f"Shot {i + 1} ({cuts[i]}-{cuts[i + 1]}s): {beat}{stop}{ref}")
    if brief.get("include"):
        lines.append(f"Must include: {brief['include'].strip().rstrip('.')}.")
    if brief.get("avoid"):
        lines.append(f"Avoid: {brief['avoid'].strip().rstrip('.')}.")
    tail = ", ".join(look + cam) or "candid, quick cuts"
    lines.append(f"Look and camera: {tail}. " + ("Upbeat music." if brief.get("needs_audio", True) else "No music."))
    return "\n".join(lines)
