import io
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

import folium
from streamlit_folium import st_folium

# ---------------------------------------------------------
# KONFIGURÁCIÓ
# ---------------------------------------------------------
BASE_INDEX_URL = "https://odp.met.hu/weather/weather_reports/synoptic/hungary/daily/csv/"

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

    # ---- StationNumber és StationName B és C oszlop ----
    if len(df.columns) < 3:
        raise ValueError("A CSV-ben nincs elég oszlop (minimum 3 szükséges a B és C oszlophoz).")
    df["station_number"] = df.iloc[:, 1].astype(str).str.strip()  # B oszlop
    df["station_name"] = df.iloc[:, 2].astype(str).str.strip()    # C oszlop

    # Kombinált név: StationName (StationNumber)
    df["station_full"] = df["station_name"] + " (" + df["station_number"] + ")"

    # ---- Min & Max oszlopok (K és M) ----
    if len(df.columns) <= 12:
        raise ValueError("A CSV-ben nincs elég oszlop a K és M oszlopokhoz.")
    min_col = df.columns[10]  # K oszlop
    max_col = df.columns[12]  # M oszlop

    # ---- Koordináták (ha vannak) ----
    lat_candidates = [c for c in df.columns if c.lower() in ("lat", "latitude")]
    lon_candidates = [c for c in df.columns if c.lower() in ("lon", "longitude", "long")]
    if lat_candidates and lon_candidates:
        df["lat"] = pd.to_numeric(df[lat_candidates[0]].str.replace(",", ".", regex=False), errors="coerce")
        df["lon"] = pd.to_numeric(df[lon_candidates[0]].str.replace(",", ".", regex=False), errors="coerce")
    else:
        df["lat"] = None
        df["lon"] = None

    # ---- Minimum és maximum konvertálása ----
    def to_float(s):
        s2 = s.astype(str).str.strip().replace("", pd.NA)
        s2 = s2.replace({"-999": pd.NA})
        s2 = s2.str.replace(",", ".", regex=False)
        return pd.to_numeric(s2, errors="coerce")

    df["min_val"] = to_float(df[min_col])
    df["max_val"] = to_float(df[max_col])

    # ---- Szélsők meghatározása ----
    min_res = None
    max_res = None

    if df["min_val"].dropna().size > 0:
        idx = df["min_val"].idxmin()
        min_res = {
            "value": float(df.loc[idx, "min_val"]),
            "station": df.loc[idx, "station_full"],
            "lat": df.loc[idx, "lat"],
            "lon": df.loc[idx, "lon"]
        }

    if df["max_val"].dropna().size > 0:
        idx = df["max_val"].idxmax()
        max_res = {
            "value": float(df.loc[idx, "max_val"]),
            "station": df.loc[idx, "station_full"],
            "lat": df.loc[idx, "lat"],
            "lon": df.loc[idx, "lon"]
        }

    df_map = df[["station_full", "lat", "lon", "min_val", "max_val"]].rename(columns={"station_full":"station"})

    return min_res, max_res, df_map

# ---------------------------------------------------------
# STREAMLIT UI
# ---------------------------------------------------------
st.set_page_config(page_title="Magyarországi napi hőmérsékleti szélsők", layout="centered")

st.title("🌡️ Magyarországi napi hőmérsékleti szélsőértékek")
st.caption("Hungaromet – Meteorológiai Adattár napi szinoptikus jelentések alapján")

# session_state inicializálása
for key in ["data_loaded","zip_bytes","csv_text","min_res","max_res","df_map","date_selected"]:
    if key not in st.session_state:
        st.session_state[key] = None
if st.session_state["data_loaded"] is None:
    st.session_state["data_loaded"] = False

# dátumválasztó
today_local = datetime.now(ZoneInfo("Europe/Budapest")).date()
default_date = today_local - timedelta(days=1)
date_selected = st.date_input("📅 Válaszd ki a dátumot:", value=default_date)
st.session_state["date_selected"] = date_selected

# gombnyomás
if st.button("Hőmérsékleti adatok lekérése"):
    try:
        fname = build_filename_for_date(date_selected)
        file_url = BASE_INDEX_URL + fname
        st.session_state["zip_bytes"] = download_zip_bytes(file_url)
        st.session_state["csv_text"] = extract_csv_from_zipbytes(st.session_state["zip_bytes"], expected_csv_name=fname.replace(".zip",""))
        st.session_state["min_res"], st.session_state["max_res"], st.session_state["df_map"] = parse_and_find_extremes(st.session_state["csv_text"])
        st.session_state["data_loaded"] = True
    except Exception as e:
        st.error(f"Hiba történt: {e}")

# --- Ha betöltődtek az adatok ---
if st.session_state["data_loaded"]:
    fname = build_filename_for_date(st.session_state["date_selected"])
    # ZIP letöltése
    st.download_button(
        "⬇️ Eredeti ZIP fájl letöltése",
        data=st.session_state["zip_bytes"],
        file_name=fname,
        mime="application/zip"
    )

    # Szélsőértékek
    date_str = st.session_state["date_selected"].strftime("%Y.%m.%d")
    st.subheader(f"Hőmérsékleti szélsőértékek {date_str}-re")
    col1, col2 = st.columns(2)
    with col1:
        if st.session_state["max_res"]:
            st.success(f"🔥 **Maximum:** {st.session_state['max_res']['value']} °C\n\n📍 {st.session_state['max_res']['station']}")
        else:
            st.warning("Nincs maximum adat.")
    with col2:
        if st.session_state["min_res"]:
            st.success(f"❄️ **Minimum:** {st.session_state['min_res']['value']} °C\n\n📍 {st.session_state['min_res']['station']}")
        else:
            st.warning("Nincs minimum adat.")

    # Térkép
    st.subheader("🗺️ Térképi megjelenítés – Állomáshálózat és szélsők")
    m = folium.Map(location=[47.1, 19.5], zoom_start=7)

    # 1) Minden állomás fekete pötty
    for _, row in st.session_state["df_map"].dropna(subset=["lat", "lon"]).iterrows():
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=4,
            color="black",
            fill=True,
            fill_color="black",
            fill_opacity=0.9,
            tooltip=row["station"]
        ).add_to(m)

    # 2) Minimum – kék
    min_res = st.session_state["min_res"]
    if min_res and min_res["lat"] and min_res["lon"]:
        folium.CircleMarker(
            location=[min_res["lat"], min_res["lon"]],
            radius=8,
            color="blue",
            fill=True,
            fill_color="blue",
            fill_opacity=1,
            tooltip=f"❄️ Minimum: {min_res['station']} – {min_res['value']} °C",
            popup=f"<b>Minimum hőmérséklet</b><br>{min_res['station']}<br>{min_res['value']} °C"
        ).add_to(m)

    # 3) Maximum – piros
    max_res = st.session_state["max_res"]
    if max_res and max_res["lat"] and max_res["lon"]:
        folium.CircleMarker(
            location=[max_res["lat"], max_res["lon"]],
            radius=8,
            color="red",
            fill=True,
            fill_color="red",
            fill_opacity=1,
            tooltip=f"🔥 Maximum: {max_res['station']} – {max_res['value']} °C",
            popup=f"<b>Maximum hőmérséklet</b><br>{max_res['station']}<br>{max_res['value']} °C"
        ).add_to(m)

    st_folium(m, width=750, height=550)
