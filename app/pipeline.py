"""Runs one ad job: dispatches to the adapter for the chosen model and saves the video."""
import base64
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"
BASE_URL = os.environ.get("COMFY_BASE_URL", "https://cloud.comfy.org")
MOCK = os.environ.get("COLLAB_MOCK") == "1"
MOCK_VIDEO = OUTPUTS / "soraa_promo_15s_draft.mp4"
MAX_JOB_CREDITS = int(os.environ.get("COLLAB_MAX_CREDITS", "600"))
JOB_TIMEOUT = 900

JOBS: dict[str, dict] = {}
LEDGER = {"credits": 0}
_lock = threading.Lock()


def load_env(path=ROOT / ".env"):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def key_present() -> bool:
    load_env()
    return bool(os.environ.get("COMFY_API_KEY"))


def friendly_error(e: Exception) -> str:
    """Turn provider and network errors into something a brand can act on."""
    name = type(e).__name__
    text = str(e).strip().splitlines()[0] if str(e).strip() else name
    table = {
        "ContentPolicyViolation": "The model's content policy refused these photos or prompt. Try different photos or a different model.",
        "InsufficientCredits": "This workspace is out of Comfy credits. Switch to a workspace with credits or add some.",
        "Unauthorized": "Comfy rejected the API key. Check COMFY_API_KEY in .env.",
        "MissingApiKey": "No Comfy API key found. Add COMFY_API_KEY to .env.",
        "QueueFull": "Comfy's queue is full right now. Try again in a minute.",
        "InvalidInput": f"The model rejected the request: {text}",
        "TimeoutError": "The render took too long and was stopped. Try a shorter video.",
    }
    if name in table:
        return table[name]
    if isinstance(e, requests.ConnectionError):
        return "Could not reach Comfy Cloud. Check your internet connection."
    return f"{name}: {text}"


def _data_uri(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def upload_file(path: Path) -> str:
    """Comfy Cloud's input upload. Used for photos, reference videos and audio."""
    r = requests.post(
        f"{BASE_URL}/api/upload/image",
        headers={"X-API-Key": os.environ["COMFY_API_KEY"]},
        files={"image": (path.name, path.read_bytes())},
        data={"type": "input", "overwrite": "true"},
        timeout=120,
    )
    r.raise_for_status()
    body = r.json()
    return f"{body['subfolder']}/{body['name']}" if body.get("subfolder") else body["name"]


def build_seedance_graph(prompt: str, image_names: list[str], duration: int, video_names=(), audio_names=()) -> dict:
    """Seedance 2.5 draft reference-to-video. Same graph as the Comfy template that worked."""
    graph = {}
    node = {
        "model": "Seedance 2.5 Draft", "model.auto_downscale": True, "model.auto_upscale": False,
        "model.duration": duration, "model.generate_audio": True, "model.output_format": "mp4",
        "model.prompt": prompt, "model.ratio": "9:16", "model.resolution": "480p",
        # "reference" is checked when the job is submitted, so a bad combination fails before any credits are spent
        "model.task_type": "reference" if (video_names or audio_names) else "auto",
        "seed": 0, "watermark": False,
    }
    for i, name in enumerate(image_names, start=1):
        load_id = str(780 + i)
        graph[load_id] = {"_meta": {"title": f"Reference photo {i}"}, "class_type": "LoadImage", "inputs": {"image": name}}
        node[f"model.reference_images.image_{i}"] = [load_id, 0]
    for i, name in enumerate(video_names, start=1):
        graph[str(800 + i)] = {"_meta": {"title": f"Reference video {i}"}, "class_type": "LoadVideo", "inputs": {"file": name}}
        node[f"model.reference_videos.video_{i}"] = [str(800 + i), 0]
    for i, name in enumerate(audio_names, start=1):
        graph[str(820 + i)] = {"_meta": {"title": f"Reference audio {i}"}, "class_type": "LoadAudio", "inputs": {"audio": name}}
        node[f"model.reference_audios.audio_{i}"] = [str(820 + i), 0]
    graph["789"] = {"_meta": {"title": "Seedance 2.5 draft"}, "class_type": "ByteDance2ReferenceNodeV2", "inputs": node}
    graph["776"] = {"_meta": {"title": "Save video"}, "class_type": "SaveVideo", "inputs": {
        "codec": "auto", "filename_prefix": "video/collab_studio", "format": "auto", "format.codec": "auto", "video": ["789", 0]}}
    graph["771"] = {"_meta": {"title": "Save draft task id"}, "class_type": "SaveText", "inputs": {
        "filename_prefix": "collab_studio_draft_task", "format": "txt", "text": ["789", 1]}}
    return graph


def _seedance(job_id, prompt, images, duration, out_file, videos=(), audios=()):
    from comfy_sdk import Comfy

    extra = f" and {len(videos) + len(audios)} reference clip(s)" if (videos or audios) else ""
    _set(job_id, status="uploading", message=f"Uploading {len(images)} photos{extra}")
    names = [upload_file(p) for p in images]
    video_names = [upload_file(p) for p in videos]
    audio_names = [upload_file(p) for p in audios]
    _set(job_id, status="rendering", message="Rendering on Comfy Cloud with Seedance 2.5 (about a minute)")
    client = Comfy()
    job = client.run(client.workflows.from_json(build_seedance_graph(prompt, names, duration, video_names, audio_names)), timeout=JOB_TIMEOUT)
    videos = [o for o in job.outputs if (o.content_type or "").startswith("video") or o.name.endswith(".mp4")]
    if not videos:
        raise RuntimeError("The job finished but returned no video")
    videos[0].to_file(out_file)


def _wan(job_id, prompt, images, duration, out_file, videos=(), audios=()):
    from comfy_sdk import Comfy

    _set(job_id, status="rendering", message="Rendering on Comfy Cloud with Wan 2.7 (about 30 seconds)")
    args = {
        "input": {"prompt": " ".join(prompt.split())[:780], "media": [{"type": "first_frame", "url": _data_uri(images[0])}]},
        "parameters": {"resolution": "720P", "duration": duration, "prompt_extend": True, "watermark": False},
    }
    res = Comfy().models.run("wan/wan2.7-i2v", args)
    url = res["output"]["video_url"]
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    Path(out_file).write_bytes(r.content)


ADAPTERS = {"seedance": _seedance, "wan": _wan}


def _set(job_id, **kw):
    with _lock:
        JOBS[job_id].update(kw)
        snap = dict(JOBS[job_id])
    d = OUTPUTS / job_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "job.json").write_text(json.dumps(snap, indent=2))


def _run(job_id: str, model, prompt: str, images: list[Path], duration: int, videos=(), audios=(), soundtrack=None):
    out = OUTPUTS / job_id / "video.mp4"
    try:
        if MOCK:
            _set(job_id, status="rendering", message="Mock mode: replaying a saved clip")
            time.sleep(4)
            shutil.copy(MOCK_VIDEO, out)
        else:
            load_env()
            if not os.environ.get("COMFY_API_KEY"):
                raise RuntimeError("No Comfy API key found. Add COMFY_API_KEY to .env.")
            ADAPTERS[model.adapter](job_id, prompt, images, duration, out, videos, audios)
        if soundtrack:
            from .media import mux_soundtrack

            _set(job_id, status="rendering", message="Mixing your music into the video")
            mixed = out.with_name("video_mixed.mp4")
            mux_soundtrack(out, soundtrack, mixed)
            mixed.replace(out)
        (OUTPUTS / job_id / "prompt.txt").write_text(prompt)
        spent = model.cost(duration) or 0
        if not MOCK:
            with _lock:
                LEDGER["credits"] += spent
        _set(job_id, status="done", message="Draft ready", video=f"/outputs/{job_id}/video.mp4")
    except Exception as e:
        _set(job_id, status="error", message=friendly_error(e))


def start_job(model, prompt: str, images: list[Path], duration: int, videos=(), audios=(), soundtrack=None) -> str:
    job_id = uuid.uuid4().hex[:10]
    with _lock:
        JOBS[job_id] = {"id": job_id, "status": "queued", "message": "Queued", "video": None, "model": model.label,
                        "duration": duration, "photos": len(images), "videos": len(videos), "music": bool(soundtrack),
                        "credits": model.cost(duration), "mock": MOCK,
                        "created": int(time.time())}
    _set(job_id)
    threading.Thread(target=_run, args=(job_id, model, prompt, images, duration, videos, audios, soundtrack), daemon=True).start()
    return job_id


def load_history():
    """Reload finished jobs from disk so history survives restarts."""
    for f in sorted(OUTPUTS.glob("*/job.json")):
        try:
            j = json.loads(f.read_text())
            if j.get("status") in ("queued", "uploading", "rendering"):
                j.update(status="error", message="Interrupted by a restart")
            JOBS[j["id"]] = j
        except (ValueError, KeyError):
            continue
