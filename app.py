import io
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

# ---------------------------------------------------------
# ALAPBEÁLLÍTÁSOK
# ---------------------------------------------------------
BASE_INDEX_URL = "https://odp.met.hu/weather/weather_reports/synoptic/hungary/daily/csv/"

st.set_page_config(
    page_title="Magyarországi hőmérsékleti szélsők",
    layout="centered",
    page_icon="🌡️",
)

# ---------------------------------------------------------
# SEGÉDFÜGGVÉNYEK
# ---------------------------------------------------------
def local_today(tz_name="Europe/Budapest"):
    return datetime.now(ZoneInfo(tz_name)).date()

def build_filename_for_date(date_obj):
    y = date_obj.strftime("%Y%m%d")
    return f"HABP_1D_{y}.csv.zip"

def download_zip_bytes(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content

def extract_csv_from_zipbytes(zip_bytes, expected_csv_name=None):
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    if expected_csv_name and expected_csv_name in z.namelist():
        with z.open(expected_csv_name) as f:
            return f.read().decode("utf-8", errors="replace")

    for name in z.namelist():
        if name.lower().endswith(".csv"):
            with z.open(name) as f:
                return f.read().decode("utf-8", errors="replace")

    raise FileNotFoundError("A zip-ben nem található CSV fájl.")

def parse_and_find_extremes(csv_text):
    df = pd.read_csv(io.StringIO(csv_text), sep=";", engine="python", dtype=str, header=0)
    df.columns = [c.strip() for c in df.columns]

    # Állomásnév keresése
    station_candidates = [c for c in df.columns if 'station' in c.lower() or 'állomás' in c.lower()]
    station_col = station_candidates[0] if station_candidates else df.columns[2]

    # Min / Max oszlopok
    min_candidates = [c for c in df.columns if c.lower() in ('tn', 'tn24', 'min', 'minimum')]
    max_candidates = [c for c in df.columns if c.lower() in ('tx', 'tx24', 'max', 'maximum')]

    min_col = min_candidates[0] if min_candidates else df.columns[10]
    max_col = max_candidates[0] if max_candidates else df.columns[12]

    # Tisztítás → float
    def to_float_series(s):
        s2 = s.astype(str).str.strip().replace('', pd.NA)
        s2 = s2.replace({'-999': pd.NA})
        s2 = s2.str.replace(',', '.', regex=False)
        return pd.to_numeric(s2, errors='coerce')

    min_series = to_float_series(df[min_col])
    max_series = to_float_series(df[max_col])
    station_series = df[station_col].astype(str).str.strip()

    # Minimum
    if min_series.dropna().empty:
        min_res = None
    else:
        idx = min_series.idxmin()
        min_res = {"value": float(min_series.loc[idx]), "station": station_series.loc[idx]}

    # Maximum
    if max_series.dropna().empty:
        max_res = None
    else:
        idx = max_series.idxmax()
        max_res = {"value": float(max_series.loc[idx]), "station": station_series.loc[idx]}

    return min_res, max_res, {
        "station": station_col,
        "min": min_col,
        "max": max_col,
    }


# ---------------------------------------------------------
# UI – CÍM
# ---------------------------------------------------------
st.title("🌡️ Hőmérsékleti szélsőértékek • Hungaromet – Meteorológiai Adattár")

st.markdown("""
Ez az alkalmazás letölti a Hungaromet `HABP_1D_<YYYYMMDD>.csv.zip` napi adatfájlját,  
kinyeri a hőmérsékleti értékeket, és megmutatja **az adott nap országos minimum és maximum hőmérsékletét**.

A ZIP fájl természetesen **egy kattintással letölthető**.
""")

# ---------------------------------------------------------
# DÁTUMVÁLASZTÓ BLOKK
# ---------------------------------------------------------
today = local_today()
default_date = today - timedelta(days=1)

st.subheader("📅 Dátum kiválasztása")
date_selected = st.date_input("Válaszd ki a napot:", value=default_date)


# ---------------------------------------------------------
# GOMB – LEKÉRÉS
# ---------------------------------------------------------
if st.button("🔎 Adatok lekérése", type="primary"):
    try:
        filename = build_filename_for_date(date_selected)
        url = BASE_INDEX_URL + filename

        st.info("⏳ Fájl letöltése folyamatban...")

        # ZIP LETÖLTÉSE
        zip_bytes = download_zip_bytes(url)

        # LETÖLTHETŐ ZIP GOMB
        st.download_button(
            label="📦 ZIP fájl letöltése",
            data=zip_bytes,
            file_name=filename,
            mime="application/zip"
        )

        # CSV kinyerése
        csv_text = extract_csv_from_zipbytes(zip_bytes, expected_csv_name=filename.replace(".zip", ""))

        # Elemzés
        min_res, max_res, used_cols = parse_and_find_extremes(csv_text)

        st.success("✅ A fájl sikeresen beolvasva és feldolgozva.")

        st.markdown(f"**Használt oszlopok:** `{used_cols}`")

        date_str = date_selected.strftime("%Y.%m.%d")

        st.subheader(f"🌤️ Hőmérsékleti szélsők – {date_str}")

        col1, col2 = st.columns(2)

        # MAXIMUM
        with col1:
            st.markdown("### 🔥 Napi maximum")
            if max_res:
                st.metric(
                    label=f"Állomás: {max_res['station']}",
                    value=f"{max_res['value']} °C"
                )
            else:
                st.warning("Nincs elérhető maximum adat.")

        # MINIMUM
        with col2:
            st.markdown("### ❄️ Napi minimum")
            if min_res:
                st.metric(
                    label=f"Állomás: {min_res['station']}",
                    value=f"{min_res['value']} °C"
                )
            else:
                st.warning("Nincs elérhető minimum adat.")

    except Exception as e:
        st.error(f"⚠️ Hiba történt: {e}")
