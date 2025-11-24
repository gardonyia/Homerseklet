import streamlit as st
import requests
import zipfile
import io
import pandas as pd
from datetime import datetime

st.title("Magyarországi napi hőmérsékleti szélsőértékek")
st.write("Adatok forrása: [Hungaromet ODP]
(https://odp.met.hu/weather/weather_reports/synoptic/hunge = st.date_input("Válassz dátumot:", datetime.now())
selected_date = st.date_input("Válassz dátumot:", datetime.now())
date_tag = selected_date.strftime("%Y%m%d")
human_date = selected_date.strftime("%Y.%m.%d")

def load_daily_df(date_tag: str) -> pd.DataFrame | None:
    """Letölti a megadott nap ZIP-jét, kikeresi benne a CSV-t és DataFrame-ként visszaadja."""
    url = f"https://odp.met.hu/weather/weather_reports/synoptic/hungary/daily/csv/HABP_1D_{date_tag}.csv.zip"
    st.write(f"Adatok letöltése: {url}")
    resp = requests.get(url)
    if resp.status_code != 200:
        st.error("Nem sikerült letölteni az adatokat. Lehet, hogy nincs adat a kiválasztott napra.")
        return None

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        # Próbáljuk automatikusan megtalálni a CSV-t
        csv_members = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not csv_members:
            st.error("A ZIP fájl nem tartalmaz CSV fájlt.")
            return None
        csv_name = csv_members[0]  # ha több van, az elsőt választjuk
        with z.open(csv_name) as csv_file:
            # A Hungaromet CSV-k általában ';' szeparátort használnak
            df = pd.read_csv(csv_file, sep=';', encoding='utf-8', dtype=str)
            return df

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Oszlopnevek tisztítása (strip + lower), és a tipikus elnevezések azonosítása."""
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    return df

def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Megpróbál egy oszlopot megtalálni a megadott jelöltek közül."""
    for c in candidates:
        if c in df.columns:
            return c
    return None

def to_numeric_series(s: pd.Series) -> pd.Series:
    """Konverzió numerikus típusra; pont a tizedesjel, hibák NaN-ná."""
    return pd.to_numeric(s, errors='coerce')

# Gomb az adatok lekéréséhez
if st.button("Hőmérsékleti adatok lekérése"):
    df_raw = load_daily_df(date_tag)
    if df_raw is None:
        st.stop()

    # Oszlopnevek normalizálása
    df = normalize_columns(df_raw)

    # Tipikus oszlopnevek – több lehetséges variánst is lefedünk
    tn_col = find_column(df, ["tn", "tmin", "min_temp", "t_n"])  # minimum
    tx_col = find_column(df, ["tx", "tmax", "max_temp", "t_x"])  # maximum
    station_col = find_column(df, ["stationname", "station_name", "station", "name", "allomas", "állomás"])

    # Ha valamelyik nincs meg, jelezzük a rendelkezésre álló oszlopokat
    missing = []
    if tn_col is None: missing.append("minimum (tn/tmin)")
    if tx_col is None: missing.append("maximum (tx/tmax)")
    if station_col is None: missing.append("állomásnév (stationName/station)")
    if missing:
        st.error("Hiányzó oszlop(ok): " + ", ".join(missing))
        st.code("Elérhető oszlopok:\n" + "\n".join(df.columns), language="text")
        st.stop()

    # Numerikus konverzió
    df[tn_col] = to_numeric_series(df[tn_col])
    df[tx_col] = to_numeric_series(df[tx_col])

    # -999 (hiányzó) értékek kiszűrése, és NaN-ok eldobása
    valid = df[(df[tn_col].notna()) & (df[tx_col].notna())]
    valid = valid[(valid[tn_col] != -999) & (valid[tx_col] != -999)]

    if valid.empty:
        st.warning("Nincs érvényes adat a kiválasztott napra (minden érték hiányzó volt vagy nem számszerű).")
        st.code("Elérhető oszlopok:\n" + "\n".join(df.columns), language="text")
        st.stop()

    # Szélsőértékek
    min_idx = valid[tn_col].idxmin()
    max_idx = valid[tx_col].idxmax()
    min_temp = valid.loc[min_idx, tn_col]
    max_temp = valid.loc[max_idx, tx_col]
    min_station = valid.loc[min_idx, station_col]
    max_station = valid.loc[max_idx, station_col]

    # Eredmény
    st.success(f"A hőmérsékleti szélső értékek {human_date}-re vonatkozóan:")
    st.write(f"**Maximum:** {max_temp} °C (állomás: {max_station})")
    st.write(f"**Minimum:** {min_temp} °C (állomás: {min_station})")

    # Opcionális: mutassuk meg az első pár sort a diagnosztika érdekében
    with st.expander("Részletek / nyers adatok (diagnosztika)"):
        st.write("Oszlopok:", list(df.columns))


