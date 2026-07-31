#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ketabBor.py

هر صفحه‌ی یک PDF را که تصویر «دو صفحه‌ی کتاب» در کنار هم است، از وسط
(یا از نسبت دلخواه) به دو نیمه تقسیم می‌کند و هر نیمه را در یک صفحه‌ی
مستقل قرار می‌دهد. ترتیب خروجی (راست اول یا چپ اول) بر اساس جهت کتاب
(راست‌به‌چپ/چپ‌به‌راست) تعیین می‌شود.

اولویت با استخراج مستقیم تصویر جاسازی‌شده در PDF است (بدون افت کیفیت).
اگر صفحه تصویر ساده نبود (وکتور/متن آزاد یا چند تصویر) با رزولوشن بالا
رندر و سپس کراپ می‌شود.

پیش‌نیازها:
    pip install pymupdf pillow

استفاده:
    python ketabBor.py INPUT.pdf -o OUTPUT.pdf --rtl
    python ketabBor.py INPUT.pdf -o OUTPUT.pdf --ltr
    python ketabBor.py INPUT_DIR/ -o OUTPUT_DIR/ --rtl --dpi 400

    --rtl : کتاب راست‌به‌چپ (فارسی/عربی) -> در هر صفحه‌ی اصلی، نیمه‌ی
            راست را قبل از نیمه‌ی چپ در خروجی قرار می‌دهد.
    --ltr : کتاب چپ‌به‌راست (پیش‌فرض) -> نیمه‌ی چپ قبل از نیمه‌ی راست.
    --split-ratio 0.5   نسبت برش (پیش‌فرض دقیقاً وسط = 0.5)
    --dpi 300           رزولوشن رندر برای صفحاتی که تصویر تک‌قطعه ندارند
    --keep-first        اگر صفحه‌ی اول جلد است و نباید دو نیم شود
"""

import argparse
import io
import os
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    print("خطا: PyMuPDF نصب نیست. دستور زیر را اجرا کنید:\n    pip install pymupdf pillow")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("خطا: Pillow نصب نیست. دستور زیر را اجرا کنید:\n    pip install pymupdf pillow")
    sys.exit(1)


def get_full_page_image(page):
    """
    اگر صفحه دقیقاً یک تصویر باشد که کل صفحه را می‌پوشاند، آن تصویر خام را
    (بدون رمزگشایی/رمزگذاری مجدد -> بدون افت کیفیت) برمی‌گرداند.
    در غیر این صورت None برمی‌گرداند تا به روش رندر برویم.
    """
    images = page.get_images(full=True)
    if len(images) != 1:
        return None

    xref = images[0][0]
    # مستطیل قرارگیری تصویر روی صفحه را پیدا می‌کنیم
    rects = page.get_image_rects(xref)
    if not rects:
        return None
    rect = rects[0]
    page_rect = page.rect

    # باید تصویر تقریباً کل صفحه را بپوشاند (حداقل ۹۰٪ مساحت)
    coverage = (rect.get_area()) / max(page_rect.get_area(), 1)
    if coverage < 0.9:
        return None

    base_image = page.parent.extract_image(xref)
    img_bytes = base_image["image"]
    pil_img = Image.open(io.BytesIO(img_bytes))
    pil_img.load()
    return pil_img


def render_page_image(page, dpi):
    """رندر پرکیفیت کل صفحه به تصویر، برای صفحاتی که تصویر تک‌قطعه ندارند."""
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    mode = "RGB" if pix.n < 4 else "RGBA"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    return img


def split_image(img, ratio):
    """تصویر را عمودی به دو نیمه (چپ، راست) بر اساس نسبت برش تقسیم می‌کند."""
    w, h = img.size
    cut = int(round(w * ratio))
    left_half = img.crop((0, 0, cut, h))
    right_half = img.crop((cut, 0, w, h))
    return left_half, right_half


def pil_to_pdf_page(pdf_doc, pil_img, dpi_hint=300):
    """یک تصویر PIL را به‌عنوان یک صفحه‌ی جدید (اندازه‌ی متناسب) به PDF اضافه می‌کند."""
    w_px, h_px = pil_img.size
    # نسبت px -> pt بر اساس ۷۲ نقطه در اینچ
    w_pt = w_px * 72.0 / dpi_hint
    h_pt = h_px * 72.0 / dpi_hint

    buf = io.BytesIO()
    save_kwargs = {}
    if pil_img.mode not in ("RGB", "L"):
        pil_img = pil_img.convert("RGB")
    # PNG برای حفظ کامل کیفیت (بدون افت فشرده‌سازی جدید مخرب)
    pil_img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    new_page = pdf_doc.new_page(width=w_pt, height=h_pt)
    new_page.insert_image(new_page.rect, stream=img_bytes)
    return new_page


def process_pdf(input_path, output_path, rtl=True, split_ratio=0.5, dpi=300,
                 keep_first=False, progress_callback=None):
    """
    progress_callback (اختیاری): تابعی با امضای
        progress_callback(current_page, total_pages, message)
    که پیش از/پس از پردازش هر صفحه فراخوانی می‌شود تا رابط کاربری
    (مثلاً GUI) بتواند شماره‌ی صفحه‌ی در حال پردازش را نشان دهد.
    """
    src = fitz.open(input_path)
    out = fitz.open()

    total = len(src)
    for i in range(total):
        page = src[i]

        if progress_callback:
            progress_callback(i + 1, total, f"در حال پردازش صفحه‌ی {i + 1} از {total}")

        if keep_first and i == 0:
            # صفحه‌ی اول (مثلاً جلد) بدون تغییر کپی می‌شود
            out.insert_pdf(src, from_page=i, to_page=i)
            print(f"[{i + 1}/{total}] صفحه‌ی جلد بدون تغییر کپی شد.")
            continue

        img = get_full_page_image(page)
        source_dpi = 300
        if img is None:
            img = render_page_image(page, dpi)
            source_dpi = dpi
            method = f"رندر با {dpi} DPI"
        else:
            method = "استخراج مستقیم تصویر (بدون افت کیفیت)"
            # DPI واقعی تصویر را از روی نسبت پیکسل به اندازه‌ی صفحه محاسبه می‌کنیم
            page_w_pt = page.rect.width
            if page_w_pt > 0:
                source_dpi = img.size[0] / (page_w_pt / 72.0)

        left_half, right_half = split_image(img, split_ratio)

        if rtl:
            first_half, second_half = right_half, left_half
        else:
            first_half, second_half = left_half, right_half

        pil_to_pdf_page(out, first_half, dpi_hint=source_dpi)
        pil_to_pdf_page(out, second_half, dpi_hint=source_dpi)

        print(f"[{i + 1}/{total}] {method} — دو صفحه ساخته شد.")
        if progress_callback:
            progress_callback(i + 1, total, f"صفحه‌ی {i + 1} از {total} انجام شد ({method})")

    out.save(output_path, garbage=4, deflate=True)
    out.close()
    src.close()
    print(f"\nانجام شد: {output_path}  ({total} -> {len(fitz.open(output_path))} صفحه)")


def main():
    parser = argparse.ArgumentParser(
        description="نصف کردن صفحات دو-صفحه‌ای یک PDF اسکن‌شده و قرار دادن هرکدام در صفحه‌ی جدا."
    )
    parser.add_argument("input", help="فایل PDF ورودی یا پوشه‌ی حاوی چند فایل PDF")
    parser.add_argument("-o", "--output", required=True,
                         help="فایل PDF خروجی (یا پوشه‌ی خروجی در صورت ورودی پوشه)")
    dir_group = parser.add_mutually_exclusive_group()
    dir_group.add_argument("--rtl", action="store_true",
                            help="کتاب راست‌به‌چپ (نیمه‌ی راست اول)")
    dir_group.add_argument("--ltr", action="store_true",
                            help="کتاب چپ‌به‌راست (نیمه‌ی چپ اول) - پیش‌فرض")
    parser.add_argument("--split-ratio", type=float, default=0.5,
                         help="نسبت محل برش از چپ صفحه (پیش‌فرض 0.5 = دقیقاً وسط)")
    parser.add_argument("--dpi", type=int, default=300,
                         help="رزولوشن رندر برای صفحاتی که تصویر تک‌قطعه ندارند (پیش‌فرض 300)")
    parser.add_argument("--keep-first", action="store_true",
                         help="صفحه‌ی اول (جلد) بدون تغییر کپی شود")

    args = parser.parse_args()
    rtl = True if not args.ltr else False  # پیش‌فرض rtl=True چون کاربر عمدتاً فارسی کار می‌کند

    if os.path.isdir(args.input):
        os.makedirs(args.output, exist_ok=True)
        pdf_files = [f for f in os.listdir(args.input) if f.lower().endswith(".pdf")]
        if not pdf_files:
            print("هیچ فایل PDF در پوشه‌ی ورودی پیدا نشد.")
            sys.exit(1)
        for fname in sorted(pdf_files):
            in_path = os.path.join(args.input, fname)
            out_path = os.path.join(args.output, fname)
            print(f"\n=== در حال پردازش: {fname} ===")
            process_pdf(in_path, out_path, rtl=rtl, split_ratio=args.split_ratio,
                        dpi=args.dpi, keep_first=args.keep_first)
    else:
        process_pdf(args.input, args.output, rtl=rtl, split_ratio=args.split_ratio,
                    dpi=args.dpi, keep_first=args.keep_first)


if __name__ == "__main__":
    main()
