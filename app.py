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

    # Állomásszám és állomásnév
    station_name_col = next((c for c in df.columns if "stationname" in c.lower()), df.columns[2])
    station_num_col = next((c for c in df.columns if "stationnumber" in c.lower()), None)

    # Koordináták
    lat_col = next((c for c in df.columns if "lat" in c.lower()), None)
    lon_col = next((c for c in df.columns if "lon" in c.lower() or "lng" in c.lower()), None)

    # Min / Max
    min_col = next((c for c in df.columns if c.lower() in ("tn", "tn24", "minimum", "min")), df.columns[10])
    max_col = next((c for c in df.columns if c.lower() in ("tx", "tx24", "maximum", "max")), df.columns[12])

    # Konvertálás
    def tf(s):
        s2 = s.astype(str).str.strip().replace("", pd.NA)
        s2 = s2.replace({"-999": pd.NA})
        s2 = s2.str.replace(",", ".", regex=False)
        return pd.to_numeric(s2, errors="coerce")

    min_series = tf(df[min_col])
    max_series = tf(df[max_col])

    # Első találatok
    min_idx = min_series.idxmin() if not min_series.dropna().empty else None
    max_idx = max_series.idxmax() if not max_series.dropna().empty else None

    def fmt_station(idx):
        name = df.loc[idx, station_name_col]
        if station_num_col:
            num = df.loc[idx, station_num_col]
            return f"{num} - {name}"
        return name

    # Minimum adat
    if min_idx is not None:
        min_res = {
            "value": float(min_series.loc[min_idx]),
            "station": fmt_station(min_idx),
            "lat": float(df.loc[min_idx, lat_col]) if lat_col else None,
            "lon": float(df.loc[min_idx, lon_col]) if lon_col else None,
        }
    else:
        min_res = None

    # Maximum adat
    if max_idx is not None:
        max_res = {
            "value": float(max_series.loc[max_idx]),
            "station": fmt_station(max_idx),
            "lat": float(df.loc[max_idx, lat_col]) if lat_col else None,
            "lon": float(df.loc[max_idx, lon_col]) if lon_col else None,
        }
    else:
        max_res = None

    return min_res, max_res


# ---------------------------------------------------------
# UI – CÍM
# ---------------------------------------------------------
st.title("🌡️ Magyarországi hőmérsékleti szélsők • Hungaromet")

st.markdown("""
Ez az alkalmazás letölti a Hungaromet napi adatállományát és megjeleníti:

- 🔥 **Napi maximum hőmérsékletet**
- ❄️ **Napi minimum hőmérsékletet**
- 🗺️ **Mindkettőt térképen is**

A ZIP fájl természetesen le is tölthető.
""")

# ---------------------------------------------------------
# DÁTUMVÁLASZTÁS
# ---------------------------------------------------------
today = local_today()
default_date = today - timedelta(days=1)

st.subheader("📅 Dátum kiválasztása")
date_selected = st.date_input("Válaszd ki a napot:", value=default_date)

# ---------------------------------------------------------
# ADATOK LEKÉRÉSE
# ---------------------------------------------------------
if st.button("🔎 Adatok lekérése", type="primary"):
    try:
        filename = build_filename_for_date(date_selected)
        url = BASE_INDEX_URL + filename

        zip_bytes = download_zip_bytes(url)

        # Letöltés gomb
        st.download_button(
            label="📦 ZIP fájl letöltése",
            data=zip_bytes,
            file_name=filename,
            mime="application/zip"
        )

        csv_text = extract_csv_from_zipbytes(zip_bytes, expected_csv_name=filename.replace(".zip", ""))

        min_res, max_res = parse_and_find_extremes(csv_text)

        st.success("✅ Sikeres feldolgozás!")

        date_str = date_selected.strftime("%Y.%m.%d")
        st.subheader(f"🌤️ Szélsőértékek – {date_str}")

        col1, col2 = st.columns(2)

        # MAX
        with col1:
            st.markdown("### 🔥 Maximum")
            if max_res:
                st.metric(
                    label=max_res["station"],
                    value=f"{max_res['value']} °C"
                )
            else:
                st.warning("Nincs adat.")

        # MIN
        with col2:
            st.markdown("### ❄️ Minimum")
            if min_res:
                st.metric(
                    label=min_res["station"],
                    value=f"{min_res['value']} °C"
                )
            else:
                st.warning("Nincs adat.")

        # ---------------------------------------------------------
        # TÉRKÉPI MEGJELENÍTÉS
        # ---------------------------------------------------------
        st.subheader("🗺️ Térképi megjelenítés")

        map_data = []

        if max_res and max_res["lat"] and max_res["lon"]:
            map_data.append({
                "lat": max_res["lat"],
                "lon": max_res["lon"],
                "type": "MAX",
                "temp": max_res["value"],
                "station": max_res["station"]
            })

        if min_res and min_res["lat"] and min_res["lon"]:
            map_data.append({
                "lat": min_res["lat"],
                "lon": min_res["lon"],
                "type": "MIN",
                "temp": min_res["value"],
                "station": min_res["station"]
            })

        if map_data:
            df_map = pd.DataFrame(map_data)
            st.map(df_map, size=200)
        else:
            st.warning("A térképi megjelenítéshez nincs elérhető koordináta.")

    except Exception as e:
        st.error(f"⚠️ Hiba történt: {e}")
