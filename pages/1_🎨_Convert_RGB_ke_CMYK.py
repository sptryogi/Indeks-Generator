"""
Halaman: Convert PDF RGB -> CMYK
=================================
Unggah PDF apa pun yang warnanya masih RGB, otomatis dikonversi ke CMYK
(memakai Ghostscript) sesuai warna asli yang ada di PDF tersebut.
"""

import time

import fitz  # PyMuPDF
import streamlit as st
import io

from engine import convert_pdf_to_cmyk, is_ghostscript_available

st.set_page_config(page_title="Convert RGB ke CMYK", page_icon="🎨", layout="wide")

st.title("🎨 Convert PDF RGB → CMYK")
st.caption(
    "Unggah PDF yang warnanya masih RGB, aplikasi akan otomatis mengonversi "
    "semua warna (teks, vektor, gambar) di dalamnya ke CMYK memakai Ghostscript."
)

if not is_ghostscript_available():
    st.error(
        "⚠️ Ghostscript belum terpasang di server ini, jadi konversi belum bisa jalan.\n\n"
        "- **Streamlit Community Cloud**: tambahkan file `packages.txt` berisi baris "
        "`ghostscript` di root repo, lalu deploy ulang.\n"
        "- **Lokal (Linux)**: `sudo apt install ghostscript`\n"
        "- **Lokal (Mac)**: `brew install ghostscript`\n"
        "- **Lokal (Windows)**: unduh installer dari ghostscript.com"
    )
    st.stop()

timeout_menit = st.sidebar.number_input(
    "Batas waktu konversi (menit)", min_value=1, max_value=60, value=15, step=1,
    help="Naikkan kalau PDF-mu banyak halaman / pakai font kompleks (mis. aksara "
         "Sunda) dan sempat gagal karena timeout.",
)

uploaded_file = st.file_uploader("Unggah PDF (RGB)", type=["pdf"], key="cmyk_uploader")

if not uploaded_file:
    st.info("⬆️ Unggah PDF di atas untuk mulai konversi.")
    st.stop()

pdf_bytes = uploaded_file.getvalue()
total_pages = fitz.open(stream=pdf_bytes, filetype="pdf").page_count

progress_bar = st.progress(0, text=f"Memulai konversi ({total_pages} halaman)...")
status_text = st.empty()
start_time = time.time()

def _update_progress(page_num: int):
    frac = min(page_num / total_pages, 1.0) if total_pages else 0
    elapsed = time.time() - start_time
    progress_bar.progress(frac, text=f"Halaman {page_num}/{total_pages} — {elapsed:.0f} detik berjalan")

try:
    cmyk_bytes = convert_pdf_to_cmyk(
        pdf_bytes, timeout=int(timeout_menit * 60), progress_callback=_update_progress
    )
except Exception as e:
    st.error(f"Gagal mengonversi: {e}")
    st.stop()

progress_bar.progress(1.0, text=f"Selesai dalam {time.time() - start_time:.0f} detik")

st.success(f"✅ Berhasil dikonversi ke CMYK ({len(cmyk_bytes) / 1024:.1f} KB).")

output_filename = st.text_input(
    "Nama file hasil", value=uploaded_file.name.rsplit(".", 1)[0] + "_CMYK.pdf",
    key="cmyk_filename",
)
st.download_button(
    "⬇️ Unduh PDF CMYK",
    data=cmyk_bytes,
    file_name=output_filename if output_filename else "output_CMYK.pdf",
    mime="application/pdf",
    type="primary",
)

with st.expander("👀 Pratinjau halaman pertama hasil konversi"):
    preview_doc = fitz.open(stream=cmyk_bytes, filetype="pdf")
    pix = preview_doc[0].get_pixmap(dpi=120)
    st.image(pix.tobytes("png"), use_container_width=True)
    preview_doc.close()
