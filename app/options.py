"""Every button, tab and dropdown in the brief. The page builds itself from this, and the server validates against it."""

# (value, label, phrase used in the shot plan)
SUBJECT = [("product", "Product only", "the product is the hero and no people appear"),
           ("people", "People", "people are the focus"),
           ("both", "Product + people", "people use or show off the product")]
GOAL = [("awareness", "Brand awareness", ""), ("launch", "Product launch", ""),
        ("promo", "Promo or sale", ""), ("event", "Event", "")]
PLATFORM = [("TikTok", "TikTok", ""), ("Instagram Reel", "Instagram Reel", ""), ("YouTube Short", "YouTube Short", "")]
LENGTH = [(5, "5s", ""), (8, "8s", ""), (15, "15s", ""), (20, "20s", ""), (30, "30s", "")]
STYLE = [("ugc", "UGC handheld", "authentic UGC feel"), ("cinematic", "Cinematic", "cinematic lighting and depth"),
         ("luxury", "Luxury", "slow, elegant, high-end"), ("playful", "Playful", "playful and energetic"),
         ("minimal", "Clean studio", "clean minimal studio look"), ("retro", "Retro film", "retro film grain"),
         ("bold", "Bold + colorful", "bold saturated colors")]
SETTING = [("street_night", "City street at night", "a city street at night with warm lights"),
           ("studio", "Studio", "a clean studio backdrop"), ("home", "Home", "a cozy home interior"),
           ("outdoors", "Outdoors", "natural outdoor light"), ("store", "In store", "a retail store"),
           ("abstract", "Abstract / color", "an abstract colorful backdrop")]
CAMERA = [("handheld", "Handheld", "handheld camera"), ("push_in", "Slow push-in", "slow push-in"),
          ("orbit", "Orbit", "smooth orbit around the subject"), ("macro", "Macro close-up", "macro close-ups of detail"),
          ("quick_cuts", "Quick cuts", "quick cuts"), ("static", "Locked off", "locked-off camera")]
AUDIO = [("music", "Music + sound", ""), ("silent", "Silent", "")]
BUDGET = [("", "No limit", ""), ("150", "Up to 150 credits", ""), ("300", "Up to 300 credits", ""), ("600", "Up to 600 credits", "")]
AUDIENCE = [("everyone", "Everyone", "a broad audience"), ("genz", "Gen Z", "Gen Z"), ("millennial", "Millennials", "millennials"),
            ("parents", "Parents", "parents"), ("pros", "Professionals", "working professionals")]
CTA = [("none", "No call to action", ""), ("shop", "Shop now", "Shop now"), ("learn", "Learn more", "Learn more"),
       ("follow", "Follow us", "Follow us"), ("visit", "Visit us", "Visit us"), ("book", "Book now", "Book now")]

VIDEO_MODE = [("reference", "Use as a style reference", ""), ("extend_forward", "Extend it forward", ""),
              ("extend_backward", "Extend it backward", ""), ("edit", "Edit it", "")]

GROUPS = {"video_mode": VIDEO_MODE, "subject": SUBJECT, "goal": GOAL, "platform": PLATFORM, "length": LENGTH, "style": STYLE, "setting": SETTING,
          "camera": CAMERA, "audio": AUDIO, "budget": BUDGET, "audience": AUDIENCE, "cta": CTA}


def values(group):
    return [str(v) for v, _, _ in GROUPS[group]]


def phrase(group, value):
    for v, _, p in GROUPS[group]:
        if str(v) == str(value):
            return p
    return ""


def as_json():
    return {k: [{"value": v, "label": l} for v, l, _ in opts] for k, opts in GROUPS.items()}
