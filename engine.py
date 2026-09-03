"""
engine.py
=========
Logika inti "Generator Indeks Sublema": ekstraksi entri dari PDF kamus sumber,
heuristik Lema/Sublema, pengurutan abjad, dan rendering PDF indeks (1 kolom,
tanpa header abjad). Modul ini murni Python + PyMuPDF, tidak bergantung pada
Streamlit, sehingga bisa dites/dipakai ulang secara terpisah dari UI.
"""

import unicodedata
from collections import Counter

import fitz  # PyMuPDF

# =====================================================================================
# PETA FONT (base-14 PDF, bawaan PyMuPDF — tidak perlu file font tambahan)
# "Arial" dipetakan ke Helvetica karena secara metrik setara & selalu tersedia
# di semua pembaca PDF tanpa perlu embed font.
# =====================================================================================
FONT_BASE14 = {
    "Arial (Helvetica)": {False: "helv", True: "hebo"},
    "Times New Roman": {False: "tiro", True: "tibo"},
    "Courier New": {False: "cour", True: "cobo"},
}
FONT_CHOICES = list(FONT_BASE14.keys())

PAGE_NUMBER_POSITIONS = {
    "Atas Kiri": "top-left",
    "Atas Tengah": "top-center",
    "Atas Kanan": "top-right",
    "Bawah Kiri": "bottom-left",
    "Bawah Tengah": "bottom-center",
    "Bawah Kanan": "bottom-right",
}

PAGE_SIZES = {
    "A4 (595 x 842 pt)": (595, 842),
    "Letter (612 x 792 pt)": (612, 792),
    "F4 / Folio (612 x 936 pt)": (612, 936),
}


# =====================================================================================
# 1) EKSTRAKSI ENTRI DARI PDF SUMBER
# =====================================================================================

def clean_word(raw: str) -> str:
    """Buang tanda titik pemisah suku kata, sisakan tanda hubung (untuk reduplikasi)."""
    return raw.strip().replace(".", "")


def get_page_label(page: "fitz.Page") -> str:
    """Ambil nomor halaman TERCETAK dari header berjalan (angka di dekat puncak
    halaman). Jika tidak ketemu, jatuh balik ke nomor halaman PDF (1-based)."""
    d = page.get_text("dict")
    best = None
    for block in d["blocks"]:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                t = span["text"].strip()
                if t.isdigit():
                    y0 = span["bbox"][1]
                    if best is None or y0 < best[0]:
                        best = (y0, t)
    return best[1] if best else str(page.number + 1)


def get_font_size_combinations(pdf_bytes: bytes, page_index: int = 0, limit: int = 40):
    """Bantu kalibrasi: kembalikan kombinasi (font, ukuran) paling sering muncul
    di satu halaman, supaya pengguna bisa menyesuaikan rentang ukuran headword."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if page_index >= len(doc):
        page_index = 0
    page = doc[page_index]
    counter = Counter()
    samples = {}
    for block in page.get_text("dict")["blocks"]:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                key = (span["font"], round(span["size"], 2))
                counter[key] += 1
                samples.setdefault(key, span["text"].strip()[:24])
    doc.close()
    rows = []
    for key, count in counter.most_common(limit):
        font, size = key
        rows.append({"font": font, "ukuran": size, "jumlah": count, "contoh": samples[key]})
    return rows


def extract_entries(doc: "fitz.Document", font_keyword: str, size_min: float,
                     size_max: float, require_script_after: bool):
    """Kembalikan list (kata_bersih, label_halaman) untuk tiap entri kamus terdeteksi."""
    entries = []
    for page in doc:
        label = get_page_label(page)
        d = page.get_text("dict")
        for block in d["blocks"]:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                spans = line["spans"]
                if not spans:
                    continue
                s0 = spans[0]
                if font_keyword and font_keyword not in s0["font"]:
                    continue
                if not (size_min <= s0["size"] <= size_max):
                    continue
                if require_script_after:
                    if len(spans) < 2 or "Type3" not in spans[1]["font"]:
                        continue
                word = clean_word(s0["text"])
                if word:
                    entries.append((word, label))
    return entries


# =====================================================================================
# 2) HEURISTIK LEMA / SUBLEMA, PENGURUTAN ABJAD
# =====================================================================================

def is_sublema(word_clean: str, prefixes, suffixes, min_root_length: int) -> bool:
    w = word_clean.lower()
    if "-" in w:
        return True  # reduplikasi / kata majemuk bertanda hubung
    core = w.replace("-", "")
    n = len(core)
    if n >= 6 and n % 2 == 0 and core[: n // 2] == core[n // 2:]:
        return True  # reduplikasi tanpa tanda hubung, mis. "abarabar"
    for suf in suffixes:
        if w.endswith(suf) and len(w) - len(suf) >= min_root_length:
            return True
    for pre in prefixes:
        if w.startswith(pre) and len(w) - len(pre) >= min_root_length:
            return True
    return False


def sort_key(word: str) -> str:
    """Kunci pengurutan abjad: huruf kecil, tanpa diakritik (é -> e), tanpa tanda hubung."""
    nfkd = unicodedata.normalize("NFKD", word.lower().replace("-", ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def build_index(entries, only_sublema: bool, prefixes, suffixes, min_root_length: int):
    grouped = {}
    for word, label in entries:
        if only_sublema and not is_sublema(word, prefixes, suffixes, min_root_length):
            continue
        grouped.setdefault(word, [])
        if label not in grouped[word]:
            grouped[word].append(label)

    def label_sort_key(lbl):
        try:
            return (0, int(lbl))
        except ValueError:
            return (1, lbl)

    items = []
    for word, labels in grouped.items():
        labels_sorted = sorted(labels, key=label_sort_key)
        items.append((word, labels_sorted))
    items.sort(key=lambda item: sort_key(item[0]))
    return items


# =====================================================================================
# 3) PENOMORAN HALAMAN (ROMAWI / ANGKA, 6 POSISI)
# =====================================================================================

ROMAN_TABLE = [
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
    (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
    (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
]


def to_roman(n: int) -> str:
    res = ""
    for value, sym in ROMAN_TABLE:
        while n >= value:
            res += sym
            n -= value
    return res if res else "0"


def format_page_number(n: int, fmt: str, prefix: str, suffix: str) -> str:
    core = to_roman(n) if fmt == "roman" else str(n)
    return f"{prefix}{core}{suffix}"


def stamp_page_numbers(doc: "fitz.Document", page_size, margin, enabled: bool,
                        position: str, fmt: str, start: int, font_size: float,
                        prefix: str, suffix: str):
    if not enabled:
        return
    W, H = page_size
    ml, mt, mr, mb = margin
    for i, page in enumerate(doc):
        text = format_page_number(start + i, fmt, prefix, suffix)
        tw = fitz.get_text_length(text, fontname="helv", fontsize=font_size)
        if position.startswith("top"):
            y = mt * 0.55
        else:
            y = H - mb * 0.4
        if position.endswith("left"):
            x = ml
        elif position.endswith("right"):
            x = W - mr - tw
        else:  # center
            x = (W - tw) / 2
        page.insert_text((x, y), text, fontname="helv", fontsize=font_size, color=(0, 0, 0))


# =====================================================================================
# 4) RENDER PDF INDEKS — 1 KOLOM, TANPA HEADER ABJAD
# =====================================================================================

def render_index_pdf(
    index_items,
    page_size=(595, 842),
    margin=(42, 56, 42, 56),
    title_text="INDEKS SUBLEMA",
    title_font="Arial (Helvetica)",
    title_font_size=14,
    title_bold=True,
    entry_font="Arial (Helvetica)",
    entry_font_size=10,
    entry_bold=False,
    line_height_ratio=1.45,
    page_number_enabled=True,
    page_number_position="bottom-center",
    page_number_format="arabic",
    page_number_start=1,
    page_number_font_size=9,
    page_number_prefix="",
    page_number_suffix="",
) -> bytes:
    W, H = page_size
    ml, mt, mr, mb = margin
    content_top = mt + (title_font_size * 2.2 if title_text else 0)
    content_bottom = H - mb
    col_width = W - ml - mr  # 1 kolom penuh, tanpa pembagian kolom

    entry_line_height = entry_font_size * line_height_ratio
    entry_fontname = FONT_BASE14[entry_font][entry_bold]
    title_fontname = FONT_BASE14[title_font][title_bold]

    doc = fitz.open()
    page = doc.new_page(width=W, height=H)

    if title_text:
        tw = fitz.get_text_length(title_text, fontname=title_fontname, fontsize=title_font_size)
        page.insert_text(((W - tw) / 2, mt + title_font_size), title_text,
                          fontname=title_fontname, fontsize=title_font_size, color=(0, 0, 0))

    y = content_top

    for word, labels in index_items:
        if y + entry_line_height > content_bottom:
            page = doc.new_page(width=W, height=H)
            y = mt

        page_str = ", ".join(labels)
        word_w = fitz.get_text_length(word, fontname=entry_fontname, fontsize=entry_font_size)
        num_w = fitz.get_text_length(page_str, fontname=entry_fontname, fontsize=entry_font_size)
        dot_w = fitz.get_text_length(".", fontname=entry_fontname, fontsize=entry_font_size)

        x0 = ml
        baseline = y + entry_font_size * 0.85
        page.insert_text((x0, baseline), word, fontname=entry_fontname,
                          fontsize=entry_font_size, color=(0, 0, 0))

        avail = col_width - word_w - num_w - 8
        n_dots = max(1, int(avail / dot_w)) if dot_w > 0 and avail > dot_w else 0
        if n_dots > 0:
            dots = "." * n_dots
            page.insert_text((x0 + word_w + 3, baseline), dots, fontname=entry_fontname,
                              fontsize=entry_font_size, color=(0.45, 0.45, 0.45))

        page.insert_text((x0 + col_width - num_w, baseline), page_str,
                          fontname=entry_fontname, fontsize=entry_font_size, color=(0, 0, 0))
        y += entry_line_height

    stamp_page_numbers(doc, page_size, margin, page_number_enabled, page_number_position,
                        page_number_format, page_number_start, page_number_font_size,
                        page_number_prefix, page_number_suffix)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes
