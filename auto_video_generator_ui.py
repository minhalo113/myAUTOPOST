from __future__ import annotations

import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from auto_video_generator import (
    combine_video_audio_subtitles,
    ensure_ffmpeg_available,
    extract_audio,
    get_media_duration_seconds,
    transcribe_audio,
    write_srt,
)


class AutoVideoGeneratorUI:
    """Tkinter application for configuring and running the video generator."""

    MODEL_CHOICES = [
        "tiny",
        "base",
        "small",
        "medium",
        "large",
    ]

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Auto Video Generator")

        self.video_a_var = tk.StringVar()
        self.video_b_var = tk.StringVar()
        self.output_var = tk.StringVar(value="final_video.mp4")
        self.model_var = tk.StringVar(value="base")
        self.language_var = tk.StringVar()
        self.keep_temp_var = tk.BooleanVar(value=False)
        self.captions_only_var = tk.BooleanVar(value = False)
        self.status_var = tk.StringVar(value="Select your files and click Generate.")

        self.generate_button: tk.Button | None = None
        self.video_b_entry: tk.Entry | None = None
        self.video_b_button: tk.Button | None = None

        self._build_widgets()

    # ------------------------------------------------------------------
    # UI construction helpers
    # ------------------------------------------------------------------
    def _build_widgets(self) -> None:
        padding = {"padx": 10, "pady": 5, "sticky": "w"}

        # Audio source
        tk.Label(self.root, text="Audio source video:").grid(row=0, column=0, **padding)
        tk.Entry(self.root, textvariable=self.video_a_var, width=60).grid(row=0, column=1, **padding)
        tk.Button(self.root, text="Browse", command=self._browse_video_a).grid(row=0, column=2, padx=10, pady=5)

        # Visual source
        tk.Label(self.root, text="Visual source video:").grid(row=1, column=0, **padding)
        video_b_entry = tk.Entry(self.root, textvariable=self.video_b_var, width=60)
        video_b_entry.grid(row=1, column=1, **padding)
        self.video_b_entry = video_b_entry

        video_b_button = tk.Button(self.root, text="Browse", command=self._browse_video_b)
        video_b_button.grid(row=1, column=2, padx=10, pady=5)
        self.video_b_button = video_b_button

        # Output path
        tk.Label(self.root, text="Output path:").grid(row=2, column=0, **padding)
        tk.Entry(self.root, textvariable=self.output_var, width=60).grid(row=2, column=1, **padding)
        tk.Button(self.root, text="Choose", command=self._choose_output).grid(row=2, column=2, padx=10, pady=5)

        # Whisper model selection
        tk.Label(self.root, text="Whisper model:").grid(row=3, column=0, **padding)
        tk.OptionMenu(self.root, self.model_var, *self.MODEL_CHOICES).grid(row=3, column=1, sticky="w", padx=10, pady=5)

        # Optional language hint
        tk.Label(self.root, text="Language hint (optional):").grid(row=4, column=0, **padding)
        tk.Entry(self.root, textvariable=self.language_var, width=20).grid(row=4, column=1, sticky="w", padx=10, pady=5)

        tk.Checkbutton(
            self.root,
            text="Generate captions only (.srt)",
            variable=self.captions_only_var,
            command=self._toggle_captions_only,
        ).grid(row=5, column=1, sticky="w", padx=10, pady=5)

        # Keep temp files option
        tk.Checkbutton(
            self.root,
            text="Keep temporary files",
            variable=self.keep_temp_var,
        ).grid(row=6, column=1, sticky="w", padx=10, pady=5)

        # Status label
        tk.Label(self.root, textvariable=self.status_var, fg="blue").grid(
            row=7, column=0, columnspan=3, padx=10, pady=10, sticky="w"
        )

        # Control buttons
        button_frame = tk.Frame(self.root)
        button_frame.grid(row=8, column=0, columnspan=3, pady=10)

        tk.Button(button_frame, text="Clear", command=self._clear_fields).grid(row=0, column=0, padx=5)
        self.generate_button = tk.Button(button_frame, text="Generate", command=self._start_generation)
        self.generate_button.grid(row=0, column=1, padx=5)
        tk.Button(button_frame, text="Quit", command=self.root.quit).grid(row=0, column=2, padx=5)

        self._toggle_captions_only()

    # ------------------------------------------------------------------
    # Browse helpers
    # ------------------------------------------------------------------
    def _browse_video_a(self) -> None:
        path = filedialog.askopenfilename(
            title="Select video for audio",
            filetypes=[("Video files", "*.mp4 *.mov *.mkv *.avi *.webm"), ("All files", "*.*")],
        )
        if path:
            self.video_a_var.set(path)

    def _browse_video_b(self) -> None:
        path = filedialog.askopenfilename(
            title="Select video for visuals",
            filetypes=[("Video files", "*.mp4 *.mov *.mkv *.avi *.webm"), ("All files", "*.*")],
        )
        if path:
            self.video_b_var.set(path)

    def _choose_output(self) -> None:
        if self.captions_only_var.get():
            path = filedialog.asksaveasfilename(
                title="Choose captions file",
                defaultextension=".srt",
                filetypes=[("SubRip Subtitle", "*.srt"), ("All files", "*.*")],
                initialfile=self.output_var.get() or "captions.srt",
            )
        else:
            path = filedialog.asksaveasfilename(
                title="Choose output video",
                defaultextension=".mp4",
                filetypes=[("MP4 Video", "*.mp4"), ("All files", "*.*")],
                initialfile=self.output_var.get() or "final_video.mp4",
            )
        if path:
            self.output_var.set(path)

    def _clear_fields(self) -> None:
        self.video_a_var.set("")
        self.video_b_var.set("")
        self.output_var.set("final_video.mp4")
        self.language_var.set("")
        self.captions_only_var.set(False)
        self._toggle_captions_only()
        self.status_var.set("Select your files and click Generate.")

    # ------------------------------------------------------------------
    # Generation logic
    # ------------------------------------------------------------------
    def _start_generation(self) -> None:
        if self.generate_button:
            self.generate_button.config(state=tk.DISABLED)
        self.status_var.set("Preparing to generate video...")
        threading.Thread(target=self._generate_video, daemon=True).start()

    def _generate_video(self) -> None:
        try:
            video_a_path = Path(self.video_a_var.get()).expanduser()
            video_b_path = Path(self.video_b_var.get()).expanduser()

            model_name = self.model_var.get().strip() or "base"
            language = self.language_var.get().strip() or None
            captions_only = self.captions_only_var.get()

            output_value = self.output_var.get().strip()
            if not output_value:
                output_value = "captions.srt" if captions_only else "final_video.mp4"
                self.output_var.set(output_value)
            output_path = Path(output_value).expanduser()

            if not video_a_path.is_file():
                raise FileNotFoundError(f"Audio source video not found: {video_a_path}")
            if captions_only:
                if output_path.suffix.lower() != ".srt":
                    output_path = output_path.with_suffix(".srt")
                    self.output_var.set(str(output_path))
            else:
                if not video_b_path.is_file():
                    raise FileNotFoundError(f"Visual source video not found: {video_b_path}")
                if output_path.suffix.lower() != ".mp4":
                    output_path = output_path.with_suffix(".mp4")
                    self.output_var.set(str(output_path))
            output_path.parent.mkdir(parents=True, exist_ok=True)

            self._update_status("Checking ffmpeg availability...")
            ensure_ffmpeg_available()

            keep_temp = self.keep_temp_var.get()
            temp_dir_context = tempfile.TemporaryDirectory() if not keep_temp else None
            temp_dir = Path(temp_dir_context.name) if temp_dir_context else output_path.parent

            audio_path = temp_dir / "extracted_audio.wav"
            self._update_status("Extracting audio...")
            extract_audio(video_a_path, audio_path)

            if not captions_only:
                audio_len = get_media_duration_seconds(audio_path)
                video_b_len = get_media_duration_seconds(video_b_path)
                if video_b_len + 0.1 < audio_len:
                    raise RuntimeError(
                        "Visual source video is shorter than the audio track. "
                        "Please select a longer visual clip."
                    )

            self._update_status("Transcribing audio (this may take a while)...")
            segments = transcribe_audio(audio_path, model_name=model_name, language=language)
            if not segments:
                raise RuntimeError("Transcription produced no segments. Aborting.")

            srt_path = output_path.with_suffix(".srt")
            self._update_status("Writing subtitles...")
            write_srt(segments, srt_path)

            if captions_only:
                self._update_status(f"Done! Captions saved to {srt_path}")
                messagebox.showinfo("Success", f"Captions file created successfully:\n{srt_path}")
            else:
                self._update_status("Combining audio, visuals, and captions...")
                combine_video_audio_subtitles(
                    video_b_path, audio_path, srt_path, output_path, segments
                )
            
                self._update_status(f"Done! Final video saved to {output_path}")
                messagebox.showinfo("Success", f"Video created successfully:\n{output_path}")
        except Exception as exc:  # noqa: BLE001 - show any exception to the user
            messagebox.showerror("Error", str(exc))
            self._update_status("An error occurred. Please check your settings and try again.")
        finally:
            if 'temp_dir_context' in locals() and temp_dir_context is not None:
                temp_dir_context.cleanup()
            if self.generate_button:
                self.generate_button.config(state=tk.NORMAL)

    def _update_status(self, message: str) -> None:
        self.status_var.set(message)

    def _toggle_captions_only(self) -> None:
        captions_only = self.captions_only_var.get()
        state = tk.DISABLED if captions_only else tk.NORMAL
        if self.video_b_entry is not None:
            self.video_b_entry.config(state=state)
        if self.video_b_button is not None:
            self.video_b_button.config(state=state)

        if captions_only:
            self.video_b_var.set("")
            current = self.output_var.get().strip()
            if not current.lower().endswith(".srt"):
                new_value = str(Path(current).with_suffix(".srt")) if current else "captions.srt"
                self.output_var.set(new_value)
        else:
            current = self.output_var.get().strip()
            if not current.lower().endswith(".mp4"):
                new_value = str(Path(current).with_suffix(".mp4")) if current else "final_video.mp4"
                self.output_var.set(new_value)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = AutoVideoGeneratorUI()
    app.run()


if __name__ == "__main__":
    main()