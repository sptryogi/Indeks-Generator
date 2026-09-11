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
import re
import pikepdf
import io

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

# Rentang Unicode aksara Sunda — dipakai untuk verifikasi "diikuti aksara Sunda"
SUNDANESE_UNICODE_RANGES = ((0x1B80, 0x1BBF), (0x1CC0, 0x1CCF))


def contains_sundanese_script(text: str) -> bool:
    return any(lo <= ord(ch) <= hi for ch in text for lo, hi in SUNDANESE_UNICODE_RANGES)
    
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
                    if len(spans) < 2 or not contains_sundanese_script(spans[1]["text"]):
                        continue
                word = clean_word(s0["text"])
                word_display = s0["text"].strip()  # versi asli, titik suku kata TETAP ada
                if word:
                    entries.append((word, label, word_display, s0["bbox"][0]))  # + indent (x kiri)
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
    nfkd = unicodedata.normalize("NFKD", word.lower().replace("-", "").replace(".", ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c))

def indented_x_values(x0_iterable, indent_max: float = 25.0):
    """Kembalikan himpunan nilai x0 yang tergolong 'menjorok' (Sublema),
    dibandingkan terhadap basis kolom (Lema) terdekat di sebelah kirinya.
    Lebih akurat daripada menebak dari awalan/akhiran kata."""
    uniq = sorted(set(round(x, 1) for x in x0_iterable))
    bases = []
    sublema_x = set()
    for x in uniq:
        near_base = next((b for b in bases if 0 < x - b <= indent_max), None)
        if near_base is not None:
            sublema_x.add(x)
        else:
            bases.append(x)
    return sublema_x
    
def build_index(entries, only_sublema: bool, prefixes, suffixes, min_root_length: int):
    sublema_x = indented_x_values(x for (_, _, _, x) in entries)

    grouped = {}
    display_map = {}
    for word, label, word_display, indent in entries:
        if only_sublema and round(indent, 1) not in sublema_x:
            continue
        grouped.setdefault(word, [])
        if label not in grouped[word]:
            grouped[word].append(label)
        display_map.setdefault(word, word_display)  # simpan versi ber-titik pertama kali ketemu

    def label_sort_key(lbl):
        try:
            return (0, int(lbl))
        except ValueError:
            return (1, lbl)

    items = []
    for word, labels in grouped.items():
        labels_sorted = sorted(labels, key=label_sort_key)
        items.append((display_map[word], labels_sorted))  # teks yang dirender = versi ber-titik
    items.sort(key=lambda item: sort_key(item[0]))
    return items

def build_letter_groups(index_items):
    """Kelompokkan item indeks (yang sudah terurut abjad) berdasarkan huruf
    pertama (tanpa diakritik/tanda hubung), untuk header A/B/C/... ."""
    groups = []
    current_letter = None
    for word, labels in index_items:
        key = sort_key(word)
        letter = key[0].upper() if key else "#"
        if letter != current_letter:
            groups.append((letter, []))
            current_letter = letter
        groups[-1][1].append((word, labels))
    return groups

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
        page.insert_text((x, y), text, fontname="helv", fontsize=font_size, color=(0, 0, 0, 1))


# =====================================================================================
# 4) RENDER PDF INDEKS — 1 KOLOM, TANPA HEADER ABJAD
# =====================================================================================

def render_index_pdf(
    index_items,
    page_size=(595, 842),
    margin=(42, 56, 42, 56),
    title_text="INDEKS SUBLEMA",
    title_font="Arial (Helvetica)",
    title_font_size=12,
    title_bold=True,
    entry_font="Arial (Helvetica)",
    entry_font_size=8,
    entry_bold=False,
    line_height_ratio=1.45,
    num_columns=3,
    column_gap=18,
    entry_separator=",  ",
    justify_entries=True,
    letter_header_enabled=True,
    letter_header_font="Arial (Helvetica)",
    letter_header_font_size=13,
    letter_header_bold=True,
    letter_header_gap_before=10,
    letter_header_gap_after=4,
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
    num_columns = max(1, int(num_columns))
    col_width = (W - ml - mr - column_gap * (num_columns - 1)) / num_columns

    entry_line_height = entry_font_size * line_height_ratio
    header_line_height = letter_header_font_size * line_height_ratio
    entry_fontname = FONT_BASE14[entry_font][entry_bold]
    title_fontname = FONT_BASE14[title_font][title_bold]
    header_fontname = FONT_BASE14[letter_header_font][letter_header_bold]

    doc = fitz.open()
    page = doc.new_page(width=W, height=H)

    if title_text:
        tw = fitz.get_text_length(title_text, fontname=title_fontname, fontsize=title_font_size)
        page.insert_text(((W - tw) / 2, mt + title_font_size), title_text,
                          fontname=title_fontname, fontsize=title_font_size, color=(0, 0, 0, 1))

    col = 0
    y = content_top
    x = ml

    def col_left():
        return ml + col * (col_width + column_gap)

    def col_right():
        return col_left() + col_width

    def new_column_or_page():
        nonlocal col, y, page, x
        col += 1
        if col >= num_columns:
            col = 0
            page = doc.new_page(width=W, height=H)
            y = mt
        else:
            y = content_top if page.number == 0 else mt
        x = col_left()

    def ensure_space(height):
        nonlocal y
        if y + height > content_bottom:
            new_column_or_page()

    groups = build_letter_groups(index_items)

    def draw_line(chunks, line_y, extra_gap=0.0):
        """Gambar satu baris dari nol di col_left(). chunks = list of
        (text, width, fontsize). extra_gap disisipkan di ANTARA tiap chunk
        untuk efek justify (rata kanan-kiri)."""
        cx = col_left()
        baseline = line_y + entry_font_size * 0.85
        for idx, (text, w, fsize) in enumerate(chunks):
            page.insert_text((cx, baseline), text, fontname=entry_fontname,
                              fontsize=fsize, color=(0, 0, 0, 1))
            cx += w
            if idx < len(chunks) - 1:
                cx += extra_gap

    for letter, items in groups:
        needed = (header_line_height + letter_header_gap_after if letter_header_enabled else 0) + entry_line_height
        ensure_space(needed)

        if letter_header_enabled:
            y += letter_header_gap_before
            page.insert_text((col_left(), y + letter_header_font_size * 0.85), letter,
                              fontname=header_fontname, fontsize=letter_header_font_size,
                              color=(0, 0, 0, 1))
            y += header_line_height + letter_header_gap_after

        # 1) siapkan tiap entri jadi "chunk" siap gambar. Kalau satu entri saja
        # sudah lebih lebar dari kolom, kecilkan ukuran hurufnya SUPAYA PAS —
        # ini menjamin tidak akan pernah tumpang tindih ke kolom sebelah.
        SAFETY_GAP = max(1.5, entry_font_size * 0.15)  # jarak jaga-jaga antar-entri (pt)

        prepared = []
        for i, (word, labels) in enumerate(items):
            page_str = ", ".join(labels)
            suffix = entry_separator if i < len(items) - 1 else ""
            text = f"{word} {page_str}{suffix}"
            tw = fitz.get_text_length(text, fontname=entry_fontname, fontsize=entry_font_size)
            fsize = entry_font_size
            if tw > col_width:
                fsize = entry_font_size * (col_width / tw) * 0.98
                tw = col_width * 0.98
            else:
                tw += SAFETY_GAP
            prepared.append((text, tw, fsize))

        # 2) susun jadi baris-baris; total lebar per baris DIJAMIN <= col_width
        lines = []
        current, current_w = [], 0.0
        for text, tw, fsize in prepared:
            if current and current_w + tw > col_width:
                lines.append(current)
                current, current_w = [], 0.0
            current.append((text, tw, fsize))
            current_w += tw
        if current:
            lines.append(current)

        # 3) gambar tiap baris. Baris terakhir grup huruf ini rata kiri biasa;
        # baris lain (kalau berisi >1 entri) di-justify kalau justify_entries aktif.
        for li, line_chunks in enumerate(lines):
            ensure_space(entry_line_height)
            is_last_line = (li == len(lines) - 1)
            natural_w = sum(w for _, w, _ in line_chunks)
            extra_gap = 0.0
            if justify_entries and len(line_chunks) > 1 and not is_last_line:
                extra_gap = max(0.0, (col_width - natural_w) / (len(line_chunks) - 1))
            draw_line(line_chunks, y, extra_gap=extra_gap)
            y += entry_line_height

        y += entry_line_height  # jarak sebelum grup huruf berikutnya

    stamp_page_numbers(doc, page_size, margin, page_number_enabled, page_number_position,
                        page_number_format, page_number_start, page_number_font_size,
                        page_number_prefix, page_number_suffix)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# =====================================================================================
# 5) KONVERSI PDF RGB -> CMYK — rumus GCR penuh langsung di operator warna
#    (rg/RG/g/G -> k/K), deterministik, TANPA Ghostscript/profil ICC, supaya
#    hasilnya konsisten di semua halaman dan warna primer tidak bocor silang.
# =====================================================================================

import io
import re

import pikepdf


def is_ghostscript_available() -> bool:
    # Dipertahankan agar halaman UI lama (yang mengecek fungsi ini sebelum
    # mengizinkan konversi) tetap berjalan tanpa perlu diubah. Ghostscript
    # sudah tidak dipakai lagi untuk convert_pdf_to_cmyk di bawah ini.
    return True


def _rgb_to_cmyk(r: float, g: float, b: float):
    # --- Snap RGB "hampir murni" cyan/magenta/yellow ke CMYK murni ---
    # Banyak PDF menyimpan cyan bukan sebagai RGB(0,255,255) persis, tapi
    # aproksimasi (mis. RGB(0,174,239)). Kalau langsung dihitung pakai rumus
    # GCR biasa, aproksimasi ini bocor jadi ada M/Y sisa + K (mis. jadi
    # C~100 M~27 K~6, bukan C100 M0 Y0 K0). Maka sebelum GCR, deteksi dulu
    # pola "satu kanal RGB rendah, dua kanal lain tinggi & berdekatan nilainya"
    # (atau sebaliknya untuk magenta/yellow) lalu paksa jadi primer CMYK murni.
    PURE_LOW = 0.05         # kanal dianggap "nol" kalau di bawah ini
    PURE_HIGH_MIN = 0.50    # dua kanal lain dianggap "tinggi/jenuh" kalau di atas ini
    PURE_HIGH_DIFF = 0.45   # selisih maksimal yang ditoleransi antar dua kanal tinggi tsb

    if (r <= PURE_LOW and g >= PURE_HIGH_MIN and b >= PURE_HIGH_MIN
            and abs(g - b) <= PURE_HIGH_DIFF):
        return 1.0, 0.0, 0.0, 0.0  # Cyan murni (C100 M0 Y0 K0)
    if (g <= PURE_LOW and r >= PURE_HIGH_MIN and b >= PURE_HIGH_MIN
            and abs(r - b) <= PURE_HIGH_DIFF):
        return 0.0, 1.0, 0.0, 0.0  # Magenta murni (C0 M100 Y0 K0)
    if (b <= PURE_LOW and r >= PURE_HIGH_MIN and g >= PURE_HIGH_MIN
            and abs(r - g) <= PURE_HIGH_DIFF):
        return 0.0, 0.0, 1.0, 0.0  # Yellow murni (C0 M0 Y100 K0)

    c, m, y = 1 - r, 1 - g, 1 - b
    k = min(c, m, y)
    if k >= 1.0:
        return 0.0, 0.0, 0.0, 1.0
    return (c - k) / (1 - k), (m - k) / (1 - k), (y - k) / (1 - k), k


_RGB_OP = re.compile(rb'([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(rg|RG)\b')
_GRAY_OP = re.compile(rb'([\d.]+)\s+(g|G)\b')


def _rgb_op_repl(m: "re.Match") -> bytes:
    r, g, b = (float(m.group(i)) for i in range(1, 4))
    c, mm, y, k = _rgb_to_cmyk(r, g, b)
    newop = b"k" if m.group(4) == b"rg" else b"K"
    return f"{c:.4f} {mm:.4f} {y:.4f} {k:.4f} ".encode() + newop


def _gray_op_repl(m: "re.Match") -> bytes:
    gray = float(m.group(1))
    newop = b"k" if m.group(2) == b"g" else b"K"
    return f"0.0000 0.0000 0.0000 {1 - gray:.4f} ".encode() + newop


def convert_pdf_to_cmyk(pdf_bytes: bytes, timeout: int = 900, progress_callback=None) -> bytes:
    """Konversi warna teks & vektor (operator rg/RG/g/G) dari RGB ke CMYK
    secara langsung & deterministik (rumus GCR penuh), tanpa Ghostscript
    atau profil ICC — supaya hasilnya konsisten di semua halaman dan warna
    primer (hitam, cyan, magenta, kuning) tidak bocor ke kanal lain.

    Catatan: ini mengonversi teks & elemen vektor. Gambar raster (foto/JPEG)
    yang masih pakai colorspace RGB TIDAK ikut dikonversi fungsi ini.

    timeout: dipertahankan untuk kompatibilitas pemanggil lama, tidak lagi
        dipakai (proses ini murni Python, jauh lebih cepat daripada GS).
    progress_callback: dipanggil dengan nomor halaman (int) setiap kali
        satu halaman selesai diproses, untuk mengisi progress bar di UI.
    """
    pdf = pikepdf.open(io.BytesIO(pdf_bytes))

    for i, page in enumerate(pdf.pages):
        contents = page.obj.get("/Contents")
        if contents is None:
            continue
        if isinstance(contents, pikepdf.Array):
            buf = b"\n".join(bytes(s.read_bytes()) for s in contents)
        else:
            buf = bytes(contents.read_bytes())

        buf = _RGB_OP.sub(_rgb_op_repl, buf)
        buf = _GRAY_OP.sub(_gray_op_repl, buf)

        page.obj.Contents = pdf.make_stream(buf)

        if progress_callback:
            progress_callback(i + 1)

    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()
