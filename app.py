import streamlit as st
import requests
import zipfile
import io
import pandas as pd
from datetime import datetime

st.title("Magyarországi napi hőmérsékleti szélsőértékek")
st.write("Adatok forrása: [Hungaromet ODP](https://odp.met.hu/weather/weather_reports/synoptic/hungary/daily/c_input("Válassz dátumot:", datetime.now())
date_str = selected_date.strftime("%Y%m%d")

if st.button("Hőmérsékleti adatok lekérése"):
    url = f"https://odp.met.hu/weather/weather_reports/synoptic/hungary/daily/csv/HABP_1D_{date_str}.zip"
    st.write(f"Adatok letöltése: {url}")
    response = requests.get(url)

    if response.status_code != 200:
        st.error("Nem sikerült letölteni az adatokat. Lehet, hogy nincs adat a kiválasztott napra.")
    else:
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            csv_name = f"HABP_1D_{date_str}.csv"
            with z.open(csv_name) as csv_file:
                df = pd.read_csv(csv_file, sep=';', encoding='utf-8')

        # Szűrés: tn és tx oszlopok, és -999 értékek kizárása
        df = df[(df['tn'] != -999) & (df['tx'] != -999)]

        if df.empty:
            st.warning("Nincs érvényes adat a kiválasztott napra.")
        else:
            min_temp = df['tn'].min()
            max_temp = df['tx'].max()
            min_station = df.loc[df['tn'].idxmin(), 'stationName']
            max_station = df.loc[df['tx'].idxmax(), 'stationName']

            st.success(f"A hőmérsékleti szélső értékek {selected_date.strftime('%Y.%m.%d')}-re vonatkozóan:")
            st.write(f"**Maximum:** {max_temp} °C (állomás: {max_station})")
            st.write(f"**Minimum:** {min_temp} °C (állomás: {min_station})")
