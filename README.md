# 📖 Generator Indeks Sublema

Aplikasi Streamlit untuk membangkitkan halaman **Indeks Sublema** dari PDF kamus
sumber (format seperti *Master ISI SUNDA*): mendeteksi tiap kata entri (headword)
beserta nomor halamannya, menyaring bentuk turunan (Sublema) lewat heuristik
imbuhan Sunda, mengurutkannya secara abjad, lalu merender jadi **PDF indeks
1 kolom** bergaya daftar isi (`kata .......... 7`) — tanpa header abjad
A/B/C — yang siap diunduh.

Semua tampilan output bisa dikustomisasi lewat sidebar:

- **Judul**: teks, font, ukuran, tebal/tidak (default: *"INDEKS SUBLEMA"*, Arial 14, bold)
- **Daftar sublema**: font, ukuran, tebal/tidak (default: Arial 10)
- **Penomoran halaman**: aktif/nonaktif, posisi (atas kiri/tengah/kanan,
  bawah kiri/tengah/kanan — default **bawah tengah**), format angka atau
  romawi (default **angka**), nomor mulai dari, ukuran, awalan/akhiran
- **Ukuran kertas & margin** (A4 / Letter / Folio)
- **Pengaturan lanjutan** untuk kalibrasi deteksi entri (kata kunci font,
  rentang ukuran huruf, daftar awalan/akhiran Sublema) — berguna kalau PDF
  kamus sumbermu memakai gaya huruf berbeda

## 🗂️ Struktur proyek

```
indeks-sublema-generator/
├── app.py                  # UI Streamlit
├── engine.py                # Logika inti: ekstraksi, heuristik, render PDF
├── requirements.txt
├── .streamlit/config.toml   # Tema warna aplikasi
├── .gitignore
└── README.md
```

`engine.py` sengaja dipisah dari `app.py` (tanpa dependensi Streamlit) supaya
logikanya mudah dites atau dipakai ulang di luar aplikasi web.

## 🚀 Menjalankan secara lokal

Butuh Python 3.9+.

```bash
git clone https://github.com/USERNAME/indeks-sublema-generator.git
cd indeks-sublema-generator
pip install -r requirements.txt
streamlit run app.py
```

Aplikasi akan terbuka otomatis di browser, biasanya di `http://localhost:8501`.

## ☁️ Deploy ke Streamlit Community Cloud

1. **Push ke GitHub.** Buat repository baru (bisa publik atau privat), lalu:
   ```bash
   git init
   git add .
   git commit -m "Generator Indeks Sublema"
   git branch -M main
   git remote add origin https://github.com/USERNAME/indeks-sublema-generator.git
   git push -u origin main
   ```
2. Buka **[share.streamlit.io](https://share.streamlit.io)**, login dengan akun GitHub-mu.
3. Klik **"New app"**, pilih repository, branch `main`, dan file utama `app.py`.
4. Klik **Deploy** — Streamlit Cloud otomatis membaca `requirements.txt` dan
   `.streamlit/config.toml`. Tunggu proses build (biasanya 1–3 menit).
5. Setelah selesai, aplikasi akan punya URL publik (`https://xxxxx.streamlit.app`)
   yang bisa dibagikan.

Setiap kali kamu `git push` perubahan baru ke branch `main`, Streamlit Cloud
akan otomatis re-deploy.

## 🧭 Cara pakai aplikasi

1. Unggah PDF kamus sumber.
2. Kalau ekstraksi menunjukkan **0 entri terdeteksi**, buka sidebar
   → **Pengaturan lanjutan → Kalibrasi font**, cek kombinasi (font, ukuran)
   yang benar-benar dipakai di PDF-mu, lalu sesuaikan
   *Kata kunci nama font headword* / *Ukuran huruf min-maks*.
3. Atur judul, font, ukuran, dan penomoran halaman sesuai selera di sidebar.
4. PDF hasil otomatis dirender ulang tiap pengaturan berubah — cek pratinjau,
   lalu klik **Unduh PDF Indeks Sublema**.

## ⚠️ Catatan tentang deteksi Lema vs Sublema

PDF sumber biasanya tidak punya penanda visual pasti untuk membedakan kata
dasar (Lema) dari bentuk turunan (Sublema). Aplikasi ini memakai heuristik:
sebuah entri dianggap **Sublema** jika mengandung tanda hubung (reduplikasi/
majemuk), berupa reduplikasi tanpa tanda hubung, atau berawalan/berakhiran
salah satu afiks Sunda umum (bisa diedit di sidebar). Setelah dijalankan ke
kamus lengkapmu, periksa hasilnya — kalau ada kata dasar yang ikut kejaring
atau bentuk turunan yang terlewat, tinggal sesuaikan daftar awalan/akhiran
di **Pengaturan lanjutan**.

## 🖋️ Tentang pilihan font

Font di aplikasi ini memakai font bawaan PDF (base-14: Helvetica, Times,
Courier) yang selalu tersedia di semua pembaca PDF tanpa perlu file font
tambahan. **"Arial (Helvetica)"** dipetakan ke Helvetica karena keduanya
setara secara metrik (lebar huruf sama), jadi hasilnya akan terlihat identik
dengan Arial di hampir semua kasus.
