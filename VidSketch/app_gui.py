"""Einfache Oberfläche für VidSketch-Inferenz.

Startet inference.py mit den eingegebenen Werten und zeigt die Ausgabe live an.
Nutzt nur die Standardbibliothek (tkinter), keine zusätzlichen Pakete nötig.

Start (im Ordner VidSketch\\VidSketch):
    python app_gui.py
"""

import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
INFERENCE = os.path.join(HERE, "inference.py")
DEFAULT_WEIGHT_DIR = os.path.normpath(os.path.join(HERE, "..", "Pretrained Weights"))
DEFAULT_PRETRAIN = "stable-diffusion-v1-5/stable-diffusion-v1-5"
# tqdm-Zeile, z. B. "  8%|8   | 4/50 [01:30<17:11, 22.43s/it]"
TQDM_RE = re.compile(r"(\d+)/(\d+) \[")


def build_command(values):
    """Baut den Aufruf von inference.py aus den Formularwerten. Wirft ValueError bei Fehlern."""
    prompt = values["prompt"].strip()
    if not prompt:
        raise ValueError("Bitte einen Prompt eingeben.")
    for key, label in (("image_path", "Ordner mit dem ersten Frame"),
                       ("sketch_path", "Skizzen-Ordner")):
        path = values[key].strip()
        if not path or not os.path.isdir(path):
            raise ValueError(f"{label} fehlt oder existiert nicht.")
    weight = values["weight"].strip()
    if weight and not os.path.exists(weight):
        raise ValueError("Gewichte-Pfad existiert nicht.")
    output = values["output_path"].strip()
    if not output:
        raise ValueError("Bitte einen Ausgabeordner angeben.")

    cmd = [sys.executable, "-u", INFERENCE,
           "--pretrain_weight", values["pretrain_weight"].strip() or DEFAULT_PRETRAIN,
           "-p", prompt,
           "--length", str(int(values["length"])),
           "--image_path", values["image_path"].strip(),
           "--sketch_path", values["sketch_path"].strip(),
           "--output_path", output]
    if weight:
        cmd += ["--weight", weight]
    lora = values["lora_weights"].strip()
    if lora:
        cmd += ["--lora_weights", lora]
    return cmd


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VidSketch")
        self.geometry("820x640")
        self.minsize(700, 560)
        self.proc = None
        self.log_queue = queue.Queue()

        self.vars = {
            "prompt": tk.StringVar(value="A candle burning quietly."),
            "length": tk.StringVar(value="10"),
            "image_path": tk.StringVar(),
            "sketch_path": tk.StringVar(),
            "weight": tk.StringVar(value=DEFAULT_WEIGHT_DIR),
            "lora_weights": tk.StringVar(),
            "pretrain_weight": tk.StringVar(value=DEFAULT_PRETRAIN),
            "output_path": tk.StringVar(value=os.path.join(HERE, "results", "gui_lauf")),
        }

        form = ttk.Frame(self, padding=12)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        self._row(form, 0, "Prompt", self.vars["prompt"])
        self._row(form, 1, "Frames (--length)", self.vars["length"], width=8)
        self._row(form, 2, "Erster-Frame-Ordner (--image_path)", self.vars["image_path"],
                  browse="dir", hint="Ein Video pro Bild in diesem Ordner")
        self._row(form, 3, "Skizzen-Ordner (--sketch_path)", self.vars["sketch_path"],
                  browse="dir", hint="Skizzen, sortiert nach Dateiname")
        self._row(form, 4, "Gewichte (--weight)", self.vars["weight"],
                  browse="dir", hint="Ordner mit den Pretrained Weights")
        self._row(form, 5, "LoRA-Gewichte (optional)", self.vars["lora_weights"], browse="file")
        self._row(form, 6, "Basismodell (--pretrain_weight)", self.vars["pretrain_weight"],
                  hint="Hugging-Face-ID oder lokaler Pfad")
        self._row(form, 7, "Ausgabeordner (--output_path)", self.vars["output_path"],
                  browse="dir", hint="Neuer Ordner, damit nichts überschrieben wird")

        buttons = ttk.Frame(self, padding=(12, 0, 12, 8))
        buttons.pack(fill="x")
        self.start_btn = ttk.Button(buttons, text="Starten", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(buttons, text="Stoppen", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        self.status = ttk.Label(buttons, text="Bereit")
        self.status.pack(side="left", padx=8)

        progress = ttk.LabelFrame(self, text="Status", padding=8)
        progress.pack(fill="x", padx=12, pady=(0, 8))
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(progress, maximum=100, variable=self.progress_var)
        self.progress_bar.pack(fill="x")
        self.detail = ttk.Label(progress, text="Noch kein Lauf gestartet")
        self.detail.pack(anchor="w", pady=(4, 0))
        self.total_videos = 0
        self.done_videos = 0

        self.log = scrolledtext.ScrolledText(self, height=18, font=("Consolas", 9), wrap="none")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.after(100, self._drain_log)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _row(self, parent, row, label, var, width=None, browse=None, hint=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3, padx=(0, 8))
        entry = ttk.Entry(parent, textvariable=var, width=width) if width else ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", pady=3)
        if browse:
            ttk.Button(parent, text="…", width=3,
                       command=lambda: self._browse(var, browse)).grid(row=row, column=2, padx=(6, 0))
        if hint:
            ttk.Label(parent, text=hint, foreground="gray").grid(row=row, column=3, sticky="w", padx=(8, 0))

    def _browse(self, var, kind):
        if kind == "dir":
            path = filedialog.askdirectory(initialdir=var.get() or HERE)
        else:
            path = filedialog.askopenfilename(initialdir=var.get() or HERE)
        if path:
            var.set(os.path.normpath(path))

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        try:
            values = {k: v.get() for k, v in self.vars.items()}
            if not values["length"].strip().isdigit():
                raise ValueError("Frames muss eine ganze Zahl sein.")
            cmd = build_command(values)
        except ValueError as exc:
            messagebox.showerror("Eingabe fehlt", str(exc))
            return

        os.makedirs(values["output_path"].strip(), exist_ok=True)
        self.log.delete("1.0", "end")
        self.log.insert("end", "Befehl:\n" + subprocess.list2cmdline(cmd) + "\n\n")
        self.total_videos = sum(
            1 for f in os.listdir(values["image_path"].strip())
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")))
        self.done_videos = 0
        self.progress_var.set(0)
        self.detail.config(text=f"Video 0 von {self.total_videos} – starte…")
        self.status.config(text="Läuft…")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        self.proc = subprocess.Popen(
            cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()

    def _reader(self, proc):
        for line in proc.stdout:
            self.log_queue.put(line)
        proc.wait()
        self.log_queue.put(f"\n[Ende, Exit-Code {proc.returncode}]\n")
        self.log_queue.put(None)

    def _drain_log(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item is None:
                    self.start_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")
                    self.status.config(text="Fertig")
                    break
                # tqdm schreibt Fortschritt mit \r; als eigene Zeilen anzeigen
                self.log.insert("end", item.replace("\r", "\n"))
                self.log.see("end")
                self._update_progress(item)
        except queue.Empty:
            pass
        self.after(100, self._drain_log)

    def _update_progress(self, line):
        """Liest Schritt (tqdm) und fertige Videos ('Saved video') aus der Ausgabe."""
        if line.startswith("Saved video"):
            self.done_videos += 1
            self.detail.config(text=f"Video {self.done_videos} von {self.total_videos} fertig")
            return
        matches = TQDM_RE.findall(line)
        if not matches:
            return
        step, total = (int(x) for x in matches[-1])
        if total <= 0:
            return
        current = self.done_videos + 1
        overall = ((self.done_videos * total + step) / (max(self.total_videos, 1) * total)) * 100
        self.progress_var.set(min(overall, 100))
        self.detail.config(
            text=f"Video {current} von {self.total_videos} – Schritt {step} von {total}")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.status.config(text="Gestoppt")

    def _on_close(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Lauf aktiv", "Der Lauf läuft noch. Wirklich beenden?"):
                return
            self.proc.terminate()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
