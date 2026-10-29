"""Graph builders for the partner-API video models.

Each builder turns (prompt, uploaded image names, duration) into a small ComfyUI graph: LoadImage nodes feeding one
partner node, saved with SaveVideo. Node and input names come from Comfy's own node specs (get_node), so they are exact.
These run through the same path as Seedance: client.run(graph, api_key=...).
"""
import re

SAVE_ID = "776"


def short(prompt: str, limit: int) -> str:
    """Collapse whitespace and cut at a word boundary. Most models cap prompt length."""
    text = " ".join(prompt.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "."


def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(n)))


def _loads(graph: dict, names: list[str], base: int = 900) -> list[str]:
    ids = []
    for i, name in enumerate(names):
        gid = str(base + i)
        graph[gid] = {"_meta": {"title": f"Photo {i + 1}"}, "class_type": "LoadImage", "inputs": {"image": name}}
        ids.append(gid)
    return ids


def _finish(graph: dict, node_id: str, class_type: str, title: str, inputs: dict) -> dict:
    graph[node_id] = {"_meta": {"title": title}, "class_type": class_type, "inputs": inputs}
    graph[SAVE_ID] = {"_meta": {"title": "Save video"}, "class_type": "SaveVideo", "inputs": {
        "codec": "auto", "filename_prefix": "video/reelmatch", "format": "auto", "format.codec": "auto", "video": [node_id, 0]}}
    return graph


def build_grok(prompt, names, duration):
    g = {}
    ids = _loads(g, names[:1])
    return _finish(g, "789", "GrokVideoNode", "Grok Imagine Video 1.5 Lite", {
        "model": "grok-imagine-video-1.5-lite", "prompt": short(prompt, 800), "resolution": "720p", "aspect_ratio": "9:16",
        "duration": clamp(duration, 1, 15), "seed": 0, "image": [ids[0], 0]})


def build_pruna(prompt, names, duration):
    g = {}
    ids = _loads(g, names[:2])
    inputs = {"model": "p-video-2", "model.first_frame": [ids[0], 0], "model.prompt": short(prompt, 1500),
              "model.duration": str(clamp(duration, 1, 20)), "model.resolution": "720p", "model.fps": "24",
              "model.draft": True, "model.generate_audio": True, "model.enhance_prompt": True, "model.seed": 42}
    if len(ids) > 1:
        inputs["model.last_frame"] = [ids[1], 0]
    return _finish(g, "789", "PrunaImageToVideoNode", "Pruna P-Video 2", inputs)


def build_flux3(prompt, names, duration):
    g = {}
    ids = _loads(g, names[:10])
    inputs = {"prompt": short(prompt, 1500), "placement": "spread across the clip", "aspect_ratio": "9:16",
              "duration": str(clamp(duration, 5, 20)), "resolution": "720p", "reasoning_level": "low", "generate_audio": True, "seed": 42}
    for i, gid in enumerate(ids):
        inputs[f"keyframes.image_{i}"] = [gid, 0]
    return _finish(g, "789", "Flux3MaxImageToVideoNode", "FLUX 3 Max", inputs)


def build_kling4(prompt, names, duration):
    g = {}
    ids = _loads(g, names[:10])
    inputs = {"model": "kling-4.0", "model.prompt": re.sub(r"[Rr]eference photo (\d+)", r"@Image\1", short(prompt, 1500)), "model.resolution": "720p",
              "model.duration": clamp(duration, 3, 30), "model.seed": 42, "model.first_frame": [ids[0], 0]}
    if len(ids) > 1:
        inputs["model.last_frame"] = [ids[-1], 0]
        for i, gid in enumerate(ids[1:-1], start=1):  # up to 8 middle frames, spaced evenly by the model
            inputs[f"model.middle_frames.middle_frame_{i}"] = [gid, 0]
    return _finish(g, "789", "Kling4ImageToVideoNode", "Kling 4.0", inputs)


def build_heygen(prompt, names, duration):
    g = {}
    ids = _loads(g, names[:9])
    text = re.sub(r"[Rr]eference photo (\d+)", r"@Image\1", short(prompt, 1500))  # HeyGen refers to references as @ImageN
    inputs = {"model": "heygen-video-1", "model.prompt": text, "model.duration": clamp(duration, 5, 15), "model.resolution": "480p",
              "model.aspect_ratio": "9:16", "model.seed": 42}
    for i, gid in enumerate(ids, start=1):
        inputs[f"model.reference_images.image_{i}"] = [gid, 0]
    return _finish(g, "789", "HeyGenReferenceToVideoNode", "HeyGen Video 1.0", inputs)


def veo_seconds(duration: int) -> int:
    """Veo renders 4, 6 or 8 second clips."""
    return min((4, 6, 8), key=lambda s: abs(s - duration))


def build_veo(prompt, names, duration):
    g = {}
    ids = _loads(g, names[:1])
    return _finish(g, "789", "Veo3VideoGenerationNode", "Google Veo 3.1 Fast", {
        "prompt": short(prompt, 1000), "aspect_ratio": "9:16", "resolution": "720p", "duration_seconds": veo_seconds(duration),
        "person_generation": "ALLOW", "seed": 0, "image": [ids[0], 0], "model": "veo-3.1-fast-generate", "generate_audio": True})


BUILDERS = {
    "grok": ("Grok Imagine Lite", build_grok), "pruna": ("Pruna P-Video 2", build_pruna), "flux3": ("FLUX 3 Max", build_flux3),
    "kling4": ("Kling 4.0", build_kling4), "heygen": ("HeyGen Video 1.0", build_heygen), "veo": ("Veo 3.1 Fast", build_veo),
}
