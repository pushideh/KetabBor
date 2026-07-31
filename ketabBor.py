#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ketabBor.py

هر صفحه‌ی یک PDF را که تصویر «دو صفحه‌ی کتاب» در کنار هم است، از وسط
(یا از نسبت دلخواه) به دو نیمه تقسیم می‌کند و هر نیمه را در یک صفحه‌ی
مستقل قرار می‌دهد. ترتیب خروجی (راست اول یا چپ اول) بر اساس جهت کتاب
(راست‌به‌چپ/چپ‌به‌راست) تعیین می‌شود.

روش کار (نسخه‌ی جدید — حذف واقعی، نه فقط کراپ بصری):
برای هر نیمه، کل صفحه‌ی اصلی کپی می‌شود و سپس با ابزار Redaction واقعی
PyMuPDF (`apply_redactions`) محتوای نیمه‌ی دیگر (متن + وکتور + پیکسل‌های
تصویر در آن ناحیه) به‌طور واقعی از جریان محتوای PDF حذف می‌شود — نه فقط
با clip پنهان می‌شود. سپس MediaBox/CropBox صفحه به اندازه‌ی همان نیمه
کوچک می‌شود. نتیجه:
  - حجم فایل واقعاً کاهش می‌یابد (محتوای نیمه‌ی حذف‌شده دیگر در فایل نیست).
  - اگر PDF ورودی متن قابل‌انتخاب/هایلایت دارد، همان بخش از متن که در
    نیمه‌ی نگه‌داشته‌شده است باقی می‌ماند و قابل‌انتخاب است.
  - هیچ رستر/تصویرسازی مجددی برای متن و وکتور رخ نمی‌دهد.

محدودیت شناخته‌شده: نسخه‌های قدیمی‌تر PyMuPDF ممکن است حذف واقعی
اشکال وکتوری (خطوط/مسیرهای غیرمتنی) را به‌خوبی حذف متن انجام ندهند؛
کد این حالت را با پارامتر «graphics» در صورت پشتیبانی فعال می‌کند و در
غیر این صورت به‌صورت خاموش (بدون خطا) به همان حذف متن/تصویر بسنده می‌کند.

پیش‌نیاز:
    pip install pymupdf

استفاده:
    python ketabBor.py INPUT.pdf -o OUTPUT.pdf --rtl
    python ketabBor.py INPUT.pdf -o OUTPUT.pdf --ltr
    python ketabBor.py INPUT_DIR/ -o OUTPUT_DIR/ --rtl

    --rtl : کتاب راست‌به‌چپ (فارسی/عربی) -> نیمه‌ی راست قبل از چپ.
    --ltr : کتاب چپ‌به‌راست (پیش‌فرض) -> نیمه‌ی چپ قبل از راست.
    --split-ratio 0.5   نسبت برش (پیش‌فرض دقیقاً وسط = 0.5)
    --keep-first        صفحه‌ی اول (مثلاً جلد) بدون تغییر کپی شود
"""

import argparse
import os
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    print("خطا: PyMuPDF نصب نیست. دستور زیر را اجرا کنید:\n    pip install pymupdf")
    sys.exit(1)


def _apply_real_redaction(page, rect_to_delete):
    """محتوای داخل rect_to_delete را به‌طور واقعی از صفحه حذف می‌کند
    (متن، تصویر، و در صورت پشتیبانی PyMuPDF، وکتور/خطوط)."""
    page.add_redact_annot(rect_to_delete)
    kwargs = {}
    if hasattr(fitz, "PDF_REDACT_IMAGE_PIXELS"):
        kwargs["images"] = fitz.PDF_REDACT_IMAGE_PIXELS
    if hasattr(fitz, "PDF_REDACT_LINE_ART_REMOVE_IF_COVERED"):
        kwargs["graphics"] = fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED
    try:
        page.apply_redactions(**kwargs)
    except TypeError:
        # نسخه‌ی قدیمی‌تر PyMuPDF که این پارامترها را نمی‌شناسد
        page.apply_redactions()


def process_pdf(input_path, output_path, rtl=True, split_ratio=0.5,
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
            if progress_callback:
                progress_callback(i + 1, total, f"صفحه‌ی جلد ({i + 1}) بدون تغییر کپی شد")
            continue

        rect = page.rect
        cut_x = rect.x0 + rect.width * split_ratio

        left_rect = fitz.Rect(rect.x0, rect.y0, cut_x, rect.y1)
        right_rect = fitz.Rect(cut_x, rect.y0, rect.x1, rect.y1)

        targets = [right_rect, left_rect] if rtl else [left_rect, right_rect]

        for kept_rect in targets:
            other_rect = left_rect if kept_rect is right_rect else right_rect

            # کل صفحه را کپی می‌کنیم، سپس نیمه‌ی ناخواسته را واقعاً حذف می‌کنیم
            out.insert_pdf(src, from_page=i, to_page=i)
            new_page = out[-1]

            _apply_real_redaction(new_page, other_rect)

            # اندازه‌ی صفحه را به همان نیمه‌ی نگه‌داشته‌شده کوچک می‌کنیم
            new_page.set_cropbox(kept_rect)
            new_page.set_mediabox(kept_rect)

        print(f"[{i + 1}/{total}] دو صفحه ساخته شد؛ نیمه‌ی حذف‌شده واقعاً از فایل پاک شد.")
        if progress_callback:
            progress_callback(i + 1, total, f"صفحه‌ی {i + 1} از {total} انجام شد")

    out.save(output_path, garbage=4, deflate=True)
    out.close()
    src.close()
    print(f"\nانجام شد: {output_path}  ({total} -> {len(fitz.open(output_path))} صفحه)")


def main():
    parser = argparse.ArgumentParser(
        description="نصف کردن صفحات دو-صفحه‌ای یک PDF و قرار دادن هرکدام در صفحه‌ی جدا (بدون رستر، با حفظ متن قابل‌انتخاب)."
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
                        keep_first=args.keep_first)
    else:
        process_pdf(args.input, args.output, rtl=rtl, split_ratio=args.split_ratio,
                    keep_first=args.keep_first)


if __name__ == "__main__":
    main()
