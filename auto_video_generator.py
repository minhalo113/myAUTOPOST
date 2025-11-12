import argparse
import random
import re
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
MAIN_EMOTE_HEIGHT_PORTION = 0.20
MICRO_EMOTE_HEIGHT_PORTION = 0.10

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


def _format_progress_bar(percent: float, width: int = 30) -> str:
    clamped = max(0.0, min(100.0, percent))
    filled = int(round((clamped / 100.0) * width))
    filled = min(filled, width)
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {clamped:6.2f}%"


def run_ffmpeg_command(
    args: list[str],
    cwd: str | None = None,
    *,
    progress_total_seconds: float | None = None,
    progress_description: str = "Progress",
):
    ffmpeg_path = str(LOCAL_FFMPEG) if LOCAL_FFMPEG.exists() else shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg.exe not found in project folder or system PATH!")

    cmd = [ffmpeg_path] + (args[1:] if args and args[0] == "ffmpeg" else args)
    cmd_str = " ".join(cmd)
    # Helpful debug if you ever hit limits again:
    # print("FFmpeg cmd length:", len(" ".join(cmd)))

    if progress_total_seconds is None or progress_total_seconds <= 0:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg failed:\nCommand (len={len(cmd_str)}): {cmd_str}\n{result.stderr}"
            )
        return

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        bufsize=1,
    )

    stderr_lines: list[str] = []
    last_printed = None

    def _maybe_print(percent: float) -> None:
        nonlocal last_printed
        percent = max(0.0, min(100.0, percent))
        rounded = round(percent, 1)
        if last_printed is not None and abs(rounded - last_printed) < 0.1:
            return
        last_printed = rounded
        bar = _format_progress_bar(percent)
        print(f"\r{progress_description}: {bar}", end="", flush=True)

    returncode: int | None = None

    try:
        _maybe_print(0.0)
        time_pattern = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")
        while True:
            line = process.stderr.readline()
            if line == "" and process.poll() is not None:
                break
            if not line:
                continue
            stderr_lines.append(line)
            match = time_pattern.search(line)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = float(match.group(3))
                elapsed = hours * 3600 + minutes * 60 + seconds
                percent = (elapsed / progress_total_seconds) * 100.0
                _maybe_print(percent)

        # Drain any remaining output
        if process.stdout:
            process.stdout.read()

        returncode = process.wait()
        if returncode == 0:
            _maybe_print(100.0)
            print()
        elif last_printed is not None:
            print()
    finally:
        if process.stderr:
            process.stderr.close()
        if process.stdout:
            process.stdout.close()

    if returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed:\nCommand (len={len(cmd_str)}): {cmd_str}\n{''.join(stderr_lines)}"
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


def get_video_dimensions(path: Path) -> tuple[int, int]:
    """Return the width and height of the first video stream using ffprobe."""
    ffprobe = _resolve_ffprobe()
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}:\n{proc.stderr}")

    try:
        width_str, height_str = proc.stdout.strip().split("x", maxsplit=1)
        return int(width_str), int(height_str)
    except ValueError as exc:
        raise RuntimeError(
            f"Could not parse video dimensions for {path}: {proc.stdout.strip()}"
        ) from exc

def combine_video_audio_subtitles(
    video_path: Path,
    audio_path: Path,
    subtitles_path: Path,
    output_path: Path,
    segments: list[dict],
) -> None:
    stage_dir = output_path.parent / "_ffstage"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)

    rel_video = os.path.relpath(str(video_path), str(stage_dir))
    rel_audio = os.path.relpath(str(audio_path), str(stage_dir))

    staged_srt = stage_dir / "subs.srt"
    shutil.copy2(subtitles_path, staged_srt)

    script_fonts = Path(__file__).parent / "fonts"
    if script_fonts.exists():
        shutil.copytree(script_fonts, stage_dir / "fonts")

    overlay_images = sorted(p for p in EMOTE_ROOT_DIR.rglob("*.png") if p.is_file()) if EMOTE_ROOT_DIR.exists() else []
    staged_overlays: list[str] = []
    for idx, src in enumerate(overlay_images):
        short_name = f"o{idx:03d}{src.suffix.lower()}"
        dst = stage_dir / short_name
        # Copy only filenames you actually use (we’ll index by event below)
        shutil.copy2(src, dst)
        staged_overlays.append(short_name)

    # Build events as before
    audio_secs = get_media_duration_seconds(Path(audio_path))
    overlay_events: list[OverlayEvent] = []

    base_label = "base0"

    # Recreate your event logic (unchanged)
    if audio_secs > 0 and staged_overlays:
        rng = random.Random()

        def emote_cycle() -> Iterator[str]:
            pool = staged_overlays[:]
            while True:
                rng.shuffle(pool)
                for name in pool:
                    yield name

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
                        image_path=Path(next(emote_iter)),
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
                            image_path=Path(next(emote_iter)),
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
            "bottom-right": ("main_w-overlay_w-main_w*0.05", "main_h-overlay_h-main_h*0.05"),
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
                    image_path=Path(next(emote_iter)),
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

    _, base_video_height = get_video_dimensions(video_path)


    # Build inputs: [0] = video, [1] = audio, overlays start from [2]
    input_args = [
        "-y", "-i", rel_video,
        "-i", rel_audio,
    ]
    for evt in overlay_events:
        # evt.image_path is a short staged filename like o000.png
        input_args.extend(["-loop", "1", "-i", str(evt.image_path)])

    # Build filter graph text (short labels, short file refs)
    genshin_force_style = (
        "FontName=Montserrat SemiBold,"
        "FontSize=14,"
        "PrimaryColour=&H00E6E6E6,"
        "OutlineColour=&H001A1A1A,"
        "BackColour=&H64000000,"
        "BorderStyle=1,"
        "Outline=2.8,"
        "Shadow=0.8,"
        "Alignment=2,"
        "MarginV=40"
    )
    subtitle_filter = f"subtitles=filename='subs.srt':fontsdir='fonts':force_style='{genshin_force_style}'"

    filter_lines = []
    filter_lines.append(
        "[0:v]setpts=PTS-STARTPTS,scale=iw*1.1:ih*1.1,"
        "crop=iw/1.1:ih/1.1:(iw-iw/1.1)/2:(ih-ih/1.1)/2[base0]"
    )

    base_label = "base0"
    for idx, event in enumerate(overlay_events):
        input_index = idx + 2  # due to [0]=video, [1]=audio
        scaled_src_label = f"e{idx}src"
        scaled_label = f"e{idx}"
        ref_label = f"base{idx}_ref"
        next_label = f"base{idx+1}"
        event_duration = max(0.0, event.end - event.start)
        if event_duration <= 0:
            continue
        fade_in = min(event.fade_in, event_duration / 2)
        fade_out = min(event.fade_out, event_duration / 2)
        fade_out_start = event.end - fade_out

        target_height_ratio = (
            MAIN_EMOTE_HEIGHT_PORTION
            if event.scale >= 0.5
            else MICRO_EMOTE_HEIGHT_PORTION
        )

        target_height_px = max(1, int(round(base_video_height * target_height_ratio)))
        filter_lines.append(
            f"[{input_index}:v]scale=w=-1:h={target_height_px}[{scaled_src_label}]"
        )

        chain = [f"[{scaled_src_label}]format=rgba"]
        if event.opacity < 1.0:
            chain.append(f"colorchannelmixer=aa={event.opacity:.2f}")
        chain.append(f"fade=t=in:st={event.start:.3f}:d={fade_in:.3f}:alpha=1")
        chain.append(f"fade=t=out:st={max(event.start, fade_out_start):.3f}:d={fade_out:.3f}:alpha=1")
        filter_lines.append(",".join(chain) + f"[{scaled_label}]")

        filter_lines.append(
            f"[{base_label}][{scaled_label}]overlay={event.x_expr}:{event.y_expr}:"
            f"enable='between(t,{event.start:.3f},{event.end:.3f})'[{next_label}]"
        )
        base_label = next_label

    filter_lines.append(f"[{base_label}]{subtitle_filter}[finalv]")

    # Write the filter graph to a file
    fgraph_path = stage_dir / "graph.ffscript"
    fgraph_path.write_text(";\n".join(filter_lines), encoding="utf-8")

    # Assemble final args (short!)
    final_args = (
        ["ffmpeg"]
        + input_args
        + [
            "-filter_complex_script", "graph.ffscript",
            "-map", "[finalv]",
            "-map", "1:a:0",
            "-t", f"{audio_secs:.3f}",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            os.path.relpath(str(output_path), str(stage_dir)),  # write to target path via relative
        ]
    )

    # Run with cwd set to stage_dir so everything is short & relative
    run_ffmpeg_command(
        final_args,
        cwd=str(stage_dir),
        progress_total_seconds=audio_secs,
        progress_description="Muxing media",
    )

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