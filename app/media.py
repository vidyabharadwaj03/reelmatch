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


def audio_seconds(path: Path) -> float:
    """How long the audio actually plays. The container's length can be longer than its sound."""
    err = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path), "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
    times = re.findall(r"time=(\d+):(\d+):(\d+\.?\d*)", err)
    if not times:
        return 0.0
    h, m, sec = times[-1]
    return int(h) * 3600 + int(m) * 60 + float(sec)


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


# ---- reference trimming, voiceover and music mixing, and clip stitching ----

def _banner(path: Path) -> str:
    return subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr


def has_audio(path: Path) -> bool:
    return "Audio:" in _banner(path)


def video_size(path: Path) -> tuple[int, int]:
    m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", _banner(path))
    if not m:
        raise RuntimeError(f"Could not read the size of {path.name}")
    return int(m.group(1)), int(m.group(2))


def _run(cmd: list[str], what: str):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{what}: " + (r.stderr.strip().splitlines() or ["ffmpeg failed"])[-1])


def trim(src: Path, out: Path, max_seconds: float = 15.0) -> Path:
    """Cut a reference clip to its first N seconds. Providers cap reference clip length, so we never send a long one."""
    if duration_seconds(src) <= max_seconds + 0.05:
        return src
    _run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-t", f"{max_seconds:.2f}", "-c", "copy", str(out)],
         f"Could not trim {src.name}")
    return out


STEREO = "aformat=sample_rates=44100:channel_layouts=stereo"


def mix_audio(video: Path, out: Path, music: Path | None = None, voice: Path | None = None,
              fade: float = 1.0, voice_delay: float = 0.4) -> Path:
    """Build the ad's final sound.

    music + voice: music loops under the voice and ducks while it speaks.
    music only: music replaces the video's sound.
    voice only: the voice sits over the video's own sound, which is turned down (or alone if the video is silent).
    """
    if not music and not voice:
        raise ValueError("mix_audio needs music, a voice, or both")
    length = duration_seconds(video)
    st = max(0.0, length - fade)
    tail = f"afade=t=out:st={st:.2f}:d={fade:.2f}"
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
    idx = 1
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        m_i, idx = idx, idx + 1
    if voice:
        cmd += ["-i", str(voice)]
        v_i = idx
    # Pad the voice with silence to the full length. Without this, the ducking filter ends when the voice does and cuts the music off.
    vo = f"[{v_i}:a]{STEREO},adelay={int(voice_delay * 1000)}|{int(voice_delay * 1000)},apad=whole_dur={length:.2f}" if voice else ""
    if music and voice:
        graph = (f"{vo},asplit=2[v][vsc];[{m_i}:a]{STEREO}[m];[m][vsc]sidechaincompress=threshold=0.02:ratio=10:attack=20:release=400[md];"
                 f"[md][v]amix=inputs=2:duration=first:normalize=0,{tail}[a]")
    elif music:
        graph = f"[{m_i}:a]{STEREO},{tail}[a]"
    elif has_audio(video):
        graph = f"[0:a]{STEREO},volume=0.25[o];{vo}[v];[o][v]amix=inputs=2:duration=first:normalize=0,{tail}[a]"
    else:
        graph = f"{vo},{tail}[a]"
    cmd += ["-filter_complex", graph, "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{length:.2f}", "-movflags", "+faststart", str(out)]
    _run(cmd, "Could not mix the audio")
    return out


def concat_clips(first: Path, second: Path, out: Path, size_from: Path | None = None) -> Path:
    """Join two clips into one. Frames are fitted to one size and sound is kept, with silence standing in for a silent clip."""
    w, h = video_size(size_from or second)
    parts, ins = [], []
    for i, p in enumerate((first, second)):
        ins += ["-i", str(p)]
        d = duration_seconds(p)
        parts.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,format=yuv420p[v{i}]")
        if has_audio(p):
            parts.append(f"[{i}:a]aresample=44100,{STEREO}[a{i}]")
        else:
            parts.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={d:.3f}[a{i}]")
    graph = ";".join(parts) + ";[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    _run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *ins, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)],
         "Could not join the clips")
    return out
