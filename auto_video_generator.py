import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
import shutil
import os

LOCAL_FFMPEG = Path(__file__).parent / "ffmpeg" / "bin" / "ffmpeg.exe"
FFMPEG_BIN_DIR = (Path(__file__).parent / "ffmpeg" / "bin").resolve()
os.environ["PATH"] = str(FFMPEG_BIN_DIR) + os.pathsep + os.environ.get("PATH", "")

LOCAL_FFPROBE = Path(__file__).parent / "ffmpeg" / "bin" / "ffprobe.exe"

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


def combine_video_audio_subtitles(video_path: Path, audio_path: Path, subtitles_path: Path, output_path: Path) -> None:
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

    run_ffmpeg_command([
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-t", f"{audio_secs:.3f}",  
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-vf", subtitle_filter,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_path),
    ])


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
        combine_video_audio_subtitles(video_b, audio_path, srt_path, output_video)
        print(f"Final video written to {output_video}")
    finally:
        if temp_dir_context is not None:
            temp_dir_context.cleanup()


if __name__ == "__main__":
    main()