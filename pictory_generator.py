import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import json
import random
import urllib.request
import urllib.error
import urllib.parse
import re
from pathlib import Path
from typing import Iterator

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
    ffmpeg_path = str(LOCAL_FFMPEG) if LOCAL_FFMPEG.exists() else shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg.exe not found in project folder or system PATH!")
    try:
        subprocess.run([ffmpeg_path, "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

    if progress_total_seconds is None or progress_total_seconds <= 0:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg failed:\nCommand: {cmd_str}\n{result.stderr}"
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
            f"FFmpeg failed:\nCommand: {cmd_str}\n{''.join(stderr_lines)}"
        )

def extract_audio(video_path: Path, audio_path: Path) -> None:
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
    millis = round(seconds * 1000)
    hours, remainder = divmod(millis, 3600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def transcribe_audio(audio_path: Path, model_name: str, language: str | None) -> list[dict]:
    try:
        import whisper
    except ImportError as exc: 
        raise RuntimeError(
            "The 'whisper' package is required. Install it via 'pip install openai-whisper'."
        ) from exc

    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path), language=language)
    return result.get("segments", [])

def write_srt(segments: list[dict], srt_path: Path) -> None:
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

def group_segments_into_blocks(segments: list[dict], min_duration: float = 4.0) -> list[dict]:
    """Group transcription segments into blocks of at least min_duration seconds."""
    blocks = []
    current_block = None

    for segment in segments:
        if current_block is None:
            current_block = {
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"],
                "segments": [segment]
            }
        else:
            current_block["end"] = segment["end"]
            current_block["text"] += " " + segment["text"]
            current_block["segments"].append(segment)

        if current_block["end"] - current_block["start"] >= min_duration:
            blocks.append(current_block)
            current_block = None

    if current_block is not None:
        if blocks:
            blocks[-1]["end"] = current_block["end"]
            blocks[-1]["text"] += " " + current_block["text"]
            blocks[-1]["segments"].extend(current_block["segments"])
        else:
            blocks.append(current_block)

    return blocks


def generate_youtube_metadata(text: str, openai_key: str) -> tuple[str, str]:
    """Use OpenAI to generate a catchy YouTube title and description based on the full transcript."""
    if not openai_key:
        return "Auto Generated Video", "This video was generated automatically."

    try:
        from openai import OpenAI
        import json
        client = OpenAI(api_key=openai_key)
        
        prompt = (
            "You are a professional YouTube content creator. Read the following video transcript and provide a "
            "catchy, engaging YouTube video title and a detailed description with hashtags. "
            "Return the result EXACTLY as a JSON object with two keys: 'title' and 'description'.\n\n"
            f"Transcript: \"{text}\""
        )
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("title", "Auto Generated Video"), data.get("description", "This video was generated automatically.")
    except Exception as e:
        print(f"Error generating YouTube metadata: {e}")
        return "Auto Generated Video", "This video was generated automatically."

def generate_search_query_for_block(text: str, openai_key: str) -> str:
    """Use OpenAI API to generate a concise search query based on the text block."""
    if not openai_key:
        return "abstract background"

    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        
        prompt = (
            f"You are a stock footage search assistant. Read the following text and provide a very concise "
            f"search query (1 to 3 words max) that visually represents the core subject or action in the text. "
            f"Do not include quotes, periods, or any conversational text. Just the search keywords.\n\n"
            f"Text: \"{text}\""
        )
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=10,
        )
        query = response.choices[0].message.content.strip().replace('"', '').replace('.', '')
        return query if query else "abstract background"
    except Exception as e:
        print(f"Error generating search query: {e}")
        return "abstract background"

def fetch_from_pexels(query: str, api_key: str, min_width: int, min_height: int) -> str | None:
    if not api_key:
        return None
    
    url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&per_page=5"
    req = urllib.request.Request(url, headers={"Authorization": api_key})
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if not data.get("videos"):
                return None
            
            videos = data["videos"]
            random.shuffle(videos)
            
            for video in videos:
                video_files = video.get("video_files", [])
                video_files.sort(key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)
                for vf in video_files:
                    if vf.get("link"):
                        return vf["link"]
            return None
    except Exception as e:
        print(f"Pexels fetch failed for '{query}': {e}")
        return None

def fetch_from_pixabay(query: str, api_key: str) -> str | None:
    if not api_key:
        return None
        
    url = f"https://pixabay.com/api/videos/?key={api_key}&q={urllib.parse.quote(query)}&per_page=5"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if not data.get("hits"):
                return None
            
            hits = data["hits"]
            random.shuffle(hits)
            
            for hit in hits:
                videos = hit.get("videos", {})
                # prefer large or medium
                for size in ["large", "medium", "small"]:
                    if size in videos and videos[size].get("url"):
                        return videos[size]["url"]
            return None
    except Exception as e:
        print(f"Pixabay fetch failed for '{query}': {e}")
        return None

def get_stock_video_url(query: str, pexels_key: str | None, pixabay_key: str | None, ratio: str) -> str | None:
    sources = []
    if pexels_key:
        sources.append("pexels")
    if pixabay_key:
        sources.append("pixabay")
        
    if not sources:
        print("Warning: Neither PEXELS_API_KEY nor PIXABAY_API_KEY is available. Cannot fetch stock video.")
        return None
        
    random.shuffle(sources)
    
    min_w = 1920 if ratio == "16:9" else 1080
    min_h = 1080 if ratio == "16:9" else 1920

    for source in sources:
        if source == "pexels":
            url = fetch_from_pexels(query, pexels_key, min_w, min_h)
            if url: return url
        elif source == "pixabay":
            url = fetch_from_pixabay(query, pixabay_key)
            if url: return url
            
    if query != "abstract background":
        return get_stock_video_url("abstract background", pexels_key, pixabay_key, ratio)
        
    return None

def download_video(url: str, output_path: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(output_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        return True
    except Exception as e:
        print(f"Failed to download video from {url}: {e}")
        return False

def process_stock_video_for_block(
    input_video: Path,
    output_video: Path,
    target_duration: float,
    ratio: str
) -> bool:
    """Process a downloaded stock video to exactly match target duration and resolution."""
    duration = get_media_duration_seconds(input_video)
    if duration <= 0:
        return False
        
    target_w = 1920 if ratio == "16:9" else 1080
    target_h = 1080 if ratio == "16:9" else 1920

    fps = 30
    
    filter_complex = [
        f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},boxblur=20:20[bg];"
        f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={fps}[v_scaled]"
    ]

    cmd = [
        "ffmpeg", "-y",
    ]
    
    if duration >= target_duration:
        cmd.extend(["-t", str(target_duration), "-i", str(input_video)])
        cmd.extend(["-filter_complex", "".join(filter_complex), "-map", "[v_scaled]"])
    else:
        loops = int(target_duration // duration) + 1
        cmd.extend(["-stream_loop", str(loops), "-i", str(input_video), "-t", str(target_duration)])
        cmd.extend(["-filter_complex", "".join(filter_complex), "-map", "[v_scaled]"])
        
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output_video)
    ])
    
    try:
        run_ffmpeg_command(cmd, progress_description=f"Processing {input_video.name}")
        return True
    except Exception as e:
        print(f"Failed to process {input_video}: {e}")
        return False

def concat_videos(video_paths: list[Path], output_path: Path) -> None:
    """Concatenate multiple videos into one using ffmpeg concat filter/demuxer."""
    if not video_paths:
        raise ValueError("No videos to concatenate.")
        
    list_file = output_path.parent / "concat_list.txt"
    with open(list_file, "w") as f:
        for p in video_paths:
            path_str = str(p.absolute()).replace("\\", "/")
            f.write(f"file '{path_str}'\n")
            
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path)
    ]
    
    run_ffmpeg_command(cmd, progress_description="Concatenating visual blocks")

def combine_pictory_final(
    visual_video: Path,
    audio_path: Path,
    subtitles_path: Path,
    output_path: Path,
    bg_music_path: Path | None = None,
    music_volume: float = 20.0,
) -> None:
    stage_dir = output_path.parent / "_pictory_stage"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)

    rel_video = os.path.relpath(str(visual_video), str(stage_dir))
    rel_audio = os.path.relpath(str(audio_path), str(stage_dir))

    staged_srt = stage_dir / "subs.srt"
    shutil.copy2(subtitles_path, staged_srt)

    script_fonts = Path(__file__).parent / "fonts"
    if script_fonts.exists():
        shutil.copytree(script_fonts, stage_dir / "fonts")
        
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
    
    fontsdir_opt = "fontsdir='fonts':" if script_fonts.exists() else ""
    subtitle_filter = f"subtitles=filename='subs.srt':{fontsdir_opt}force_style='{genshin_force_style}'"

    cmd = [
        "ffmpeg", "-y",
        "-i", rel_video,
        "-i", rel_audio,
    ]
    
    if bg_music_path and bg_music_path.exists() and music_volume > 0:
        rel_bg = os.path.relpath(str(bg_music_path), str(stage_dir))
        cmd.extend(["-stream_loop", "-1", "-i", rel_bg])
        vol = music_volume / 100.0
        audio_filter = f"[2:a]volume={vol}[bg];[1:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        cmd.extend(["-filter_complex", audio_filter, "-map", "0:v", "-map", "[aout]"])
    else:
        cmd.extend(["-map", "0:v", "-map", "1:a"])

    cmd.extend([
        "-vf", subtitle_filter,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        os.path.relpath(str(output_path), str(stage_dir))
    ])
    
    audio_secs = get_media_duration_seconds(audio_path)
    run_ffmpeg_command(
        cmd,
        cwd=str(stage_dir),
        progress_total_seconds=audio_secs,
        progress_description="Final Compositing"
    )


def run_pictory_pipeline(
    audio_source: Path,
    output_video: Path,
    ratio: str = "16:9",
    model: str = "base",
    language: str | None = None,
    keep_temp: bool = False,
    bg_music_path: Path | None = None,
    music_volume: float = 20.0,
    upload_to_youtube: bool = False,
    youtube_channel_name: str | None = None,
    youtube_channel_url: str | None = None
) -> None:
    ensure_ffmpeg_available()
    
    openai_key = None
    pexels_key = None
    pixabay_key = None
    try:
        from config import OPENAI_KEY
        openai_key = OPENAI_KEY
    except ImportError:
        print("Warning: Could not import OPENAI_KEY from config.py.")
        
    try:
        from config import PEXELS_API_KEY
        pexels_key = PEXELS_API_KEY
    except ImportError:
        pass
        
    try:
        from config import PIXABAY_API_KEY
        pixabay_key = PIXABAY_API_KEY
    except ImportError:
        pass

    if not audio_source.exists():
        raise FileNotFoundError(f"Audio source file not found: {audio_source}")
        
    print(f"Starting Pictory Generator for {audio_source}")
    
    temp_dir_context = tempfile.TemporaryDirectory() if not keep_temp else None
    temp_dir_path = Path(temp_dir_context.name) if temp_dir_context else Path.cwd() / "temp_pictory"
    temp_dir_path.mkdir(exist_ok=True)
    
    try:
        audio_path = temp_dir_path / "extracted_audio.wav"
        print("Extracting audio...", flush=True)
        extract_audio(audio_source, audio_path)
        
        print("Transcribing audio with Whisper...", flush=True)
        audio_secs = get_media_duration_seconds(audio_path)
        segments = transcribe_audio(audio_path, model_name=model, language=language)
        if not segments:
            raise RuntimeError("Transcription produced no segments. Aborting.")
            
        srt_path = output_video.with_suffix(".srt")
        write_srt(segments, srt_path)
        print(f"Captions saved to {srt_path}")
        
        blocks = group_segments_into_blocks(segments, min_duration=4.0)
        processed_blocks = []
        
        for i, block in enumerate(blocks):
            current_start = block["start"] if i > 0 else 0.0
            if i < len(blocks) - 1:
                target_duration = blocks[i+1]["start"] - current_start
            else:
                target_duration = audio_secs - current_start if 'audio_secs' in locals() else (block["end"] - current_start + 1.0)

                
            print(f"\nProcessing block {i+1}/{len(blocks)} (Duration: {target_duration:.2f}s): \"{block['text'][:50]}...\"")
            
            query = generate_search_query_for_block(block["text"], openai_key)
            print(f"Generated query: '{query}'")
            
            video_url = get_stock_video_url(query, pexels_key, pixabay_key, ratio)
            
            raw_video_path = temp_dir_path / f"raw_block_{i}.mp4"
            processed_video_path = temp_dir_path / f"processed_block_{i}.mp4"
            
            success = False
            if video_url:
                print(f"Downloading video from {video_url[:50]}...")
                if download_video(video_url, raw_video_path):
                    print("Processing downloaded video...")
                    success = process_stock_video_for_block(raw_video_path, processed_video_path, target_duration, ratio)
            
            if not success:
                print("Using blank fallback video block...")
                w = 1920 if ratio == "16:9" else 1080
                h = 1080 if ratio == "16:9" else 1920
                cmd = [
                    "ffmpeg", "-y", "-f", "lavfi", f"-i", f"color=c=black:s={w}x{h}:r=30:d={target_duration}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(processed_video_path)
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
            processed_blocks.append(processed_video_path)
            
        print("\nStitching visual blocks...", flush=True)
        stitched_visual_path = temp_dir_path / "stitched_visual.mp4"
        concat_videos(processed_blocks, stitched_visual_path)
        
        print("\nFinal Compositing (Audio + Visual + Subtitles)...", flush=True)
        combine_pictory_final(stitched_visual_path, audio_path, srt_path, output_video, bg_music_path, music_volume)
        print(f"\nFinal video written to {output_video}")
        
        stage_dir = output_video.parent / "_pictory_stage"
        if not keep_temp and stage_dir.exists():
            import shutil
            shutil.rmtree(stage_dir, ignore_errors=True)
        
        if upload_to_youtube and youtube_channel_url:
            print("\nGenerating YouTube Title & Description...")
            full_transcript = " ".join([seg["text"] for seg in segments])
            yt_title, yt_desc = generate_youtube_metadata(full_transcript, openai_key)
            print(f"Title: {yt_title}")
            
            try:
                from youtube_uploader import upload_to_youtube as yt_upload
                yt_upload(output_video, yt_title, yt_desc, youtube_channel_name, youtube_channel_url)
            except ImportError:
                print("Warning: youtube_uploader module not found. Skipping YouTube upload.")
            except Exception as e:
                print(f"YouTube Upload failed: {e}")
                
    finally:
        if temp_dir_context is not None:
            temp_dir_context.cleanup()

def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Pictory-style video using stock footage and AI-generated captions.")
    parser.add_argument("audio_source", type=Path, help="Path to the media file that provides the audio track.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("pictory_final_video.mp4"),
        help="Path for the output video (default: pictory_final_video.mp4).",
    )
    parser.add_argument(
        "--ratio",
        choices=["16:9", "9:16"],
        default="16:9",
        help="Aspect ratio for the output video (default: 16:9)."
    )
    parser.add_argument("--model", default="base", help="Whisper model name to use for transcription (default: base).")
    parser.add_argument("--language", default=None, help="Optional language hint for Whisper transcription.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep intermediate files for debugging purposes.")

    args = parser.parse_args()
    
    try:
        run_pictory_pipeline(
            audio_source=args.audio_source.resolve(),
            output_video=args.output.resolve(),
            ratio=args.ratio,
            model=args.model,
            language=args.language,
            keep_temp=args.keep_temp
        )
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
