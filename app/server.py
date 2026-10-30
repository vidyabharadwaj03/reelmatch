"""Local web server for Reelmatch. Standard library only. Run: python -m app.server"""
import base64
import binascii
import hashlib
import hmac
import json
import math
import mimetypes
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import pipeline
from . import likeness, media, options
from .planner import make_plan
from .script import make_scripts
from .registry import BY_ID, apply_override, choose

STATIC = Path(__file__).parent / "static"
SAMPLES = Path(__file__).parent / "samples"  # AI-made product photos, no people, so anyone can try the app
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGES = 20
MAX_PHOTO_BYTES = 12 * 1024 * 1024
MAX_BODY = (60 if os.environ.get("REELMATCH_PUBLIC") == "1" else 160) * 1024 * 1024
GOALS = {"awareness", "launch", "promo", "event"}

# ---- hosted, judge-only mode (all off by default, so a local run behaves exactly as before) ----
PUBLIC = os.environ.get("REELMATCH_PUBLIC") == "1"  # a shared copy: no server folders, no identity checks, spending caps
ACCESS_CODE = os.environ.get("REELMATCH_ACCESS_CODE", "")  # if set, nothing works without it
TOTAL_BUDGET = int(os.environ.get("REELMATCH_BUDGET", "6000"))  # most credits a public copy may spend in total
MAX_ACTIVE = int(os.environ.get("REELMATCH_MAX_ACTIVE", "2"))  # renders running at once
PER_HOUR = int(os.environ.get("REELMATCH_PER_HOUR", "8"))  # renders per visitor per hour
_hits: dict[str, list[float]] = {}
_hits_lock = threading.Lock()


def access_token(code: str) -> str:
    """What the browser keeps instead of the code itself."""
    return hashlib.sha256(("reelmatch|" + code).encode()).hexdigest()


def is_authorized(cookie_header: str, code: str = "") -> bool:
    code = code or ACCESS_CODE
    if not code:
        return True
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == "rm_access" and hmac.compare_digest(v, access_token(code)):
            return True
    return False


def budget_left() -> int:
    """Credits still available to a public copy: the total minus what is spent or reserved by running renders."""
    running = sum((j.get("credits") or 0) for j in pipeline.JOBS.values() if j.get("status") in ("queued", "uploading", "rendering") and not j.get("mock"))
    return max(0, TOTAL_BUDGET - pipeline.LEDGER["credits"] - running)


def active_jobs() -> int:
    return sum(1 for j in pipeline.JOBS.values() if j.get("status") in ("queued", "uploading", "rendering"))


def allow_visitor(ip: str) -> bool:
    now = time.time()
    with _hits_lock:
        recent = [t for t in _hits.get(ip, []) if now - t < 3600]
        if len(recent) >= PER_HOUR:
            _hits[ip] = recent
            return False
        recent.append(now)
        _hits[ip] = recent
        return True


def sweep(older_than_s: int = 7200):
    """A public copy keeps nothing for long: uploads and finished renders are deleted after a couple of hours."""
    keep = {"_mock_sample.mp4", "likeness.json"}
    now = time.time()
    for f in pipeline.OUTPUTS.iterdir():
        try:
            if f.name in keep or now - f.stat().st_mtime < older_than_s:
                continue
            if f.is_dir():
                for sub in f.rglob("*"):
                    if sub.is_file():
                        sub.unlink()
                for d in sorted((x for x in f.rglob("*") if x.is_dir()), reverse=True):
                    d.rmdir()
                f.rmdir()
            else:
                f.unlink()
        except OSError:
            continue


GATE_PAGE = b"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Reelmatch</title>
<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#290d17;color:#fff4de;font:16px system-ui,sans-serif">
<form method=get style="max-width:340px;padding:24px"><h1 style="margin:0 0 8px;font-size:34px;letter-spacing:-.04em">Reel<span style="color:#d8f36a">match</span></h1>
<p style="color:#dbc3c8">This copy is for judging. Enter the access code from the entry form.</p>
<input name=code placeholder="Access code" autofocus style="width:100%;box-sizing:border-box;padding:12px;border-radius:12px;border:0;font:inherit">
<button style="margin-top:12px;width:100%;padding:12px;border-radius:999px;border:0;background:#d8f36a;color:#290d17;font:700 16px system-ui">Continue</button></form>"""


class BadRequest(Exception):
    pass


def sniff_ok(data: bytes) -> bool:
    """Accept only real JPEG, PNG or WebP bytes, whatever the file is called."""
    return data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")


def folder_images(folder: str) -> list[Path]:
    if PUBLIC or not folder.strip():
        return []
    p = Path(folder).expanduser()
    if not p.is_absolute():
        p = pipeline.ROOT / p
    if not p.is_dir():
        return []
    good = []
    for f in sorted(p.iterdir()):
        if f.suffix.lower() in IMG_EXT and f.stat().st_size <= MAX_PHOTO_BYTES and sniff_ok(f.read_bytes()[:16]):
            good.append(f)
    return good[:MAX_IMAGES]


def save_uploads(uploads: list[dict]) -> list[Path]:
    dest = pipeline.OUTPUTS / "uploads"
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for u in uploads[:MAX_IMAGES]:
        name = re.sub(r"[^A-Za-z0-9._-]", "_", str(u.get("name", "photo.jpg")))[:80]
        if Path(name).suffix.lower() not in IMG_EXT:
            raise BadRequest(f"{name}: only JPG, PNG and WebP photos are supported.")
        try:
            data = base64.b64decode(str(u.get("data", "")).split(",")[-1], validate=True)
        except (binascii.Error, ValueError):
            raise BadRequest(f"{name}: the file could not be read.")
        if len(data) > MAX_PHOTO_BYTES:
            raise BadRequest(f"{name} is over {MAX_PHOTO_BYTES // 1024 // 1024} MB. Please shrink it.")
        if not sniff_ok(data):
            raise BadRequest(f"{name} does not look like a real image.")
        p = dest / name
        p.write_bytes(data)
        paths.append(p)
    return paths


def save_media(items: list[dict], kind: str) -> list[Path]:
    """Reference videos and music: check extension, size and real file type before keeping them."""
    exts, limit, cap, sniff = ((media.VIDEO_EXT, media.MAX_VIDEO_BYTES, media.MAX_VIDEOS, media.sniff_video) if kind == "video"
                               else (media.AUDIO_EXT, media.MAX_AUDIO_BYTES, media.MAX_AUDIOS, media.sniff_audio))
    dest = pipeline.OUTPUTS / "uploads"
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for u in (items or [])[:cap]:
        name = re.sub(r"[^A-Za-z0-9._-]", "_", str(u.get("name", f"{kind}.bin")))[:80]
        if Path(name).suffix.lower() not in exts:
            raise BadRequest(f"{name}: supported {kind} types are {', '.join(sorted(exts))}.")
        try:
            data = base64.b64decode(str(u.get("data", "")).split(",")[-1], validate=True)
        except (binascii.Error, ValueError):
            raise BadRequest(f"{name}: the file could not be read.")
        if len(data) > limit:
            raise BadRequest(f"{name} is over {limit // 1024 // 1024} MB. Please trim or compress it.")
        if not sniff(data[:16]):
            raise BadRequest(f"{name} does not look like a real {kind} file.")
        p = dest / name
        p.write_bytes(data)
        paths.append(p)
    return paths


def gather_media(body: dict) -> tuple[list[Path], list[Path], list[Path]]:
    return save_media(body.get("videos"), "video"), save_media(body.get("audios"), "audio"), save_media(body.get("voices"), "audio")[:1]


def gather_images(body: dict) -> list[Path]:
    """Uploaded photos win over the folder, so a brand can drop files without clearing the path."""
    ups = save_uploads(body.get("uploads") or [])
    return (ups or folder_images(body.get("folder", "")))[:MAX_IMAGES]


def clean_brief(raw: dict) -> dict:
    """Validate and normalise the brief once, so the rest of the code can trust it."""
    try:
        duration = int(raw.get("duration", 15))
    except (TypeError, ValueError):
        raise BadRequest("Length must be a number of seconds.")
    if not 4 <= duration <= 30:
        raise BadRequest("Length must be between 4 and 30 seconds.")
    budget = raw.get("budget")
    try:
        budget = int(budget) if budget not in (None, "") else None
    except (TypeError, ValueError):
        raise BadRequest("Budget must be a number of credits.")
    if budget is not None and budget <= 0:
        budget = None

    def one(group, default):
        v = str(raw.get(group, default))
        return v if v in options.values(group) else default

    def many(group):
        picked = raw.get(group) or []
        return [v for v in picked if str(v) in options.values(group)][:6] if isinstance(picked, list) else []

    t = lambda k, n=300: str(raw.get(k, "")).strip()[:n]
    subject = one("subject", "people")
    return {
        "brand": t("brand", 60) or "the brand", "subject": subject, "goal": one("goal", "awareness"),
        "platform": one("platform", "TikTok"), "duration": duration, "style": many("style"), "camera": many("camera"),
        "setting": one("setting", "street_night"), "audience": one("audience", "everyone"), "cta": one("cta", "none"),
        "description": t("description"), "feel": t("feel", 160), "message": t("message", 160),
        "include": t("include", 200), "avoid": t("avoid", 200),
        "needs_audio": bool(raw.get("needs_audio", True)), "budget": budget,
        "open_weights_only": bool(raw.get("open_weights_only")), "soundtrack": bool(raw.get("soundtrack", True)),
        "video_mode": one("video_mode", "reference"),
        "consent": bool(raw.get("consent")), "people": ([str(i) for i in raw.get("people", [])][:4] if isinstance(raw.get("people"), list) and subject != "product" else []),
        "verified_likeness": False,
    }


def apply_people(brief: dict) -> list[str]:
    """Turn selected person ids into names (for the prompt) and ByteDance asset ids (for the render)."""
    found = likeness.resolve(brief.get("people", []))
    brief["people"] = [p["id"] for p in found]
    brief["people_names"] = [p["name"] for p in found]
    brief["verified_likeness"] = bool(found)
    return [p["asset_ids"][0] for p in found]


PHOTOS: dict[str, Path] = {}


def register(paths: list[Path]) -> list[dict]:
    out = []
    for n, p in enumerate(paths, start=1):
        token = hashlib.sha1(str(p).encode()).hexdigest()[:12]
        PHOTOS[token] = p
        out.append({"n": n, "name": p.name, "url": f"/photo/{token}"})
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path):
        if not path.is_file():
            return self._json({"error": "not found"}, 404)
        size = path.stat().st_size
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        start, end, code = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else end
            else:
                start = max(0, size - int(m.group(2)))
            code = 206
        if start > end or start >= size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return
        with open(path, "rb") as f:
            f.seek(start)
            chunk = f.read(end - start + 1)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(chunk)))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        self.wfile.write(chunk)

    def _client_ip(self) -> str:
        fwd = self.headers.get("X-Forwarded-For", "")
        return (fwd.split(",")[0].strip() if fwd else self.client_address[0]) or "?"

    def _gate(self) -> bool:
        """True if the request may continue. With an access code set, everything else is closed to visitors without it."""
        path, _, query = self.path.partition("?")
        if path == "/health":
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")
            return False
        if is_authorized(self.headers.get("Cookie", "")):
            return True
        code = dict(kv.split("=", 1) for kv in query.split("&") if "=" in kv).get("code", "")
        if code and hmac.compare_digest(code, ACCESS_CODE):
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
            self.send_response(302)
            self.send_header("Set-Cookie", f"rm_access={access_token(ACCESS_CODE)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800{secure}")
            self.send_header("Location", "/"); self.send_header("Content-Length", "0"); self.end_headers()
            return False
        if path in ("/", "/index.html"):
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(GATE_PAGE))); self.end_headers(); self.wfile.write(GATE_PAGE)
        else:
            self._json({"error": "Access code required."}, 401)
        return False

    def do_GET(self):
        if not self._gate():
            return
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._file(STATIC / "index.html")
        if path == "/api/likeness":
            return self._json({"people": likeness.public_people()})
        if path.startswith("/api/likeness/session/"):
            st = likeness.status(path.rsplit("/", 1)[1])
            return self._json(st) if st else self._json({"error": "no such session"}, 404)
        if path == "/api/options":
            return self._json(options.as_json())
        if path == "/api/health":
            return self._json({"mock": pipeline.MOCK, "key": pipeline.key_present(),
                               "max_credits": pipeline.MAX_JOB_CREDITS, "session_credits": pipeline.LEDGER["credits"],
                               "example": bool(folder_images("assets/soraa")), "public": PUBLIC,
                               "budget_left": budget_left() if PUBLIC else None})
        if path == "/api/jobs":
            jobs = sorted(pipeline.JOBS.values(), key=lambda j: j.get("created", 0), reverse=True)[:8]
            return self._json({"jobs": jobs})
        if path.startswith("/api/jobs/"):
            job = pipeline.JOBS.get(path.rsplit("/", 1)[1])
            return self._json(job) if job else self._json({"error": "no such job"}, 404)
        if path.startswith("/samples/"):
            target = (SAMPLES / path[len("/samples/"):]).resolve()
            if SAMPLES.resolve() in target.parents and target.suffix == ".jpg":
                return self._file(target)
            return self._json({"error": "not found"}, 404)
        if path.startswith("/photo/"):
            photo = PHOTOS.get(path.rsplit("/", 1)[1])
            return self._file(photo) if photo else self._json({"error": "not found"}, 404)
        if path.startswith("/outputs/"):
            target = (pipeline.OUTPUTS / path[len("/outputs/"):]).resolve()
            if pipeline.OUTPUTS.resolve() in target.parents and target.suffix in (".mp4", ".jpg", ".jpeg", ".png", ".webp"):
                return self._file(target)
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._gate():
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY:
                return self._json({"error": "That upload is too large."}, 413)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                raise BadRequest("The request was not valid JSON.")
            self._post(body)
        except BadRequest as e:
            self._json({"error": str(e)}, 400)
        except Exception as e:  # never leave the page hanging on a server bug
            self._json({"error": f"Server error: {type(e).__name__}"}, 500)

    def _likeness_start(self, body) -> dict:
        """Begin a one-time identity check. The person opens the link we show and does the liveness check themselves."""
        name = str(body.get("name", "")).strip()[:60]
        if not name:
            raise BadRequest("Enter the person's name.")
        if not body.get("consent"):
            raise BadRequest("Confirm this is you, or that the person is with you and agrees.")
        if pipeline.MOCK:
            raise BadRequest("Identity verification needs live mode. Demo mode never contacts Comfy or ByteDance.")
        if not pipeline.key_present():
            raise BadRequest("No Comfy API key found. Add COMFY_API_KEY to .env.")
        selfie = save_uploads([body.get("selfie") or {}])
        if not selfie:
            raise BadRequest("Add a clear photo of the person's face.")
        return {"session": likeness.start(name, selfie[0])}

    def _quote(self, body) -> dict:
        """Which model would be used, and what it costs. Takes counts, not files, so the page can ask it on every tap."""
        brief = clean_brief(body.get("brief") or {})
        apply_people(brief)
        counts = body.get("counts") or {}
        n = {k: max(0, min(int(counts.get(k, 0) or 0), 20)) for k in ("images", "videos", "audios", "voices")}
        if not n["videos"]:
            brief["video_mode"] = "reference"
        elif brief["video_mode"] == "edit" and body.get("video_seconds"):
            brief["duration"] = min(30, max(4, math.ceil(min(float(body["video_seconds"]), 15))))
        brief.update(n_videos=n["videos"], n_audio=n["audios"], n_voice=n["voices"])
        choice = choose(brief, n["images"])
        ignored = False
        try:
            choice = apply_override(choice, body.get("model_id"))
        except ValueError:
            ignored = True  # a stale override after the brief changed: fall back to the automatic pick
        return {"model": choice, "credits": choice["cost"], "duration": brief["duration"], "override_ignored": ignored}

    def _post(self, body):
        if self.path == "/api/photos":
            return self._json({"images": register(gather_images(body))})
        if PUBLIC and self.path.startswith("/api/likeness"):
            return self._json({"error": "Identity verification is turned off on this shared copy. Run Reelmatch locally to use it."}, 403)
        if self.path == "/api/likeness/start":
            return self._json(self._likeness_start(body))
        if self.path == "/api/likeness/delete":
            return self._json({"ok": likeness.delete_person(str(body.get("id", "")))})
        if self.path == "/api/script":
            b = clean_brief(body.get("brief") or {})
            if b["video_mode"] != "reference":
                b["description"] = ""  # in extend or edit mode the description is about the clip, not the brand
            return self._json(make_scripts(b))
        if self.path == "/api/quote":
            return self._json(self._quote(body))
        if self.path not in ("/api/plan", "/api/generate"):
            return self._json({"error": "not found"}, 404)

        brief = clean_brief(body.get("brief") or {})
        assets = apply_people(brief)
        images = gather_images(body)
        videos, audios, voices = gather_media(body)
        mode = brief["video_mode"]
        if mode != "reference" and not videos:
            raise BadRequest("Add a reference video to extend or edit it.")
        warnings, trimmed = [], []
        for v in videos:
            length = media.duration_seconds(v)
            if length > 15.05:
                warnings.append(f"{v.name} is {length:.0f}s, so only its first 15 seconds are used.")
            trimmed.append(media.trim(v, v.with_name(v.stem + "_trim.mp4")))
        videos = trimmed
        if mode == "edit":  # the edited clip keeps the source's length, so that is what we pay for
            brief["duration"] = min(30, max(4, math.ceil(media.duration_seconds(videos[0]))))
        brief.update(n_videos=len(videos), n_audio=len(audios), n_voice=len(voices))
        choice = choose(brief, len(images))
        try:
            choice = apply_override(choice, body.get("model_id"))
        except ValueError as e:
            raise BadRequest(str(e))
        if voices:
            final = brief["duration"] + (media.duration_seconds(videos[0]) if mode.startswith("extend") else 0)
            vlen = media.duration_seconds(voices[0])
            if vlen > final + 0.5:
                warnings.append(f"Your voiceover is {vlen:.0f}s but the ad is {final:.0f}s, so the end will be cut. Shorten the script or pick a longer ad.")

        if self.path == "/api/plan":
            return self._json({"plan": make_plan(brief, len(images)), "model": choice, "n_images": len(images),
                               "images": register(images), "credits": choice["cost"], "brief": brief, "warnings": warnings})

        if not brief["consent"]:
            raise BadRequest("Confirm you have the right to use these photos.")
        if not images and mode == "reference" and not assets:
            raise BadRequest("Add at least one photo, or choose a verified person.")
        if not choice["model"]:
            raise BadRequest("No model fits this brief. Loosen the length, sound, budget or likeness options.")
        model = BY_ID[choice["model"]]
        cost = choice["cost"]
        if PUBLIC and not pipeline.MOCK:
            if cost > budget_left():
                raise BadRequest("This judging copy has used up its credit budget. Run Reelmatch locally from the repo, or use demo mode.")
            if active_jobs() >= MAX_ACTIVE:
                raise BadRequest("Other renders are running right now. Please try again in a minute.")
            if not allow_visitor(self._client_ip()):
                raise BadRequest(f"That is the limit of {PER_HOUR} renders per hour from one visitor.")
        if body.get("confirm_credits") != cost:
            raise BadRequest("Credit confirmation does not match the estimate.")
        if cost > pipeline.MAX_JOB_CREDITS:
            raise BadRequest(f"That job (about {cost} credits) is over the {pipeline.MAX_JOB_CREDITS}-credit safety limit.")
        plan = str(body.get("plan", "")).strip()[:6000]
        if not plan:
            raise BadRequest("The shot plan is empty.")
        if model.max_refs:
            images = images[:model.max_refs]
        ref_audio = [media.trim(a, a.with_name(a.stem + "_trim" + a.suffix)) for a in audios[:model.audio_refs]]
        soundtrack = audios[0] if audios and brief["soundtrack"] else None
        job = pipeline.start_job(model, plan, images, brief["duration"], videos[:model.video_refs], ref_audio, soundtrack,
                                 voices[0] if voices else None, mode, assets)
        return self._json({"job": job})


def main(port=None, host=None):
    port = int(port or os.environ.get("PORT", 8000))
    host = host or os.environ.get("HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost") and not ACCESS_CODE and not pipeline.MOCK:
        raise SystemExit("Refusing to listen on a public address in live mode without REELMATCH_ACCESS_CODE set.")
    pipeline.OUTPUTS.mkdir(exist_ok=True)
    pipeline.load_history()
    if PUBLIC:
        def loop():
            while True:
                time.sleep(600)
                sweep()
        threading.Thread(target=loop, daemon=True).start()
    srv = ThreadingHTTPServer((host, port), Handler)
    mode = "MOCK (no credits spent)" if pipeline.MOCK else "LIVE (spends Comfy credits)"
    extra = f", shared copy, budget {TOTAL_BUDGET} credits, access code {'on' if ACCESS_CODE else 'OFF'}" if PUBLIC else ""
    print(f"Reelmatch on http://{host}:{port}  [{mode}{extra}]")
    srv.serve_forever()


if __name__ == "__main__":
    main()
