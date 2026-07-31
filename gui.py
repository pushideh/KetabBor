#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui.py — رابط گرافیکی ساده برای ketabBor.py

پیش‌نیاز اصلی: pymupdf, pillow (همان‌های اسکریپت خط‌فرمان)
پیش‌نیاز اختیاری برای Drag & Drop واقعی: tkinterdnd2
    pip install tkinterdnd2
اگر tkinterdnd2 نصب نباشد، برنامه به‌صورت خودکار فقط با دکمه‌ی
«انتخاب فایل / پوشه» کار می‌کند (بدون افت قابلیت اصلی).

اجرا:
    python gui.py
"""

import os
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# تلاش برای فعال‌سازی Drag & Drop واقعی
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

# ماژول پردازش اصلی باید کنار همین فایل باشد
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ketabBor import process_pdf  # noqa: E402


# نویسه‌های نامرئی یونیکد برای اجبار جهت راست‌به‌چپ روی بخش‌های خنثی
# (مثل ":" یا اعداد لاتین) که تیک‌کیت به‌خودی‌خود جهتشان را درست تشخیص نمی‌دهد.
_RLE = "\u202B"  # Right-to-Left Embedding
_PDF_MARK = "\u202C"  # Pop Directional Formatting


def rtl(text):
    """متن را داخل یک embedding راست‌به‌چپ می‌گذارد تا علائم خنثی
    (دونقطه، اعداد، حروف لاتین) در جای درست (سمت راست کلمه‌ی فارسی) قرار بگیرند."""
    return f"{_RLE}{text}{_PDF_MARK}"


def setup_rtl_widget_styles(style):
    """چیدمان پیش‌فرض Radiobutton/Checkbutton در ttk نشانه (دایره/چک‌باکس)
    را قبل از متن (سمت چپ) می‌گذارد. این استایل آن را بعد از متن (سمت راست
    در چیدمان RTL) قرار می‌دهد.
    نکته‌ی مهم: نام واقعی عناصر داخلی ttk بدون پیشوند «T» است
    (مثلاً Radiobutton.indicator، نه TRadiobutton.indicator)."""
    element_prefix = {"TRadiobutton": "Radiobutton", "TCheckbutton": "Checkbutton"}
    for widget_type, elem in element_prefix.items():
        style.layout(f"RTL.{widget_type}", [
            (f"{elem}.padding", {
                "sticky": "nswe",
                "children": [
                    (f"{elem}.indicator", {"side": "right", "sticky": ""}),
                    (f"{elem}.focus", {
                        "side": "right",
                        "sticky": "",
                        "children": [
                            (f"{elem}.label", {"sticky": "nswe"})
                        ]
                    }),
                ]
            })
        ])


class PDFSplitterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("کتاب‌بُر")
        self.root.geometry("480x600")
        self.root.resizable(False, False)

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.direction = tk.StringVar(value="rtl")
        self.dpi = tk.StringVar(value="300")
        self.split_ratio = tk.StringVar(value="0.5")
        self.keep_first = tk.BooleanVar(value=False)

        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        title = ttk.Label(self.root, text="کتاب‌بُر",
                           font=("Segoe UI", 14, "bold"))
        title.pack(pady=(10, 2))

        subtitle_text = rtl("فایل یا پوشه‌ی PDF را اینجا رها کنید یا انتخاب کنید") if HAS_DND \
            else rtl("فایل یا پوشه‌ی PDF را انتخاب کنید")
        self.drop_area = tk.Label(
            self.root, text=subtitle_text, justify="right", anchor="center",
            relief="ridge", bd=2, height=2, bg="#f5f5f5", fg="#555",
            font=("Segoe UI", 10)
        )
        self.drop_area.pack(fill="x", padx=16, pady=4)

        if HAS_DND:
            self.drop_area.drop_target_register(DND_FILES)
            self.drop_area.dnd_bind("<<Drop>>", self._on_drop)

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", **pad)
        ttk.Button(btn_frame, text="انتخاب فایل",
                   command=self._choose_file).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="انتخاب پوشه",
                   command=self._choose_folder).pack(side="right", padx=4)

        in_frame = ttk.LabelFrame(self.root, text="مسیر ورودی")
        in_frame.pack(fill="x", padx=16, pady=3)
        ttk.Entry(in_frame, textvariable=self.input_path,
                  justify="right").pack(fill="x", padx=8, pady=4)

        out_frame = ttk.LabelFrame(self.root, text="مسیر خروجی")
        out_frame.pack(fill="x", padx=16, pady=3)
        out_row = ttk.Frame(out_frame)
        out_row.pack(fill="x", padx=8, pady=4)
        ttk.Entry(out_row, textvariable=self.output_path,
                  justify="right").pack(side="right", fill="x", expand=True, padx=(4, 0))
        ttk.Button(out_row, text="...", width=4,
                   command=self._choose_output).pack(side="left")

        opts_frame = ttk.LabelFrame(self.root, text="تنظیمات")
        opts_frame.pack(fill="x", padx=16, pady=3)

        dir_row = ttk.Frame(opts_frame)
        dir_row.pack(fill="x", padx=8, pady=3)
        ttk.Label(dir_row, text=rtl("جهت کتاب:")).pack(side="right", padx=4)
        ttk.Radiobutton(dir_row, text="راست‌به‌چپ (فارسی/عربی)", style="RTL.TRadiobutton",
                         variable=self.direction, value="rtl").pack(side="right", padx=4)
        ttk.Radiobutton(dir_row, text="چپ‌به‌راست", style="RTL.TRadiobutton",
                         variable=self.direction, value="ltr").pack(side="right", padx=4)

        num_row = ttk.Frame(opts_frame)
        num_row.pack(fill="x", padx=8, pady=3)
        ttk.Label(num_row, text=rtl("DPI رندر:")).pack(side="right", padx=4)
        ttk.Entry(num_row, textvariable=self.dpi, width=8, justify="right").pack(side="right", padx=4)
        ttk.Label(num_row, text=rtl("نسبت برش (0.5=وسط):")).pack(side="right", padx=(20, 4))
        ttk.Entry(num_row, textvariable=self.split_ratio, width=8, justify="right").pack(side="right", padx=4)

        check_row = ttk.Frame(opts_frame)
        check_row.pack(fill="x", padx=8, pady=3)
        ttk.Checkbutton(check_row, text="صفحه‌ی اول (جلد) بدون تغییر کپی شود", style="RTL.TCheckbutton",
                         variable=self.keep_first).pack(side="right", padx=4)

        self.run_btn = ttk.Button(self.root, text="شروع پردازش", command=self._start)
        self.run_btn.pack(pady=6, ipadx=20, ipady=4)

        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(self.root, textvariable=self.status_var,
                                       font=("Segoe UI", 9))
        self.status_label.pack(fill="x", padx=16)

        self.progress = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=16, pady=(2, 4))

        log_frame = ttk.LabelFrame(self.root, text="گزارش")
        log_frame.pack(fill="both", expand=True, padx=16, pady=(0, 3))
        self.log_text = tk.Text(log_frame, height=5, state="disabled",
                                 font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, padx=6, pady=4)

        self._build_footer()

    def _build_footer(self):
        footer = ttk.Frame(self.root)
        footer.pack(side="bottom", fill="x", padx=16, pady=(0, 6))

        # یک زیرقاب برای وسط‌چین کردن مجموعه‌ی متن+لینک
        inner = ttk.Frame(footer)
        inner.pack(anchor="center")

        # ترتیب Pack: اول متن «طراحی شده توسط:» (سمت راست/اول خوانده می‌شود)
        # سپس «پوشیده» (سمت چپ آن/بعد از دونقطه خوانده می‌شود)
        ttk.Label(inner, text=":طراحی شده توسط ",
                  font=("Segoe UI", 9)).pack(side="right")

        link_label = tk.Label(inner, text="پوشیده", fg="#0066cc",
                               cursor="hand2", font=("Segoe UI", 9, "underline"))
        link_label.pack(side="right")
        link_label.bind("<Button-1>", lambda e: self._open_link("https://x.com/pushideh"))

    @staticmethod
    def _open_link(url):
        import webbrowser
        webbrowser.open(url)

    # ------------------------------------------------------------ helpers
    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _on_drop(self, event):
        path = event.data.strip("{}")
        self.input_path.set(path)
        self._auto_fill_output(path)

    def _choose_file(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self.input_path.set(path)
            self._auto_fill_output(path)

    def _choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.input_path.set(path)
            self._auto_fill_output(path)

    def _choose_output(self):
        if os.path.isdir(self.input_path.get()):
            path = filedialog.askdirectory()
        else:
            path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                                 filetypes=[("PDF files", "*.pdf")])
        if path:
            self.output_path.set(path)

    def _auto_fill_output(self, in_path):
        if os.path.isdir(in_path):
            out = in_path.rstrip("/\\") + "_split"
        else:
            base, ext = os.path.splitext(in_path)
            out = base + "_split" + ext
        self.output_path.set(out)

    # -------------------------------------------------------------- run
    def _start(self):
        in_path = self.input_path.get().strip()
        out_path = self.output_path.get().strip()

        if not in_path or not os.path.exists(in_path):
            messagebox.showerror("خطا", "مسیر ورودی معتبر نیست.")
            return
        if not out_path:
            messagebox.showerror("خطا", "مسیر خروجی را مشخص کنید.")
            return
        try:
            dpi = int(self.dpi.get())
            ratio = float(self.split_ratio.get())
        except ValueError:
            messagebox.showerror("خطا", "مقدار DPI یا نسبت برش نامعتبر است.")
            return

        self.run_btn.configure(state="disabled")
        self.progress.configure(value=0)
        self.status_var.set(rtl("در حال آماده‌سازی..."))
        thread = threading.Thread(target=self._run_processing,
                                   args=(in_path, out_path, dpi, ratio), daemon=True)
        thread.start()

    def _update_progress(self, current, total, message, file_prefix=""):
        pct = (current / total * 100) if total else 0
        self.root.after(0, lambda: self.progress.configure(value=pct))
        self.root.after(0, lambda: self.status_var.set(rtl(f"{file_prefix}{message}")))

    def _run_processing(self, in_path, out_path, dpi, ratio):
        rtl = self.direction.get() == "rtl"
        try:
            if os.path.isdir(in_path):
                os.makedirs(out_path, exist_ok=True)
                pdf_files = sorted(f for f in os.listdir(in_path) if f.lower().endswith(".pdf"))
                if not pdf_files:
                    self.root.after(0, self._log, "هیچ فایل PDF در پوشه پیدا نشد.")
                for fidx, fname in enumerate(pdf_files, start=1):
                    self.root.after(0, self._log, f"در حال پردازش: {fname}")
                    prefix = f"[فایل {fidx}/{len(pdf_files)}: {fname}] "
                    process_pdf(
                        os.path.join(in_path, fname), os.path.join(out_path, fname),
                        rtl=rtl, split_ratio=ratio, dpi=dpi,
                        keep_first=self.keep_first.get(),
                        progress_callback=lambda cur, tot, msg, p=prefix:
                            self._update_progress(cur, tot, msg, p)
                    )
                    self.root.after(0, self._log, f"  تمام شد: {fname}")
            else:
                self.root.after(0, self._log, f"در حال پردازش: {os.path.basename(in_path)}")
                process_pdf(
                    in_path, out_path, rtl=rtl, split_ratio=ratio, dpi=dpi,
                    keep_first=self.keep_first.get(),
                    progress_callback=self._update_progress
                )
                self.root.after(0, self._log, "تمام شد.")

            self.root.after(0, self._log, f"\nخروجی نهایی: {out_path}")
            self.root.after(0, lambda: messagebox.showinfo("پایان یافت", "پردازش با موفقیت انجام شد."))
        except Exception as e:
            err = traceback.format_exc()
            self.root.after(0, self._log, f"خطا: {e}")
            self.root.after(0, lambda: messagebox.showerror("خطا در پردازش", str(e)))
            print(err)
        finally:
            self.root.after(0, lambda: self.run_btn.configure(state="normal"))


def main():
    if HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    style = ttk.Style(root)
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass
    setup_rtl_widget_styles(style)
    app = PDFSplitterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
