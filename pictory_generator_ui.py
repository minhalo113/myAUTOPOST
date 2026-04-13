import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import sys
import queue
from pathlib import Path

class RedirectText:
    """Redirects stdout to a tkinter Text widget using a thread-safe queue."""
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.queue = queue.Queue()
        self.update_widget()

    def write(self, string):
        self.queue.put(string)

    def flush(self):
        pass
        
    def update_widget(self):
        while not self.queue.empty():
            line = self.queue.get_nowait()
            self.text_widget.insert(tk.END, line)
            self.text_widget.see(tk.END)
        self.text_widget.after(100, self.update_widget)

class PictoryGeneratorUI:
    MODEL_CHOICES = ["tiny", "base", "small", "medium", "large"]
    RATIO_CHOICES = ["16:9", "9:16"]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Pictory-Style Video Generator")
        self.root.geometry("700x600")

        self.audio_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar(value=str(Path("pictory_final_video.mp4").resolve()))
        self.ratio_var = tk.StringVar(value=self.RATIO_CHOICES[0])
        self.model_var = tk.StringVar(value=self.MODEL_CHOICES[1])
        self.language_var = tk.StringVar()
        self.keep_temp_var = tk.BooleanVar(value=False)
        self.bg_music_var = tk.StringVar()
        self.music_volume_var = tk.DoubleVar(value=50.0)
        
        self.upload_youtube_var = tk.BooleanVar(value=False)
        self.youtube_channel_var = tk.StringVar()
        
        from youtube_uploader import YOUTUBE_CHANNELS
        self.channels_dict = YOUTUBE_CHANNELS
        if self.channels_dict:
            self.youtube_channel_var.set(list(self.channels_dict.keys())[0])

        self._build_ui()
        
    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Audio Source
        row_audio = ttk.Frame(main_frame)
        row_audio.pack(fill=tk.X, pady=5)
        ttk.Label(row_audio, text="Audio Source:", width=15).pack(side=tk.LEFT)
        ttk.Entry(row_audio, textvariable=self.audio_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row_audio, text="Browse", command=self._browse_audio).pack(side=tk.LEFT)

        # Output Video
        row_output = ttk.Frame(main_frame)
        row_output.pack(fill=tk.X, pady=5)
        ttk.Label(row_output, text="Output Video:", width=15).pack(side=tk.LEFT)
        ttk.Entry(row_output, textvariable=self.output_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row_output, text="Browse", command=self._browse_output).pack(side=tk.LEFT)

        # Background Music
        row_music = ttk.Frame(main_frame)
        row_music.pack(fill=tk.X, pady=5)
        ttk.Label(row_music, text="BG Music (opt):", width=15).pack(side=tk.LEFT)
        ttk.Entry(row_music, textvariable=self.bg_music_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row_music, text="Browse", command=self._browse_music).pack(side=tk.LEFT)

        row_music_vol = ttk.Frame(main_frame)
        row_music_vol.pack(fill=tk.X, pady=0)
        ttk.Label(row_music_vol, text="Music Volume:", width=15).pack(side=tk.LEFT)
        vol_scale = ttk.Scale(row_music_vol, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.music_volume_var)
        vol_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(row_music_vol, text="%").pack(side=tk.LEFT)

        # YouTube Upload
        yt_frame = ttk.LabelFrame(main_frame, text="YouTube Upload", padding=10)
        yt_frame.pack(fill=tk.X, pady=5)
        
        row_yt1 = ttk.Frame(yt_frame)
        row_yt1.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(row_yt1, text="Auto Upload to YouTube", variable=self.upload_youtube_var).pack(side=tk.LEFT)
        
        row_yt2 = ttk.Frame(yt_frame)
        row_yt2.pack(fill=tk.X, pady=2)
        ttk.Label(row_yt2, text="Channel:").pack(side=tk.LEFT)
        channel_cb = ttk.Combobox(row_yt2, textvariable=self.youtube_channel_var, values=list(self.channels_dict.keys()), state="readonly", width=30)
        channel_cb.pack(side=tk.LEFT, padx=5)
        ttk.Button(row_yt2, text="Setup YouTube Login (Run Once)", command=self._setup_youtube).pack(side=tk.RIGHT)


        # Options Frame
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding=10)
        options_frame.pack(fill=tk.X, pady=10)

        # Ratio & Model
        row_opt1 = ttk.Frame(options_frame)
        row_opt1.pack(fill=tk.X, pady=5)
        
        ttk.Label(row_opt1, text="Ratio:").pack(side=tk.LEFT)
        ratio_cb = ttk.Combobox(row_opt1, textvariable=self.ratio_var, values=self.RATIO_CHOICES, state="readonly", width=8)
        ratio_cb.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row_opt1, text="Whisper Model:").pack(side=tk.LEFT, padx=(20,0))
        model_cb = ttk.Combobox(row_opt1, textvariable=self.model_var, values=self.MODEL_CHOICES, state="readonly", width=10)
        model_cb.pack(side=tk.LEFT, padx=5)

        # Language & Keep Temp
        row_opt2 = ttk.Frame(options_frame)
        row_opt2.pack(fill=tk.X, pady=5)

        ttk.Label(row_opt2, text="Language (opt):").pack(side=tk.LEFT)
        ttk.Entry(row_opt2, textvariable=self.language_var, width=10).pack(side=tk.LEFT, padx=5)

        ttk.Checkbutton(row_opt2, text="Keep temp files", variable=self.keep_temp_var).pack(side=tk.LEFT, padx=(20,0))

        # Generate Button
        self.generate_btn = ttk.Button(main_frame, text="Generate Video", command=self._start_generation)
        self.generate_btn.pack(pady=10)

        # Console Output
        ttk.Label(main_frame, text="Console Output:").pack(anchor=tk.W)
        self.console = tk.Text(main_frame, wrap=tk.WORD, height=15)
        self.console.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(self.console, command=self.console.yview)
        self.console.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        sys.stdout = RedirectText(self.console)

    def _browse_audio(self):
        path = filedialog.askopenfilename(title="Select Audio/Video Source")
        if path:
            self.audio_path_var.set(path)

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Save Output Video As",
            defaultextension=".mp4",
            filetypes=[("MP4 files", "*.mp4")]
        )
        if path:
            self.output_path_var.set(path)

    def _browse_music(self):
        path = filedialog.askopenfilename(
            title="Select Background Music",
            filetypes=[("Audio files", "*.mp3 *.wav *.m4a *.aac")]
        )
        if path:
            self.bg_music_var.set(path)

    def _setup_youtube(self):
        channel_name = self.youtube_channel_var.get()
        if not channel_name:
            messagebox.showerror("Error", "Please select a channel first.")
            return
        url = self.channels_dict.get(channel_name)
        
        def run_setup():
            try:
                from youtube_uploader import setup_youtube_login
                setup_youtube_login(channel_name, url)
            except Exception as e:
                self.root.after(0, lambda e=e: messagebox.showerror("Error", str(e)))
                
        threading.Thread(target=run_setup, daemon=True).start()

    def _start_generation(self):
        audio_path = self.audio_path_var.get().strip()
        output_path = self.output_path_var.get().strip()
        
        if not audio_path:
            messagebox.showerror("Error", "Please select an audio source.")
            return
        if not output_path:
            messagebox.showerror("Error", "Please select an output file.")
            return
            
        ratio = self.ratio_var.get()
        model = self.model_var.get()
        language = self.language_var.get().strip() or None
        keep_temp = self.keep_temp_var.get()

        self.generate_btn.config(state=tk.DISABLED, text="Generating...")
        self.console.delete(1.0, tk.END)

        def run_thread():
            try:
                from pictory_generator import run_pictory_pipeline
                bg_music_path = self.bg_music_var.get().strip()
                music_volume = self.music_volume_var.get()
                
                run_pictory_pipeline(
                    audio_source=Path(audio_path),
                    output_video=Path(output_path),
                    ratio=ratio,
                    model=model,
                    language=language,
                    keep_temp=keep_temp,
                    bg_music_path=Path(bg_music_path) if bg_music_path else None,
                    music_volume=music_volume,
                    upload_to_youtube=self.upload_youtube_var.get(),
                    youtube_channel_name=self.youtube_channel_var.get(),
                    youtube_channel_url=self.channels_dict.get(self.youtube_channel_var.get())
                )
                self.root.after(0, lambda: messagebox.showinfo("Success", f"Video generated successfully:\n{output_path}"))
            except Exception as e:
                self.root.after(0, lambda e=e: messagebox.showerror("Error", str(e)))
            finally:
                self.root.after(0, lambda: self.generate_btn.config(state=tk.NORMAL, text="Generate Video"))

        threading.Thread(target=run_thread, daemon=True).start()


def main():
    root = tk.Tk()
    app = PictoryGeneratorUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
