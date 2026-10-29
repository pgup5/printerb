"""Standalone NIIMBOT B1 desktop label printer. Run: python main.py."""
import json
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageTk
from printerb_core import b1_label_printer as b1


LABELS = ("姓名／生日／身分證", "病歷號條碼", "姓名貼（五格）", "手機條碼", "收集標籤", "尿液小單", "自訂文字", "生長數據")
LABEL_OPTIONS = (("列印姓名生日", LABELS[0]), ("姓名貼", LABELS[2]),
                 ("手機條碼", LABELS[3]), ("TEXT", LABELS[6]))
FIELDS = (
    ("name", "姓名"), ("id", "身分證字號"),
    ("birthday", "生日（西元 YYYY/MM/DD）"), ("carrier", "手機條碼（例如 /ABC1234）"),
    ("age", "年齡（例如 2y6m）"), ("body_height", "身高 cm"),
    ("height_percentile", "身高百分位"), ("body_weight", "體重 kg"),
    ("weight_percentile", "體重百分位"), ("head_circumference", "頭圍 cm"),
    ("head_circumference_percentile", "頭圍百分位"), ("BMI", "BMI"),
    ("bmi_interpretation", "體位"),
)


def rotate_label(image, degrees):
    """Rotate clockwise and fit the whole result onto the fixed-size label."""
    rotated = image.rotate(-degrees, expand=True, fillcolor=1)
    rotated.thumbnail(image.size, Image.Resampling.NEAREST)
    result = Image.new(image.mode, image.size, 1)
    result.paste(rotated, ((image.width - rotated.width) // 2,
                           (image.height - rotated.height) // 2))
    return result


def scale_label(image, percent):
    """Scale content around the center while keeping the physical label size."""
    if percent == 100:
        return image.copy()
    width, height = image.size
    scaled = image.resize((max(1, round(width * percent / 100)),
                           max(1, round(height * percent / 100))), Image.Resampling.NEAREST)
    result = Image.new(image.mode, image.size, 1)
    result.paste(scaled, ((width - scaled.width) // 2, (height - scaled.height) // 2))
    return result


def render_label(kind, data, text, font_family="黑體"):
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
        return b1.render_text_label(text, font_family=font_family)
    if kind == LABELS[7]:
        return b1.render_growth_label(data)
    raise ValueError("請選擇標籤種類。")


class PrinterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PrinterB · NIIMBOT B1 · 50 × 30 mm · USB")
        width = min(1280, self.winfo_screenwidth() - 60)
        height = self.winfo_screenheight() - 60
        self.geometry(f"{width}x{height}")
        self.minsize(760, 560)
        families = set(tkfont.families(self))
        self.ui_font = next((name for name in ("Noto Sans CJK TC", "Microsoft JhengHei UI")
                             if name in families), "TkDefaultFont")
        # Negative Tk font sizes are pixels. Never shrink text to fit the window.
        self.body_font = tkfont.Font(self, family=self.ui_font, size=-28)
        self.small_font = tkfont.Font(self, family=self.ui_font, size=-24)
        self.section_font = tkfont.Font(self, family=self.ui_font, size=-32, weight="bold")
        self.title_font = tkfont.Font(self, family=self.ui_font, size=-52, weight="bold")
        self.option_add("*TCombobox*Listbox.font", self.body_font)
        self.events = queue.Queue()
        self.busy = False
        self.kind = tk.StringVar(value=LABELS[6])
        self.port = tk.StringVar(value="自動偵測")
        self.paper = tk.StringVar(value="原廠紙")
        self.density = tk.IntVar(value=3)
        self.content_scale = tk.DoubleVar(value=100)
        self.content_rotation = tk.StringVar(value="0°")
        self.text_font_family = tk.StringVar(value="黑體")
        self.scale_caption = tk.StringVar(value="列印內容大小：100%")
        self.rendered_label = None
        self.status = tk.StringVar(value="就緒 · 50 × 30 mm · USB")
        self.fields = {key: tk.StringVar() for key, _ in FIELDS}
        self._build()
        self.refresh_ports()
        self.after(100, self.poll)

    def _build(self):
        background, ink, muted, accent = "#f3f5f8", "#18283b", "#66758a", "#2463eb"
        self.configure(background=background)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=self.body_font)
        style.configure("TFrame", background=background)
        style.configure("TLabel", background=background, foreground=ink, font=self.body_font)
        style.configure("Card.TFrame", background="white")
        style.configure("Card.TLabel", background="white", foreground=ink)
        style.configure("Title.TLabel", font=self.title_font)
        style.configure("Muted.TLabel", foreground=muted)
        style.configure("Section.TLabel", background="white", font=self.section_font)
        style.configure("TButton", font=self.body_font, padding=(10, 7))
        style.configure("Accent.TButton", background=accent, foreground="white")
        style.map("Accent.TButton", background=[("active", "#194fbd")])
        style.configure("TRadiobutton", background="white", font=self.body_font, padding=4)
        self.radio_images = []
        for selected in (False, True):
            indicator = Image.new("RGBA", (128, 128), "white")
            draw = ImageDraw.Draw(indicator)
            draw.ellipse((8, 8, 120, 120), outline=accent if selected else muted, width=8)
            if selected:
                draw.ellipse((36, 36, 92, 92), fill=accent)
            self.radio_images.append(ImageTk.PhotoImage(
                indicator.resize((32, 32), Image.Resampling.LANCZOS)))
        style.element_create("LargeRadio.indicator", "image", self.radio_images[0],
                             ("selected", self.radio_images[1]), width=40, sticky="w")
        style.layout("Large.TRadiobutton", [
            ("Radiobutton.padding", {"sticky": "nswe", "children": [
                ("LargeRadio.indicator", {"side": "left", "sticky": ""}),
                ("Radiobutton.focus", {"side": "left", "sticky": "w", "children": [
                    ("Radiobutton.label", {"sticky": "nswe"})]})]})])
        style.configure("TEntry", padding=6, font=self.body_font)
        style.configure("TSpinbox", padding=5, font=self.body_font)
        style.configure("TCombobox", padding=5, font=self.body_font)

        # Scroll the workspace on small displays instead of clipping controls.
        workspace = ttk.Frame(self)
        workspace.pack(fill="both", expand=True, padx=16)
        viewport = tk.Canvas(workspace, background=background, highlightthickness=0)
        scrollbar = ttk.Scrollbar(workspace, orient="vertical", command=viewport.yview)
        def update_workspace_scrollbar(first, last):
            scrollbar.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                scrollbar.pack_forget()
            elif not scrollbar.winfo_manager():
                scrollbar.pack(side="right", fill="y", before=viewport)

        viewport.configure(yscrollcommand=update_workspace_scrollbar)
        viewport.pack(side="left", fill="both", expand=True)
        content = ttk.Frame(viewport)
        window = viewport.create_window(0, 0, window=content, anchor="nw")
        content.bind("<Configure>", lambda event: viewport.configure(scrollregion=viewport.bbox("all")))
        viewport.bind("<Configure>", lambda event: viewport.itemconfigure(window, width=event.width))

        settings_card = ttk.Frame(content, style="Card.TFrame", padding=14)
        settings_card.pack(fill="x", pady=(0, 12))
        settings = ttk.Frame(settings_card, style="Card.TFrame")
        settings.pack(fill="x")
        settings.columnconfigure(2, weight=1)
        settings.columnconfigure(5, weight=1)
        self.settings_font = tkfont.Font(self, family=self.ui_font, size=-20)
        style.configure("Settings.TLabel", background="white", foreground=ink, font=self.settings_font)
        style.configure("SettingsTitle.TLabel", background="white", foreground=ink,
                        font=(self.ui_font, -20, "bold"))
        style.configure("Settings.TButton", font=self.settings_font, padding=(5, 7))
        ttk.Label(settings, text="印表機設定", style="SettingsTitle.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(settings, text="連接埠", style="Settings.TLabel").grid(row=0, column=1, padx=(0, 8))
        self.ports = ttk.Combobox(settings, textvariable=self.port, width=8, state="readonly", font=self.settings_font)
        self.ports.grid(row=0, column=2, sticky="ew")
        ttk.Button(settings, style="Settings.TButton", text="重新偵測", command=self.refresh_ports).grid(row=0, column=3, padx=(6, 8))
        ttk.Label(settings, text="紙張", style="Settings.TLabel").grid(row=0, column=4, padx=(0, 8))
        ttk.Combobox(settings, textvariable=self.paper, values=("原廠紙", "副廠紙（+1 mm）"),
                     state="readonly", width=13, font=self.settings_font).grid(
                         row=0, column=5, sticky="ew")
        ttk.Label(settings, text="濃度", style="Settings.TLabel").grid(row=0, column=6, padx=(8, 6))
        ttk.Spinbox(settings, from_=1, to=5, textvariable=self.density, width=2,
                    font=self.settings_font).grid(row=0, column=7)
        ttk.Button(settings, style="Settings.TButton", text="讀取診斷", command=self.diagnose).grid(row=0, column=8, padx=(8, 0))

        body = ttk.Frame(content)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1, uniform="pane")
        body.columnconfigure(1, weight=1, uniform="pane")
        left = ttk.Frame(body, style="Card.TFrame", padding=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right = ttk.Frame(body, style="Card.TFrame", padding=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ttk.Label(left, text="標籤種類", style="Section.TLabel").pack(anchor="w")
        selector = ttk.Frame(left, style="Card.TFrame")
        selector.pack(fill="x", pady=(6, 14))
        selector.columnconfigure((0, 1), weight=1)
        for index, (label, kind) in enumerate(LABEL_OPTIONS):
            ttk.Radiobutton(selector, text=label, variable=self.kind, value=kind,
                            style="Large.TRadiobutton", command=self.update_inputs).grid(
                                row=index // 2, column=index % 2, sticky="w", padx=(0, 12), pady=6)
        self.text_label = ttk.Label(left, text="自訂文字（可換行）", style="Section.TLabel")
        self.text_label.pack(anchor="w", pady=(6, 6))
        text_frame = ttk.Frame(left, style="Card.TFrame")
        text_frame.pack(fill="both", expand=True)
        self.text = tk.Text(text_frame, height=3, width=20, wrap="word", relief="flat",
                            borderwidth=0, highlightthickness=1, highlightbackground="#dce2eb",
                            highlightcolor=accent, padx=8, pady=8, font=self.body_font)
        text_scroll = ttk.Scrollbar(text_frame, command=self.text.yview)
        self.text.configure(yscrollcommand=text_scroll.set)
        text_scroll.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        font_controls = ttk.Frame(left, style="Card.TFrame")
        font_controls.pack(fill="x", pady=(8, 12))
        ttk.Label(font_controls, text="字型", style="Card.TLabel").pack(side="left", padx=(0, 8))
        for family in ("黑體", "標楷體"):
            ttk.Radiobutton(font_controls, text=family, variable=self.text_font_family,
                            value=family, style="Large.TRadiobutton",
                            command=self.update_text_font).pack(side="left", padx=(0, 12))

        patient = ttk.Frame(left, style="Card.TFrame")
        patient.pack(fill="x")
        patient.columnconfigure(0, weight=1)

        labels = ("姓名", "身分證字號", "生日 YYYY/MM/DD", "手機條碼 /ABC1234")
        for index, ((key, _), label) in enumerate(zip(FIELDS[:4], labels)):
            row, column = index * 2, 0
            gap = (0, 0)
            ttk.Label(patient, text=label, style="Card.TLabel").grid(row=row, column=column, sticky="w", padx=gap)
            ttk.Entry(patient, textvariable=self.fields[key], width=14, font=self.body_font).grid(
                row=row + 1, column=column, sticky="ew", padx=gap, pady=(3, 10))

        ttk.Label(right, text="preview", style="Section.TLabel").pack(anchor="w")
        preview_frame = ttk.Frame(right, style="Card.TFrame")
        preview_frame.pack(fill="x", pady=(10, 12))
        self.preview = tk.Canvas(preview_frame, width=384, height=240, bg="#edf1f6", highlightthickness=0)
        self.preview.pack(fill="x")
        self.preview.bind("<Configure>", lambda event: self.layout_preview())
        ttk.Label(preview_frame, textvariable=self.scale_caption, style="Card.TLabel").pack(anchor="w", pady=(8, 0))
        ttk.Scale(preview_frame, from_=25, to=200, variable=self.content_scale,
                  command=self.update_content_scale).pack(fill="x", pady=(4, 0))
        rotation_controls = ttk.Frame(right, style="Card.TFrame")
        rotation_controls.pack(fill="x", pady=(0, 8))
        ttk.Label(rotation_controls, text="列印內容旋轉", style="Card.TLabel").pack(side="left")
        rotation_buttons = ttk.Frame(rotation_controls, style="Card.TFrame")
        rotation_buttons.pack(side="right")
        for column, (symbol, degrees) in enumerate((("↶", -90), ("↷", 90))):
            square = ttk.Frame(rotation_buttons, style="Card.TFrame", width=56, height=56)
            square.grid(row=0, column=column, padx=(8, 0))
            square.pack_propagate(False)
            ttk.Button(square, text=symbol, width=2,
                       command=lambda step=degrees: self.rotate_content(step)).pack(fill="both", expand=True)
        buttons = ttk.Frame(right, style="Card.TFrame")
        buttons.pack(fill="x")
        for index, (label, command) in enumerate((("預覽", self.show_preview), ("儲存 PNG", self.save_png), ("列印一張", self.print_label))):
            buttons.columnconfigure(0, weight=1)
            ttk.Button(buttons, text=label, command=command,
                       style="Accent.TButton" if index == 2 else "TButton").grid(
                           row=index, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(right, text="診斷結果", style="Section.TLabel").pack(anchor="w", pady=(16, 6))
        diagnostic = ttk.Frame(right, style="Card.TFrame")
        diagnostic.pack(fill="both", expand=True)
        self.diagnostic_output = tk.Text(diagnostic, width=20, height=3, wrap="word", state="disabled",
                                         relief="flat", background="#f5f7fa", foreground=muted,
                                         padx=8, pady=6, font=self.small_font)
        diagnostic_scroll = ttk.Scrollbar(diagnostic, command=self.diagnostic_output.yview)
        self.diagnostic_output.configure(yscrollcommand=diagnostic_scroll.set)
        diagnostic_scroll.pack(side="right", fill="y")
        self.diagnostic_output.pack(fill="both", expand=True)
        self.diagnostic_output.tag_configure("length", font=self.section_font, foreground=ink)
        ttk.Label(self, textvariable=self.status, style="Muted.TLabel", padding=(20, 8)).pack(fill="x")
        def arrange_panels(event):
            wide = event.width >= 1160
            right.grid_configure(row=0 if wide else 1, column=1 if wide else 0,
                                 padx=(6, 0) if wide else 0, pady=0 if wide else (12, 0))
            left.grid_configure(padx=(0, 6) if wide else 0)
            body.columnconfigure(1, weight=1 if wide else 0, uniform="pane" if wide else "")

        body.bind("<Configure>", arrange_panels)

        def scroll_workspace(event):
            if isinstance(event.widget, (tk.Text, ttk.Combobox, ttk.Spinbox)):
                return
            step = (-1 if event.num == 4 else 1) if event.num in (4, 5) else (-1 if event.delta > 0 else 1)
            viewport.yview_scroll(step * 3, "units")

        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind(sequence, scroll_workspace, add="+")
        self.update_inputs()

    def layout_preview(self):
        bounds = self.preview.bbox("content")
        if bounds is None:
            return
        width = max(self.preview.winfo_width(), bounds[2] - bounds[0])
        height = max(self.preview.winfo_height(), bounds[3] - bounds[1])
        self.preview.coords("content", width / 2, height / 2)
        self.preview.configure(scrollregion=(0, 0, width, height))

    def update_inputs(self):
        self.rendered_label = None
        self.text_label.configure(text="自訂文字（可換行）")
        self.text.configure(state="normal")
        self.preview.delete("all")
        self.preview.create_text(self.preview.winfo_width() / 2, self.preview.winfo_height() / 2,
                                 text="按「預覽」查看目前資料", fill="#66758a",
                                 font=self.body_font, tags="content")
        self.layout_preview()
        self.preview.xview_moveto(0)

    def refresh_ports(self):
        try:
            values = ["自動偵測"] + [port.device for port in b1.available_serial_ports()]
            self.ports.configure(values=values)
            if self.port.get() not in values:
                self.port.set(values[0])
        except Exception as exc:
            messagebox.showerror("連接埠", str(exc), parent=self)

    def update_text_font(self, event=None):
        if self.kind.get() == LABELS[6] and self.text.get("1.0", "end-1c").strip():
            self.show_preview()

    def update_content_scale(self, value):
        percent = round(float(value))
        self.scale_caption.set(f"列印內容大小：{percent}%")
        self.update_transformed_preview()

    def transformed_label(self):
        image = rotate_label(self.rendered_label, int(self.content_rotation.get().rstrip("°")))
        return scale_label(image, round(self.content_scale.get()))

    def rotate_content(self, degrees):
        angle = (int(self.content_rotation.get().rstrip("°")) + degrees) % 360
        self.content_rotation.set(f"{angle}°")
        self.update_transformed_preview()

    def update_transformed_preview(self):
        if self.rendered_label is not None:
            self.display_label(self.transformed_label())

    def display_label(self, image):
        self.preview_image = ImageTk.PhotoImage(image.convert("RGB"))
        self.preview.delete("all")
        self.preview.create_image(self.preview.winfo_width() / 2, self.preview.winfo_height() / 2,
                                  image=self.preview_image, tags="content")
        self.layout_preview()

    def show_preview(self):
        try:
            image = render_label(self.kind.get(), {key: var.get().strip() for key, var in self.fields.items()}, self.text.get("1.0", "end-1c"), self.text_font_family.get())
            self.rendered_label = image
            image = self.transformed_label()
            self.display_label(image)
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
                    rfid = result.get("rfid", {})
                    for key in ("total_length", "used_length"):
                        output.insert("end", f'"{key}": {rfid.get(key, "—")}\n', "length")
                    output.insert("end", json.dumps(result, ensure_ascii=False, indent=2, default=str))
                    output.yview_moveto(0)
                    output.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self.poll)


if __name__ == "__main__":
    PrinterApp().mainloop()
