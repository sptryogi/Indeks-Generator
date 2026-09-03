"""
Generator Indeks Sublema — Aplikasi Streamlit
==============================================
Unggah PDF kamus sumber (format seperti *Master ISI SUNDA*), aplikasi ini akan
mendeteksi tiap kata entri (headword) beserta nomor halamannya, menyaringnya
dengan heuristik Lema vs Sublema, lalu menyusun halaman "Indeks Sublema"
(1 kolom, tanpa header abjad, gaya daftar isi dengan titik-titik + nomor
halaman) dan siap diunduh sebagai PDF.

Judul, font & ukuran judul, font & ukuran daftar, serta posisi/format
penomoran halaman semuanya bisa diatur lewat sidebar.
"""

import fitz  # PyMuPDF
import streamlit as st

from engine import (
    FONT_CHOICES,
    PAGE_NUMBER_POSITIONS,
    PAGE_SIZES,
    build_index,
    extract_entries,
    get_font_size_combinations,
    render_index_pdf,
)

st.set_page_config(page_title="Generator Indeks Sublema", page_icon="📖", layout="wide")

st.title("📖 Generator Indeks Sublema")
st.caption(
    "Unggah PDF kamus sumber, aplikasi akan mendeteksi kata turunan (sublema) "
    "beserta nomor halamannya, lalu menyusunnya jadi halaman indeks siap unduh."
)

uploaded_file = st.file_uploader("Unggah PDF kamus sumber", type=["pdf"])

with st.sidebar:
    st.header("⚙️ Pengaturan Output")

    st.subheader("Judul")
    title_text = st.text_input("Teks judul", value="INDEKS SUBLEMA",
                                help="Kosongkan untuk tanpa judul.")
    c1, c2 = st.columns(2)
    with c1:
        title_font = st.selectbox("Font judul", FONT_CHOICES, index=0, key="title_font")
    with c2:
        title_font_size = st.number_input("Ukuran judul", min_value=6, max_value=48,
                                           value=12, step=1, key="title_size")
    title_bold = st.checkbox("Judul tebal (bold)", value=True, key="title_bold")

    st.divider()
    st.subheader("Daftar sublema")
    c3, c4 = st.columns(2)
    with c3:
        entry_font = st.selectbox("Font daftar", FONT_CHOICES, index=0, key="entry_font")
    with c4:
        entry_font_size = st.number_input("Ukuran daftar", min_value=6, max_value=24,
                                           value=8, step=1, key="entry_size")
    entry_bold = st.checkbox("Daftar tebal (bold)", value=False, key="entry_bold")
    num_columns = st.number_input("Jumlah kolom", min_value=1, max_value=4,
                                   value=3, step=1, key="num_columns",
                                   help="Jumlah kolom daftar sublema per halaman.")

    st.divider()
    st.subheader("Penomoran halaman")
    page_number_enabled = st.checkbox("Tampilkan nomor halaman", value=True, key="pn_enabled")
    position_label = st.selectbox(
        "Posisi", list(PAGE_NUMBER_POSITIONS.keys()),
        index=list(PAGE_NUMBER_POSITIONS.keys()).index("Bawah Tengah"), key="pn_pos",
        disabled=not page_number_enabled,
    )
    format_label = st.radio(
        "Format", ["Angka (1, 2, 3, ...)", "Romawi (i, ii, iii, ...)"],
        index=0, key="pn_format", disabled=not page_number_enabled,
    )
    c5, c6 = st.columns(2)
    with c5:
        page_number_start = st.number_input("Mulai dari", min_value=1, value=1, step=1,
                                             key="pn_start", disabled=not page_number_enabled)
    with c6:
        page_number_font_size = st.number_input("Ukuran nomor", min_value=6, max_value=20,
                                                  value=9, step=1, key="pn_size",
                                                  disabled=not page_number_enabled)
    c7, c8 = st.columns(2)
    with c7:
        page_number_prefix = st.text_input("Awalan (mis. 'hal. ')", value="",
                                            key="pn_prefix", disabled=not page_number_enabled)
    with c8:
        page_number_suffix = st.text_input("Akhiran", value="", key="pn_suffix",
                                            disabled=not page_number_enabled)

    st.divider()
    with st.expander("Ukuran halaman & margin"):
        page_size_label = st.selectbox("Ukuran kertas", list(PAGE_SIZES.keys()), index=0)
        cm1, cm2 = st.columns(2)
        with cm1:
            margin_left = st.number_input("Margin kiri (pt)", value=42, step=1)
            margin_top = st.number_input("Margin atas (pt)", value=56, step=1)
        with cm2:
            margin_right = st.number_input("Margin kanan (pt)", value=42, step=1)
            margin_bottom = st.number_input("Margin bawah (pt)", value=56, step=1)

    st.divider()
    with st.expander("⚗️ Pengaturan lanjutan — deteksi entri (kalibrasi)"):
        st.caption(
            "Kata entri dikenali lewat gaya huruf. Ubah nilai di bawah kalau ekstraksi "
            "gagal / kosong pada PDF kamusmu."
        )
        headword_font_keyword = st.text_input("Kata kunci nama font headword", value="Bold")
        c9, c10 = st.columns(2)
        with c9:
            headword_size_min = st.number_input("Ukuran huruf min.", value=9.0, step=0.5, format="%.1f")
        with c10:
            headword_size_max = st.number_input("Ukuran huruf maks.", value=11.5, step=0.5, format="%.1f")
        require_script_after = st.checkbox(
            "Wajib diikuti aksara Sunda (lebih akurat)", value=True
        )

        st.markdown("**Mode Lema vs Sublema**")
        only_sublema = st.checkbox(
            "Hanya tampilkan bentuk turunan (Sublema)", value=True,
            help="Matikan untuk memasukkan SEMUA entri (Lema + Sublema).",
        )
        sublema_prefixes = st.text_input(
            "Awalan Sublema (pisahkan koma)",
            value="di, nga, pi, sa, ka, mang, pang, ba, si, ti, per, barang",
        )
        sublema_suffixes = st.text_input(
            "Akhiran Sublema (pisahkan koma)", value="keun, eun, an, na",
        )
        min_root_length = st.number_input("Panjang minimum kata inti", min_value=1, value=2, step=1)

        st.markdown("**Kalibrasi font (opsional)**")
        st.caption(
            "Kalau hasil ekstraksi 0 entri, cek kombinasi (font, ukuran) yang benar-benar "
            "ada di PDF-mu di sini, lalu sesuaikan pengaturan di atas."
        )
        calib_page = st.number_input("Nomor halaman PDF untuk dicek (0 = pertama)",
                                      min_value=0, value=0, step=1)
        do_calibrate = st.button("🔍 Cek kombinasi font di halaman ini")

page_size = PAGE_SIZES[page_size_label]
margin = (margin_left, margin_top, margin_right, margin_bottom)
pn_position = PAGE_NUMBER_POSITIONS[position_label]
pn_format = "roman" if format_label.startswith("Romawi") else "arabic"
prefixes_list = [p.strip().lower() for p in sublema_prefixes.split(",") if p.strip()]
suffixes_list = [s.strip().lower() for s in sublema_suffixes.split(",") if s.strip()]

if not uploaded_file:
    st.info("⬆️ Unggah PDF kamus sumber di atas untuk mulai membuat indeks sublema.")
    st.stop()

pdf_bytes = uploaded_file.getvalue()

if do_calibrate:
    rows = get_font_size_combinations(pdf_bytes, page_index=int(calib_page))
    st.subheader(f"Kombinasi (font, ukuran) di halaman {calib_page}")
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.warning("Tidak ada teks terdeteksi di halaman ini.")

with st.spinner("Memproses PDF kamus..."):
    try:
        src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Gagal membuka PDF: {e}")
        st.stop()

    entries = extract_entries(
        src_doc, headword_font_keyword, headword_size_min, headword_size_max,
        require_script_after,
    )
    index_items = build_index(entries, only_sublema, prefixes_list, suffixes_list, min_root_length)
    src_doc.close()

col_res1, col_res2 = st.columns(2)
col_res1.metric("Total entri terdeteksi di sumber", len(entries))
col_res2.metric("Total entri masuk indeks", len(index_items))

if len(entries) == 0:
    st.warning(
        "⚠️ Tidak ada entri terdeteksi. Kemungkinan gaya huruf PDF-mu berbeda dari "
        "pengaturan default. Buka **Pengaturan lanjutan → Kalibrasi font** di sidebar "
        "untuk memeriksa kombinasi font & ukuran yang ada, lalu sesuaikan."
    )
    st.stop()

if len(index_items) == 0:
    st.warning(
        "⚠️ Entri terdeteksi, tapi tidak ada yang lolos filter Lema/Sublema. Coba matikan "
        "'Hanya tampilkan bentuk turunan (Sublema)' di Pengaturan lanjutan."
    )
    st.stop()

output_pdf_bytes = render_index_pdf(
    index_items,
    page_size=page_size,
    margin=margin,
    title_text=title_text,
    title_font=title_font,
    title_font_size=title_font_size,
    title_bold=title_bold,
    entry_font=entry_font,
    entry_font_size=entry_font_size,
    entry_bold=entry_bold,
    num_columns=num_columns,
    page_number_enabled=page_number_enabled,
    page_number_position=pn_position,
    page_number_format=pn_format,
    page_number_start=page_number_start,
    page_number_font_size=page_number_font_size,
    page_number_prefix=page_number_prefix,
    page_number_suffix=page_number_suffix,
)

st.success("✅ Indeks sublema berhasil dibuat.")

output_filename = st.text_input("Nama file hasil", value="Indeks_Sublema.pdf")
st.download_button(
    "⬇️ Unduh PDF Indeks Sublema",
    data=output_pdf_bytes,
    file_name=output_filename if output_filename else "Indeks_Sublema.pdf",
    mime="application/pdf",
    type="primary",
)

with st.expander("👀 Pratinjau 20 entri pertama"):
    for w, labels in index_items[:20]:
        st.text(f"{w:<28s} {', '.join(labels)}")

with st.expander("📄 Pratinjau halaman pertama PDF hasil"):
    preview_doc = fitz.open(stream=output_pdf_bytes, filetype="pdf")
    pix = preview_doc[0].get_pixmap(dpi=120)
    st.image(pix.tobytes("png"), use_container_width=True)
    preview_doc.close()
