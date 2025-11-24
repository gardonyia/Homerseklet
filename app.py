
import streamlit as st
import requests
import zipfile
import io
import pandas as pd
from datetime import datetime

# Cím és forrás
st.title("Magyarországi napi hőmérsékleti szélsőértékek")
st.write("Adatok forrása: [Hungaromet ODP"]
(https://odp.met.hu/weather/weather_reports/synoptic/hungary/dailyte_input("Válassz dátumot:", datetime.now())
date_tag = selected_date.strftime("%Y%m%d")
human_date = selected_date.strftime("%Y.%m.%d")

def load_daily_df(date_tag: str) -> pd.DataFrame | None:
    url = f"https://odp.met.hu/weather/weather_reports/synoptic/hungary/daily/csv/HABP_1D_{date_tag}.csv.zip"
    st.write(f"Adatok letöltése: {url}")
    resp = requests.get(url)
    if resp.status_code != 200:
        st.error("Nem sikerült letölteni az adatokat. Lehet, hogy nincs adat a kiválasztott napra.")
        return None

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        csv_members = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not csv_members:
            st.error("A ZIP fájl nem tartalmaz CSV fájlt.")
            return None
        csv_name = csv_members[0]
        with z.open(csv_name) as csv_file:
            df = pd.read_csv(csv_file, sep=';', encoding='utf-8', dtype=str)
            return df

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    return df

def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None

def to_numeric_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors='coerce')

if st.button("Hőmérsékleti adatok lekérése"):
    df_raw = load_daily_df(date_tag)
    if df_raw is None:
        st.stop()

    df = normalize_columns(df_raw)

    tn_col = find_column(df, ["tn", "tmin", "min_temp", "t_n"])
    tx_col = find_column(df, ["tx", "tmax", "max_temp", "t_x"])
    station_col = find_column(df, ["stationname", "station_name", "station", "name", "allomas", "állomás"])

    missing = []
    if tn_col is None: missing.append("minimum (tn/tmin)")
    if tx_col is None: missing.append("maximum (tx/tmax)")
    if station_col is None: missing.append("állomásnév (stationName/station)")
    if missing:
        st.error("Hiányzó oszlop(ok): " + ", ".join(missing))
        st.code("Elérhető oszlopok:\n" + "\n".join(df.columns), language="text")
        st.stop()

    df[tn_col] = to_numeric_series(df[tn_col])
    df[tx_col] = to_numeric_series(df[tx_col])

    valid = df[(df[tn_col].notna()) & (df[tx_col].notna())]
    valid = valid[(valid[tn_col] != -999) & (valid[tx_col] != -999)]

    if valid.empty:
        st.warning("Nincs érvényes adat a kiválasztott napra.")
        st.stop()

    min_idx = valid[tn_col].idxmin()
    max_idx = valid[tx_col].idxmax()
    min_temp = valid.loc[min_idx, tn_col]
    max_temp = valid.loc[max_idx, tx_col]
    min_station = valid.loc[min_idx, station_col]
    max_station = valid.loc[max_idx, station_col]

    st.success(f"A hőmérsékleti szélső értékek {human_date}-re vonatkozóan:")
    st.write(f"**Maximum:** {max_temp} °C (állomás: {max_station})")
    st.write(f"**Minimum:** {min_temp} °C (állomás: {min_station})")

    with st.expander("Részletek / nyers adatok"):
        st.write("Oszlopok:", list(df.columns))
        st.dataframe(valid[[station_col, tn_col, tx_col]].head(20))

