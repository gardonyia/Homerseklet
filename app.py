# app.py
import io
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

# --- Konfiguráció ---
BASE_INDEX_URL = "https://odp.met.hu/weather/weather_reports/synoptic/hungary/daily/csv/"
# A fájlnév formátuma: HABP_1D_<YYYYMMDD>.csv.zip

# Segédfüggvény: helyi dátum (Europe/Budapest)
def local_today(tz_name="Europe/Budapest"):
    return datetime.now(ZoneInfo(tz_name)).date()

def build_filename_for_date(date_obj):
    # date_obj: datetime.date
    y = date_obj.strftime("%Y%m%d")
    return f"HABP_1D_{y}.csv.zip"

def download_zip_bytes(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content

def extract_csv_from_zipbytes(zip_bytes, expected_csv_name=None):
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    # Ha megadtunk expected_csv_name-t, azt próbáljuk meg kinyitni, különben az első .csv fájl.
    if expected_csv_name and expected_csv_name in z.namelist():
        with z.open(expected_csv_name) as f:
            return f.read().decode("utf-8", errors="replace")
    # különben keressük az első .csv-t
    for name in z.namelist():
        if name.lower().endswith(".csv"):
            with z.open(name) as f:
                return f.read().decode("utf-8", errors="replace")
    raise FileNotFoundError("A zip-ben nem található CSV fájl.")

def parse_and_find_extremes(csv_text):
    """
    Megpróbálja rugalmasan beolvasni a csv-t (pontosvessző delimiter).
    Feltételezzük a felhasználói leírás alapján:
      - C oszlop = állomásnév (Excel A=0, B=1, C=2 -> index 2)
      - K oszlop = napi minimum (index 10)
      - M oszlop = napi maximum (index 12)
    Ha a CSV fejléc tartalmaz paraméterneveket (pl. 'StationName' vagy 'tn'/'tx'), akkor azokat is figyelembe vesszük.
    """
    # 1) beolvasás pandas-szal; ; szeparátor
    df = pd.read_csv(io.StringIO(csv_text), sep=";", engine="python", dtype=str, header=0)

    # Normalize columns: trim spaces
    df.columns = [c.strip() for c in df.columns]

    # Lehet, hogy a fájl metaadat sorokkal kezdődik (##Meta), ezért töröljük a metaszöveget, ha van.
    # Ha az első oszlop neve '#StationNumber' vagy hasonló, próbáljuk meg a releváns adatokat kinyerni:
    # Tisztább megoldás: csak a sorokat hagyjuk meg, ahol a dátum / számok vannak.
    # Átalakítjuk minden cellát string->float próbálva ahol szükséges.

    # Kísérlet: ha vannak oszlopnevek mint 'Station Name' vagy 'StationName' használjuk azokat.
    col_map = {}
    # Megkeressük a lehetséges állomásnév oszlopot
    station_candidates = [c for c in df.columns if 'station' in c.lower() or 'állomás' in c.lower() or 'StationName' in c]
    if station_candidates:
        col_map['station'] = station_candidates[0]
    else:
        # ha nincs, használjuk C oszlop pozícióként (index 2) ha létezik
        if len(df.columns) > 2:
            col_map['station'] = df.columns[2]
        else:
            raise ValueError("Nem található állomásnév oszlop a CSV-ben.")

    # K (min) és M (max) oszlopok: először keressük felirat alapján (tn, tx, min, max),
    # különben használjuk az Excel-pozíciót: K -> index 10, M -> index 12
    min_candidates = [c for c in df.columns if c.lower() in ('tn', 'tn24', 'min', 'minimum', 'k')]
    max_candidates = [c for c in df.columns if c.lower() in ('tx', 'tx24', 'max', 'maximum', 'm')]

    if min_candidates:
        col_map['min'] = min_candidates[0]
    elif len(df.columns) > 10:
        col_map['min'] = df.columns[10]
    else:
        raise ValueError("Nem található minimum oszlop (K).")

    if max_candidates:
        col_map['max'] = max_candidates[0]
    elif len(df.columns) > 12:
        col_map['max'] = df.columns[12]
    else:
        raise ValueError("Nem található maximum oszlop (M).")

    # Most konvertáljuk a min/max oszlopokat float-tá, figyelmen kívül hagyva a -999 értékeket
    def to_float_series(s):
        # eltávolítjuk a whitespace-et, üres -> NaN, '-999' -> NaN
        s2 = s.astype(str).str.strip().replace('', pd.NA)
        s2 = s2.replace({'-999': pd.NA})
        # csere ha vessző lenne (de a doc szerint '.'), de biztonság kedvéért:
        s2 = s2.str.replace(',', '.', regex=False)
        return pd.to_numeric(s2, errors='coerce')

    min_series = to_float_series(df[col_map['min']])
    max_series = to_float_series(df[col_map['max']])
    station_series = df[col_map['station']].astype(str).str.strip()

    # Legkisebb minimum (azaz a K oszlop legkisebb értéke) -> ez a napi legkisebb hőm.
    if min_series.dropna().empty:
        min_result = None
    else:
        min_idx = min_series.idxmin()
        min_result = {
            "value": float(min_series.loc[min_idx]),
            "station": station_series.loc[min_idx]
        }

    # Legnagyobb maximum (azaz a M oszlop legnagyobb értéke) -> ez a napi legnagyobb hőm.
    if max_series.dropna().empty:
        max_result = None
    else:
        max_idx = max_series.idxmax()
        max_result = {
            "value": float(max_series.loc[max_idx]),
            "station": station_series.loc[max_idx]
        }

    return min_result, max_result, col_map

# ---------- Streamlit UI ----------
st.set_page_config(page_title="Magyarországi napi hőmérsékleti szélsők", layout="centered")

st.title("Hőmérsékleti adatok | Hungaromet - Meteorológiai Adattár")

st.markdown("""
Ez az alkalmazás letölti a Meteorológiai Adattár `HABP_1D_<YYYYMMDD>.csv.zip` fájlját,
kiolvassa a K (minimum) és M (maximum) oszlopokat, majd megmutatja az országos szélsőértékeket.
""")

# Dátumválasztó: alapértelmezett: tegnap (mivel a napi adatok gyakran a következő napon érkeznek)
today_local = local_today()
default_date = today_local - timedelta(days=1)
date_selected = st.date_input("Válassz dátumot (YYYY-MM-DD):", value=default_date)

if st.button("Hőmérsékleti adatok lekérése"):
    st.info("Lekérés folyamatban...")
    try:
        fname = build_filename_for_date(date_selected)
        file_url = BASE_INDEX_URL + fname
        st.write(f"Letöltendő fájl: `{fname}`")
        # letöltés
        zip_bytes = download_zip_bytes(file_url)
        # a belső csv fájlnév általában a zip fájl neve nélkül a .zip nélkül; de extract függvény kezeli
        csv_text = extract_csv_from_zipbytes(zip_bytes, expected_csv_name=fname.replace(".zip", ""))
        # parse
        min_res, max_res, used_cols = parse_and_find_extremes(csv_text)

        st.success(f"A fájl beolvasása sikeres. (Használt oszlopok: {used_cols})")

        date_str = date_selected.strftime("%Y.%m.%d")
        # Kiírás a kért formátumban:
        parts = []
        if max_res:
            parts.append(f"Maximum: {max_res['value']} °C (állomás: {max_res['station']})")
        else:
            parts.append("Maximum: Nincs elérhető adat")

        if min_res:
            parts.append(f"Minimum: {min_res['value']} °C (állomás: {min_res['station']})")
        else:
            parts.append("Minimum: Nincs elérhető adat")

        st.markdown(f"### A hőmérsékleti szélső értékek {date_str}-re vonatkozóan:\n\n" + " | ".join(parts))

    except requests.HTTPError as e:
        st.error(f"Hiba a fájl letöltésekor: {e}. Ellenőrizd, hogy a fájl létezik a szerveren (a dátum lehet, hogy túl friss, vagy túl régi).")
    except FileNotFoundError as e:
        st.error(f"A zip fájlban nem található CSV: {e}")
    except Exception as e:
        st.error(f"Hiba történt: {e}")


