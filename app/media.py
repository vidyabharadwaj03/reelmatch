"""Video and audio helpers: file-type checks and mixing a brand's own track into the finished ad."""
import re
import subprocess
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".webm"}
AUDIO_EXT = {".mp3", ".wav", ".m4a"}
MAX_VIDEO_BYTES = 40 * 1024 * 1024
MAX_AUDIO_BYTES = 15 * 1024 * 1024
MAX_VIDEOS = 3
MAX_AUDIOS = 3


def sniff_video(d: bytes) -> bool:
    """mp4 and mov carry 'ftyp' at byte 4, webm starts with the EBML header."""
    return d[4:8] == b"ftyp" or d[:4] == b"\x1aE\xdf\xa3"


def sniff_audio(d: bytes) -> bool:
    return (d[:3] == b"ID3" or (len(d) > 1 and d[0] == 0xFF and d[1] & 0xE0 == 0xE0)
            or (d[:4] == b"RIFF" and d[8:12] == b"WAVE") or d[4:8] == b"ftyp")


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise RuntimeError("ffmpeg is not installed. Run: pip install -r requirements.txt")


def duration_seconds(path: Path) -> float:
    """Read a file's length from ffmpeg's banner (imageio-ffmpeg ships no ffprobe)."""
    out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.?\d*)", out)
    if not m:
        raise RuntimeError(f"Could not read the length of {path.name}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


def mux_soundtrack(video: Path, audio: Path, out: Path, fade: float = 1.0) -> Path:
    """Replace the video's sound with the brand's track: loop it if short, cut it to the video's length, fade out."""
    length = duration_seconds(video)
    start_fade = max(0.0, length - fade)
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(audio),
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
           "-af", f"afade=t=out:st={start_fade:.2f}:d={fade:.2f}", "-t", f"{length:.2f}", "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("Could not mix your music into the video: " + (r.stderr.strip().splitlines() or ["ffmpeg failed"])[-1])
    return out
