"""Standalone NIIMBOT B1 desktop label printer. Run: python main.py."""
import json
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk
from printerb_core import b1_label_printer as b1


LABELS = ("姓名／生日／身分證", "病歷號條碼", "姓名貼（六格）", "手機條碼", "收集標籤", "尿液小單", "自訂文字", "生長數據")
LABEL_ACTIONS = tuple(zip(("列印姓名生日", "快篩條碼", "姓名貼", "手機條碼", "收集", "開驗尿單", "TEXT", "生長數據"), LABELS))
FIELDS = (
    ("name", "姓名"), ("number", "病歷號"), ("id", "身分證字號"),
    ("birthday", "生日（西元 YYYY/MM/DD）"), ("carrier", "手機條碼（例如 /ABC1234）"),
    ("age", "年齡（例如 2y6m）"), ("body_height", "身高 cm"),
    ("height_percentile", "身高百分位"), ("body_weight", "體重 kg"),
    ("weight_percentile", "體重百分位"), ("head_circumference", "頭圍 cm"),
    ("head_circumference_percentile", "頭圍百分位"), ("BMI", "BMI"),
    ("bmi_interpretation", "體位"),
)


def render_label(kind, data, text):
    """Render once so preview, export and printing use the same bitmap."""
    if kind == LABELS[0]:
        return b1.render_name_birthday_label(data["name"], data["birthday"], data["id"])
    if kind == LABELS[1]:
        return b1.render_name_mrn_barcode_label(data["name"], data["number"])
    if kind == LABELS[2]:
        return b1.render_name_sticker(data["name"])
    if kind == LABELS[3]:
        return b1.render_mobile_barcode_label(data["carrier"])
    if kind == LABELS[4]:
        return b1.render_collection_label(data["name"], data["number"], text)
    if kind == LABELS[5]:
        return b1.render_urine_order_label()
    if kind == LABELS[6]:
        return b1.render_text_label(text)
    if kind == LABELS[7]:
        return b1.render_growth_label(data)
    raise ValueError("請選擇標籤種類。")


class PrinterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PrinterB · NIIMBOT B1")
        self.geometry("1100x900")
        self.minsize(1000, 850)
        self.option_add("*Font", ("Microsoft JhengHei UI", 10))
        self.events = queue.Queue()
        self.busy = False
        self.kind = tk.StringVar(value=LABELS[0])
        self.port = tk.StringVar(value="自動偵測")
        self.paper = tk.StringVar(value="原廠紙")
        self.density = tk.IntVar(value=3)
        self.status = tk.StringVar(value="就緒 · 50 × 30 mm · USB")
        self.fields = {key: tk.StringVar() for key, _ in FIELDS}
        self._build()
        self.refresh_ports()
        self.after(100, self.poll)

    def _build(self):
        header = ttk.Frame(self, padding=16)
        header.pack(fill="x")
        ttk.Label(header, text="PrinterB", font=("Segoe UI", 22, "bold")).pack(side="left")
        ttk.Label(header, text="NIIMBOT B1  /  50 × 30 mm").pack(side="right")
        settings = ttk.LabelFrame(self, text="印表機設定", padding=10)
        settings.pack(fill="x", padx=16)
        self.ports = ttk.Combobox(settings, textvariable=self.port, width=20, state="readonly")
        self.ports.grid(row=0, column=0, padx=5)
        ttk.Button(settings, text="重新偵測", command=self.refresh_ports).grid(row=0, column=1, padx=5)
        ttk.Combobox(settings, textvariable=self.paper, values=("原廠紙", "副廠紙（+1 mm）"), state="readonly", width=19).grid(row=0, column=2, padx=5)
        ttk.Label(settings, text="濃度").grid(row=0, column=3, padx=5)
        ttk.Spinbox(settings, from_=1, to=5, textvariable=self.density, width=4).grid(row=0, column=4)
        ttk.Button(settings, text="讀取診斷", command=self.diagnose).grid(row=0, column=5, padx=10)
        actions = ttk.LabelFrame(self, text="直接列印一張（使用下方資料）", padding=8)
        actions.pack(fill="x", padx=16, pady=(10, 0))
        self.label_buttons = {}
        for index, (label, kind) in enumerate(LABEL_ACTIONS):
            button = ttk.Button(actions, text=label, command=lambda selected=kind: self.print_kind(selected))
            button.grid(row=index // 4, column=index % 4, sticky="ew", padx=4, pady=4)
            actions.columnconfigure(index % 4, weight=1)
            self.label_buttons[kind] = button
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 16))
        ttk.Label(left, text="標籤種類").pack(anchor="w")
        selector = ttk.Frame(left)
        selector.pack(fill="x", pady=(4, 10))
        for index, (label, kind) in enumerate(LABEL_ACTIONS):
            ttk.Radiobutton(selector, text=label, variable=self.kind, value=kind,
                            command=self.update_inputs).grid(row=index // 4, column=index % 4, sticky="w", padx=3, pady=3)
        patient = ttk.LabelFrame(left, text="病人資料", padding=6)
        patient.pack(fill="x")
        growth = ttk.LabelFrame(left, text="生長數據", padding=6)
        growth.pack(fill="x", pady=(6, 0))
        for index, (key, label) in enumerate(FIELDS):
            panel = patient if index < 5 else growth
            offset = index if index < 5 else index - 5
            row, column = offset // 2, (offset % 2) * 2
            ttk.Label(panel, text=label).grid(row=row, column=column, sticky="w", pady=5)
            ttk.Entry(panel, textvariable=self.fields[key], width=14).grid(row=row, column=column + 1, sticky="ew", padx=(8, 6), pady=5)
            panel.columnconfigure(column + 1, weight=1)
        self.text_label = ttk.Label(left, text="自訂文字／收集原因（可換行）")
        self.text_label.pack(anchor="w", pady=(12, 4))
        self.text = tk.Text(left, height=4, wrap="word", relief="solid", borderwidth=1)
        self.text.pack(fill="x")
        right = ttk.Frame(body, width=410)
        right.pack(side="right", fill="both")
        ttk.Label(right, text="標籤預覽", font=("Microsoft JhengHei UI", 12, "bold")).pack(anchor="w")
        self.preview = tk.Canvas(right, width=400, height=280, bg="#e8edf2", highlightthickness=0)
        self.preview.pack(pady=12)
        self.preview.create_text(200, 140, text="輸入資料後按「預覽」", fill="#526070")
        ttk.Label(right, text="沿用原專案 B1 字型、版面及列印協定。\n生長百分位與 BMI 由使用者填入。", justify="left").pack(anchor="w", pady=6)
        for label, command in (("預覽", self.show_preview), ("儲存 PNG", self.save_png), ("列印一張", self.print_label)):
            ttk.Button(right, text=label, command=command).pack(fill="x", pady=5)
        ttk.Label(right, text="診斷結果（不列印）").pack(anchor="w", pady=(12, 4))
        self.diagnostic_output = tk.Text(right, width=48, height=8, wrap="word", state="disabled")
        self.diagnostic_output.pack(fill="both", expand=True)
        ttk.Separator(self).pack(fill="x")
        ttk.Label(self, textvariable=self.status, padding=10).pack(fill="x")
        self.update_inputs()

    def update_inputs(self):
        self.text_label.configure(text="收集原因（必填，可換行）" if self.kind.get() == LABELS[4] else "自訂文字（可換行）")
        self.text.configure(state="normal")
        self.preview.delete("all")
        self.preview.create_text(200, 140, text="按「預覽」查看目前資料", fill="#526070")

    def refresh_ports(self):
        try:
            values = ["自動偵測"] + [port.device for port in b1.available_serial_ports()]
            self.ports.configure(values=values)
            if self.port.get() not in values:
                self.port.set(values[0])
        except Exception as exc:
            messagebox.showerror("連接埠", str(exc), parent=self)

    def show_preview(self):
        try:
            image = render_label(self.kind.get(), {key: var.get().strip() for key, var in self.fields.items()}, self.text.get("1.0", "end-1c"))
            display = image.convert("RGB")
            display.thumbnail((384, 260), Image.Resampling.NEAREST)
            self.preview_image = ImageTk.PhotoImage(display)
            self.preview.delete("all")
            self.preview.create_image(200, 140, image=self.preview_image)
            self.status.set("預覽已更新 · 384 × 240 pixels")
            return image
        except Exception as exc:
            messagebox.showerror("標籤內容", str(exc), parent=self)
            return None

    def save_png(self):
        image = self.show_preview()
        if image is None:
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".png", filetypes=[("PNG", "*.png")])
        if path:
            try:
                image.save(path)
                self.status.set("已儲存 PNG")
            except Exception as exc:
                messagebox.showerror("儲存失敗", str(exc), parent=self)

    def selected_port(self):
        return None if self.port.get() == "自動偵測" else self.port.get()

    def start_job(self, action, diagnostic=False):
        if self.busy:
            messagebox.showinfo("請稍候", "印表機作業進行中。", parent=self)
            return
        self.busy = True
        self.status.set("正在讀取診斷…" if diagnostic else "正在列印…")
        def worker():
            try:
                self.events.put((True, action(), diagnostic))
            except Exception as exc:
                self.events.put((False, str(exc), diagnostic))
        threading.Thread(target=worker, daemon=True).start()

    def print_kind(self, kind):
        """Print a label directly from its main-window action button."""
        if self.busy:
            return
        self.kind.set(kind)
        self.update_inputs()
        self.print_label()

    def print_label(self):
        if self.busy:
            return
        image = self.show_preview()
        if image is None:
            return
        try:
            density = self.density.get()
            if density not in range(1, 6):
                raise ValueError("濃度須為 1 至 5。")
        except (ValueError, tk.TclError):
            messagebox.showerror("濃度", "濃度須為 1 至 5。", parent=self)
            return
        port = self.selected_port()
        feed = 0 if self.paper.get() == "原廠紙" else 1
        self.start_job(lambda: b1.print_image(image, port=port, density=density, extra_feed_mm=feed))

    def diagnose(self):
        port = self.selected_port()
        phase = self.paper.get()
        self.start_job(lambda: b1.read_b1_diagnostic(phase=phase, port=port), diagnostic=True)

    def poll(self):
        try:
            while True:
                ok, result, diagnostic = self.events.get_nowait()
                self.busy = False
                self.status.set(("診斷完成" if diagnostic else f"列印完成 · {result}") if ok else "作業失敗")
                if not ok:
                    messagebox.showerror("印表機", result, parent=self)
                elif diagnostic:
                    output = self.diagnostic_output
                    output.configure(state="normal")
                    output.delete("1.0", "end")
                    output.insert("1.0", json.dumps(result, ensure_ascii=False, indent=2, default=str))
                    output.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self.poll)


if __name__ == "__main__":
    PrinterApp().mainloop()
