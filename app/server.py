"""Local web server for Collab Studio. Standard library only. Run: python -m app.server"""
import base64
import binascii
import hashlib
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import pipeline
from . import media, options
from .planner import make_plan
from .registry import BY_ID, choose

STATIC = Path(__file__).parent / "static"
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGES = 20
MAX_PHOTO_BYTES = 12 * 1024 * 1024
MAX_BODY = 160 * 1024 * 1024
GOALS = {"awareness", "launch", "promo", "event"}


class BadRequest(Exception):
    pass


def sniff_ok(data: bytes) -> bool:
    """Accept only real JPEG, PNG or WebP bytes, whatever the file is called."""
    return data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")


def folder_images(folder: str) -> list[Path]:
    if not folder.strip():
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


def gather_media(body: dict) -> tuple[list[Path], list[Path]]:
    return save_media(body.get("videos"), "video"), save_media(body.get("audios"), "audio")


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
        "consent": bool(raw.get("consent")), "verified_likeness": bool(raw.get("verified_likeness")) and subject != "product",
    }


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

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._file(STATIC / "index.html")
        if path == "/api/options":
            return self._json(options.as_json())
        if path == "/api/health":
            return self._json({"mock": pipeline.MOCK, "key": pipeline.key_present(),
                               "max_credits": pipeline.MAX_JOB_CREDITS, "session_credits": pipeline.LEDGER["credits"]})
        if path == "/api/jobs":
            jobs = sorted(pipeline.JOBS.values(), key=lambda j: j.get("created", 0), reverse=True)[:8]
            return self._json({"jobs": jobs})
        if path.startswith("/api/jobs/"):
            job = pipeline.JOBS.get(path.rsplit("/", 1)[1])
            return self._json(job) if job else self._json({"error": "no such job"}, 404)
        if path.startswith("/photo/"):
            photo = PHOTOS.get(path.rsplit("/", 1)[1])
            return self._file(photo) if photo else self._json({"error": "not found"}, 404)
        if path.startswith("/outputs/"):
            target = (pipeline.OUTPUTS / path[len("/outputs/"):]).resolve()
            if pipeline.OUTPUTS.resolve() in target.parents and target.suffix in (".mp4", ".jpg", ".jpeg", ".png", ".webp"):
                return self._file(target)
        self._json({"error": "not found"}, 404)

    def do_POST(self):
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

    def _post(self, body):
        if self.path == "/api/photos":
            return self._json({"images": register(gather_images(body))})
        if self.path == "/api/plan":
            brief = clean_brief(body.get("brief") or {})
            images = gather_images(body)
            videos, audios = gather_media(body)
            brief.update(n_videos=len(videos), n_audio=len(audios))
            choice = choose(brief, len(images))
            return self._json({"plan": make_plan(brief, len(images)), "model": choice, "n_images": len(images),
                               "images": register(images), "credits": choice["cost"], "brief": brief})
        if self.path == "/api/generate":
            brief = clean_brief(body.get("brief") or {})
            if not brief["consent"]:
                raise BadRequest("Confirm you have the right to use these photos.")
            images = gather_images(body)
            if not images:
                raise BadRequest("Add at least one photo.")
            videos, audios = gather_media(body)
            brief.update(n_videos=len(videos), n_audio=len(audios))
            choice = choose(brief, len(images))  # decided here, never trusted from the browser
            if not choice["model"]:
                raise BadRequest("No model fits this brief. Loosen the length, sound, budget or likeness options.")
            model = BY_ID[choice["model"]]
            cost = choice["cost"]
            if body.get("confirm_credits") != cost:
                raise BadRequest("Credit confirmation does not match the estimate.")
            if cost > pipeline.MAX_JOB_CREDITS:
                raise BadRequest(f"That job (about {cost} credits) is over the {pipeline.MAX_JOB_CREDITS}-credit safety limit.")
            plan = str(body.get("plan", "")).strip()[:6000]
            if not plan:
                raise BadRequest("The shot plan is empty.")
            if model.max_refs:
                images = images[:model.max_refs]
            videos = videos[:model.video_refs]
            soundtrack = audios[0] if audios and brief["soundtrack"] else None
            refs_audio = audios[:model.audio_refs]
            return self._json({"job": pipeline.start_job(model, plan, images, brief["duration"], videos, refs_audio, soundtrack)})
        self._json({"error": "not found"}, 404)


def main(port=8000):
    pipeline.OUTPUTS.mkdir(exist_ok=True)
    pipeline.load_history()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    mode = "MOCK (no credits spent)" if pipeline.MOCK else "LIVE (spends Comfy credits)"
    print(f"Collab Studio on http://localhost:{port}  [{mode}]")
    srv.serve_forever()


if __name__ == "__main__":
    main()
