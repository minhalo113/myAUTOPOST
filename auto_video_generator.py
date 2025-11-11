import argparse
import random
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
import shutil
import os

LOCAL_FFMPEG = Path(__file__).parent / "ffmpeg" / "bin" / "ffmpeg.exe"
FFMPEG_BIN_DIR = (Path(__file__).parent / "ffmpeg" / "bin").resolve()
os.environ["PATH"] = str(FFMPEG_BIN_DIR) + os.pathsep + os.environ.get("PATH", "")

LOCAL_FFPROBE = Path(__file__).parent / "ffmpeg" / "bin" / "ffprobe.exe"
EMOTE_ROOT_DIR = Path(__file__).parent / "Genshin Emotes"
LAYER1_DURATION_PORTION = 0.40
LAYER1_FADE_SECONDS = 0.15
LAYER2_TRIGGER_THRESHOLD = 4.0
LAYER2_FADE_SECONDS = 0.15
LAYER3_MIN_GAP = 6.0
LAYER3_MAX_GAP = 10.0
LAYER3_MIN_DURATION = 0.4
LAYER3_MAX_DURATION = 0.7
LAYER3_FADE_SECONDS = 0.12
MICRO_EMOTE_OPACITY = 0.8

@dataclass
class OverlayEvent:
    image_path: Path
    start: float
    end: float
    scale: float
    x_expr: str
    y_expr: str
    fade_in: float
    fade_out: float
    opacity: float = 1.0

def _resolve_ffprobe() -> str:
    p = str(LOCAL_FFPROBE) if LOCAL_FFPROBE.exists() else shutil.which("ffprobe")
    if not p:
        raise RuntimeError("ffprobe.exe not found beside ffmpeg or on PATH!")
    return p

def get_media_duration_seconds(path: Path) -> float:
    """Return duration in seconds using ffprobe."""
    ffprobe = _resolve_ffprobe()
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}:\n{proc.stderr}")
    try:
        return float(proc.stdout.strip())
    except ValueError:
        raise RuntimeError(f"Could not parse duration for {path}: {proc.stdout}")

def ensure_ffmpeg_available() -> None:
    """Check whether ffmpeg is available on the system."""
    try:
        subprocess.run([LOCAL_FFMPEG, "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc: 
        raise RuntimeError("ffmpeg must be installed and available on PATH.") from exc


def run_ffmpeg_command(args: list[str]):
    ffmpeg_path = str(LOCAL_FFMPEG) if LOCAL_FFMPEG.exists() else shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg.exe not found in project folder or system PATH!")

    if args[0] == "ffmpeg":
        cmd = [ffmpeg_path] + args[1:]
    else:
        cmd = [ffmpeg_path] + args

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed:\nCommand: {' '.join(cmd)}\n{result.stderr}"
        )

def extract_audio(video_path: Path, audio_path: Path) -> None:
    """Extract mono WAV audio from the provided video file."""
    run_ffmpeg_command([
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-vn",
        str(audio_path),
    ])


def format_timestamp(seconds: float) -> str:
    """Convert seconds (with fractions) to SRT timestamp format."""
    millis = round(seconds * 1000)
    hours, remainder = divmod(millis, 3600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


_FFMPEG_ESCAPE_CHARACTERS = set("\\':,[]();=")


def _ffmpeg_escape_for_filter_arg(value: str) -> str:
    # For libavfilter args: escape backslash, colon, single-quote, spaces
    # Use forward slashes to avoid Windows backslash hell
    s = value.replace("\\", "/")
    s = s.replace(":", r"\:")      # escape drive colon C:\ -> C\:/
    s = s.replace("'", r"\'")      # escape single quotes
    s = s.replace(" ", r"\ ")      # escape spaces
    return s


def combine_video_audio_subtitles(
    video_path: Path,
    audio_path: Path,
    subtitles_path: Path,
    output_path: Path,
    segments: list[dict],
) -> None:
    sub_arg = _ffmpeg_escape_for_filter_arg(subtitles_path.resolve().as_posix())

    genshin_force_style = (
        "FontName=Montserrat SemiBold,"
        "FontSize=48,"
        "PrimaryColour=&H00E6E6E6,"
        "OutlineColour=&H001A1A1A,"
        "BackColour=&H64000000,"
        "BorderStyle=1,"
        "Outline=2.8,"
        "Shadow=0.8,"
        "Alignment=2,"
        "MarginV=40"          
    )

    subtitle_filter = f"subtitles=filename='{sub_arg}':fontsdir='fonts':force_style='{genshin_force_style}'"

    audio_secs = get_media_duration_seconds(audio_path)

    overlay_images = sorted(p for p in EMOTE_ROOT_DIR.rglob("*.png") if p.is_file()) if EMOTE_ROOT_DIR.exists() else []
    overlay_inputs: list[str] = []
    filter_complex_parts: list[str] = []

    base_label = "base0"

    filter_complex_parts.append(
        "[0:v]setpts=PTS-STARTPTS,"
        "scale=iw*1.1:ih*1.1,"
        "crop=iw/1.1:ih/1.1:(iw-iw/1.1)/2:(ih-ih/1.1)/2"
        f"[{base_label}]"
    )

    overlay_events: list[OverlayEvent] = []
    if audio_secs > 0 and overlay_images:
        rng = random.Random()

        def emote_cycle() -> Iterator[Path]:
            pool = overlay_images[:]
            while True:
                rng.shuffle(pool)
                for img in pool:
                    yield img

        emote_iter = emote_cycle()

        for segment in segments:
            seg_start = float(segment.get("start", 0.0))
            seg_end = float(segment.get("end", seg_start))
            seg_duration = max(0.0, seg_end - seg_start)
            if seg_duration <= 0:
                continue

            main_duration = seg_duration * LAYER1_DURATION_PORTION
            main_end = min(audio_secs, seg_end, seg_start + main_duration)
            if main_end > seg_start:
                fade_time = min(LAYER1_FADE_SECONDS, (main_end - seg_start) / 2)
                overlay_events.append(
                    OverlayEvent(
                        image_path=next(emote_iter),
                        start=seg_start,
                        end=main_end,
                        scale=0.5,
                        x_expr="(main_w-overlay_w)/2",
                        y_expr="(main_h-overlay_h)/2",
                        fade_in=fade_time,
                        fade_out=fade_time,
                    )
                )

            if seg_duration > LAYER2_TRIGGER_THRESHOLD:
                booster_start = seg_start + seg_duration * 0.55
                booster_start = min(booster_start, seg_end - 0.05)
                booster_start = max(seg_start, booster_start)
                booster_duration = rng.uniform(0.7, 1.2)
                booster_end = min(audio_secs, seg_end, booster_start + booster_duration)
                if booster_end > booster_start:
                    fade_time = min(LAYER2_FADE_SECONDS, (booster_end - booster_start) / 2)
                    offset_x = rng.uniform(-45, 45)
                    offset_y = rng.uniform(-50, 50)
                    overlay_events.append(
                        OverlayEvent(
                            image_path=next(emote_iter),
                            start=booster_start,
                            end=booster_end,
                            scale=0.5,
                            x_expr=f"(main_w-overlay_w)/2+{offset_x:.0f}",
                            y_expr=f"(main_h-overlay_h)/2+{offset_y:.0f}",
                            fade_in=fade_time,
                            fade_out=fade_time,
                        )
                    )

        corner_positions = {
            "top-left": ("main_w*0.05", "main_h*0.05"),
            "top-right": ("main_w-overlay_w-main_w*0.05", "main_h*0.05"),
            "bottom-left": ("main_w*0.05", "main_h-overlay_h-main_h*0.05"),
            "bottom-right": (
                "main_w-overlay_w-main_w*0.05",
                "main_h-overlay_h-main_h*0.05",
            ),
        }
        micro_time = 0.0
        while micro_time < audio_secs:
            micro_time += rng.uniform(LAYER3_MIN_GAP, LAYER3_MAX_GAP)
            if micro_time >= audio_secs:
                break
            micro_end = min(audio_secs, micro_time + rng.uniform(LAYER3_MIN_DURATION, LAYER3_MAX_DURATION))
            if micro_end <= micro_time:
                continue
            fade_time = min(LAYER3_FADE_SECONDS, (micro_end - micro_time) / 2)
            _, (x_expr, y_expr) = rng.choice(list(corner_positions.items()))
            overlay_events.append(
                OverlayEvent(
                    image_path=next(emote_iter),
                    start=micro_time,
                    end=micro_end,
                    scale=0.25,
                    x_expr=x_expr,
                    y_expr=y_expr,
                    fade_in=fade_time,
                    fade_out=fade_time,
                    opacity=MICRO_EMOTE_OPACITY,
                )
            )

    overlay_events.sort(key=lambda evt: evt.start)

    for idx, event in enumerate(overlay_events):
        overlay_inputs.extend(["-loop", "1", "-i", str(event.image_path)])

    for idx, event in enumerate(overlay_events):
        input_index = idx + 2
        scaled_label = f"emote{idx}"
        next_label = f"base{idx + 1}"
        event_duration = max(0.0, event.end - event.start)
        if event_duration <= 0:
            continue
        fade_in = min(event.fade_in, event_duration / 2)
        fade_out = min(event.fade_out, event_duration / 2)
        fade_out_start = event.end - fade_out
        filter_chain_parts = [
            f"[{input_index}:v]scale=iw*{event.scale}:ih*{event.scale}",
            "format=rgba",
        ]
        if event.opacity < 1.0:
            filter_chain_parts.append(f"colorchannelmixer=aa={event.opacity:.2f}")
        filter_chain_parts.append(
            f"fade=t=in:st={event.start:.3f}:d={fade_in:.3f}:alpha=1"
        )
        filter_chain_parts.append(
            f"fade=t=out:st={max(event.start, fade_out_start):.3f}:d={fade_out:.3f}:alpha=1"
        )
        filter_complex_parts.append(
            ",".join(filter_chain_parts) + f"[{scaled_label}]"
        )
        filter_complex_parts.append(
            f"[{base_label}][{scaled_label}]overlay={event.x_expr}:{event.y_expr}:"
            f"enable='between(t,{event.start:.3f},{event.end:.3f})'[{next_label}]"
        )
        base_label = next_label

    filter_complex_parts.append(f"[{base_label}]{subtitle_filter}[finalv]")
    filter_complex = ";".join(filter_complex_parts)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
    ]

    cmd.extend(overlay_inputs)

    cmd.extend([
        "-filter_complex",
        filter_complex,
        "-map",
        "[finalv]",
        "-map",
        "1:a:0",
        "-t",
        f"{audio_secs:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_path),
    ])
    
    run_ffmpeg_command(cmd)

def transcribe_audio(audio_path: Path, model_name: str, language: str | None) -> list[dict]:
    """Transcribe the provided audio using OpenAI Whisper."""
    try:
        import whisper
    except ImportError as exc: 
        raise RuntimeError(
            "The 'whisper' package is required. Install it via 'pip install openai-whisper'."
        ) from exc

    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path), language=language)
    # result = model.transcribe(str(audio_path), language=language, task = "translate") # force English output no matter what language the audio is
    return result.get("segments", [])


def write_srt(segments: list[dict], srt_path: Path) -> None:
    """Write Whisper segments to an SRT subtitle file."""
    lines = []
    for index, segment in enumerate(segments, start=1):
        start = format_timestamp(segment["start"])
        end = format_timestamp(segment["end"])
        text = segment["text"].strip()
        lines.append(str(index))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")

    srt_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a video using Video B's visuals, Video A's audio, and generated captions.")
    parser.add_argument("video_a", type=Path, help="Path to the video that provides the audio track.")
    parser.add_argument("video_b", type=Path, help="Path to the video that provides the visual track.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("final_video.mp4"),
        help="Path for the output video (default: final_video.mp4).",
    )
    parser.add_argument("--model", default="base", help="Whisper model name to use for transcription (default: base).")
    parser.add_argument("--language", default=None, help="Optional language hint for Whisper transcription.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep intermediate files for debugging purposes.")

    args = parser.parse_args()

    ensure_ffmpeg_available()

    video_a = args.video_a.resolve()
    video_b = args.video_b.resolve()
    output_video = args.output.resolve()
    output_video.parent.mkdir(parents=True, exist_ok=True)

    if not video_a.exists():
        sys.exit(f"Audio source video not found: {video_a}")
    if not video_b.exists():
        sys.exit(f"Visual source video not found: {video_b}")

    temp_dir_context = tempfile.TemporaryDirectory() if not args.keep_temp else None
    temp_dir_path = Path(temp_dir_context.name) if temp_dir_context else Path.cwd()
    try:
        audio_path = temp_dir_path / "extracted_audio.wav"
        extract_audio(video_a, audio_path)

        audio_len = get_media_duration_seconds(audio_path)
        video_b_len = get_media_duration_seconds(video_b)

        if video_b_len + 0.1 < audio_len:
            sys.exit(
                f"Error: Visual source (video_b) is too short.\n"
                f"video_b length = {video_b_len:.2f}s, audio length = {audio_len:.2f}s.\n"
                f"Please supply a visual that is >= the audio length."
            )

        print("Transcribing audio with Whisper...", flush=True)
        segments = transcribe_audio(audio_path, model_name=args.model, language=args.language)
        if not segments:
            sys.exit("Transcription produced no segments. Aborting.")

        srt_path = output_video.with_suffix(".srt")
        write_srt(segments, srt_path)
        print(f"Captions saved to {srt_path}")

        print("Combining visuals, audio, and captions...", flush=True)
        combine_video_audio_subtitles(video_b, audio_path, srt_path, output_video, segments)
        print(f"Final video written to {output_video}")
    finally:
        if temp_dir_context is not None:
            temp_dir_context.cleanup()


if __name__ == "__main__":
    main()