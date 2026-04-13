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
                run_pictory_pipeline(
                    audio_source=Path(audio_path),
                    output_video=Path(output_path),
                    ratio=ratio,
                    model=model,
                    language=language,
                    keep_temp=keep_temp
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
