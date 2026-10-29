"""Verified likeness: a person registers once with ByteDance's real-person check, then can appear in any ad.

How it works (Comfy's ByteDanceCreateImageAsset node): we upload the person's portrait and run the node with an empty
group id. ByteDance generates a verification link. The PERSON opens it on their own phone and does a short liveness check.
We never see or handle that face video. The result is a group id (the verified person) and an asset id (that portrait),
which are stored locally and reused, so the person never has to verify again.
"""
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from . import pipeline

STORE = pipeline.OUTPUTS / "likeness.json"  # local only, and outputs/ is not committed
SESSIONS: dict[str, dict] = {}
_lock = threading.Lock()
URL_RE = re.compile(r"https?://[^\s\"'<>)\]\\]+")
STORAGE_HOSTS = ("storage.googleapis.com", "comfy-cloud-assets")  # output downloads, not the verification link
WAIT_SECONDS = 15 * 60


def load_people() -> list[dict]:
    try:
        return json.loads(STORE.read_text())
    except (OSError, ValueError):
        return []


def _save_people(people: list[dict]):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(people, indent=2))
    try:
        STORE.chmod(0o600)
    except OSError:
        pass


def public_people() -> list[dict]:
    """What the page may see: names and ids, never the verification ids."""
    return [{"id": p["id"], "name": p["name"]} for p in load_people()]


def resolve(ids) -> list[dict]:
    have = {p["id"]: p for p in load_people()}
    return [have[i] for i in ids if i in have]


def delete_person(pid: str) -> bool:
    people = load_people()
    keep = [p for p in people if p["id"] != pid]
    _save_people(keep)
    return len(keep) != len(people)


def find_link(text: str) -> str | None:
    for u in URL_RE.findall(text or ""):
        u = u.rstrip(".,;")
        if not any(h in u for h in STORAGE_HOSTS):
            return u
    return None


def verification_graph(image_name: str, group_id: str = "") -> dict:
    """Portrait in, (asset id, group id) out. An empty group id triggers the liveness flow."""
    return {
        "1": {"_meta": {"title": "Portrait"}, "class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"_meta": {"title": "Create asset"}, "class_type": "ByteDanceCreateImageAsset", "inputs": {"image": ["1", 0], "group_id": group_id}},
        "3": {"_meta": {"title": "Asset id"}, "class_type": "SaveText", "inputs": {"filename_prefix": "reelmatch_asset_id", "format": "txt", "text": ["2", 0]}},
        "4": {"_meta": {"title": "Group id"}, "class_type": "SaveText", "inputs": {"filename_prefix": "reelmatch_group_id", "format": "txt", "text": ["2", 1]}},
    }


def _set(sid: str, **kw):
    with _lock:
        SESSIONS[sid].update(kw)


def status(sid: str) -> dict | None:
    with _lock:
        s = SESSIONS.get(sid)
        return dict(s) if s else None


def _event_text(ev) -> str:
    """Anything an event carries that could hold a link: log messages and text previews."""
    parts = [str(getattr(ev, "message", "") or "")]
    data = getattr(ev, "data", None)
    if isinstance(data, (bytes, bytearray)):
        parts.append(data[:4000].decode("utf-8", "ignore"))
    elif isinstance(data, str):
        parts.append(data)
    return " ".join(parts)


def _read_text(output) -> str:
    return output.to_bytes().decode("utf-8", "ignore").strip()


def _run(sid: str, selfie: Path, name: str):
    try:
        from comfy_sdk import Comfy

        pipeline.load_env()
        key = os.environ["COMFY_API_KEY"]
        _set(sid, status="uploading", message="Sending the portrait to Comfy")
        image_name = pipeline.upload_file(selfie)
        try:
            selfie.unlink()  # the portrait now lives with Comfy for this check; no need to keep our copy
        except OSError:
            pass
        client = Comfy()
        job = client.submit(client.workflows.from_json(verification_graph(image_name)), api_key=key)
        _set(sid, status="waiting", message="Waiting for Comfy to produce the verification link")
        deadline = time.time() + WAIT_SECONDS
        log = pipeline.OUTPUTS / "likeness_events.log"
        for ev in job.events():
            text = _event_text(ev)
            with open(log, "a") as f:  # kept so a failed run can be diagnosed; links are single-use
                f.write(f"{time.strftime('%H:%M:%S')} {type(ev).__name__} {text[:300]!r}\n")
            link = find_link(text)
            if link and not status(sid).get("url"):
                _set(sid, url=link, message="Open the link on your phone and complete the quick liveness check")
            if time.time() > deadline:
                job.cancel()
                raise TimeoutError("The verification was not completed in 15 minutes")
        job.wait()
        outs = {o.node_id: _read_text(o) for o in job.outputs if o.name.endswith(".txt") or "text" in (o.content_type or "")}
        asset_id, group_id = outs.get("3", ""), outs.get("4", "")
        if not asset_id or not group_id:
            raise RuntimeError("Verification finished but returned no ids")
        people = load_people()
        pid = uuid.uuid4().hex[:8]
        people.append({"id": pid, "name": name, "group_id": group_id, "asset_ids": [asset_id], "created": int(time.time())})
        _save_people(people)
        _set(sid, status="done", message=f"{name} is verified", person=pid)
    except Exception as e:
        _set(sid, status="error", message=pipeline.friendly_error(e))


def start(name: str, selfie: Path) -> str:
    sid = uuid.uuid4().hex[:10]
    with _lock:
        SESSIONS[sid] = {"id": sid, "status": "queued", "message": "Starting", "url": None, "person": None}
    threading.Thread(target=_run, args=(sid, selfie, name), daemon=True).start()
    return sid
