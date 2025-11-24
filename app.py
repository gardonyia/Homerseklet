import streamlit as st
import requests
import zipfile
import io
import pandas as pd
from datetime import datetime

# Cím és forrás
st.title("Magyarországi napi hőmérsékleti szélsőértékek")
st.write("Adatok forrása: [Hungaromet ODP](https://odp.met.hu/weather/weather_reports/synoptic/hungary/dailyte_input("Válassz dátumot:", datetime.now())
date_tag = selected_date.strftime("%Y%m%d")
human_date = selected_date.strftime("%Y.%m.%d")

def load_daily_df(date_tag: str) -> pd.DataFrame | None:
    """Letölti a megadott nap ZIP-jét, kikeresi benne a CSV-t és DataFrame-ként visszaadja."""
    url = f"https://odp.met.hu/weather/weather_reports/synoptic/hungary/daily/csv/HABP_1D_{date_tag}.zip"
    st.write(f"Adatok letöltése: {url}")
    resp = requests.get(url)
    if resp.status_code != 200:
        st.error("Nem sikerült letölteni az adatokat. Lehet, hogy nincs adat a kiválasztott napra.")
        return None

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
