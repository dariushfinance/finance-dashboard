import streamlit as st
import pandas as pd
import psycopg2
import yfinance as yf
import plotly.graph_objects as go

# Verbindung wie gehabt
def get_connection():
    return psycopg2.connect(
        host=st.secrets["DB_HOST"],
        database=st.secrets["DB_NAME"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASS"],
        port=st.secrets["DB_PORT"],
        sslmode="require"
    )

st.title("🏆 Portfolio vs. S&P 500")

# 1. Daten aus DB holen
conn = get_connection()
df_portfolio = pd.read_sql("SELECT ticker, shares, buy_date FROM portfolio WHERE user_id = 'meinportfolio'", conn) # Dein User hier!
conn.close()

if not df_portfolio.empty:
    # Startdatum ermitteln
    start_date = pd.to_datetime(df_portfolio["buy_date"]).min()
    
    # 2. Benchmarks laden (S&P 500 = ^GSPC)
    spy = yf.download("^GSPC", start=start_date)["Close"]
    
    # 3. Portfolio-Historie berechnen (vereinfacht für den Vergleich)
    tickers = df_portfolio["ticker"].unique().tolist()
    hist_data = yf.download(tickers, start=start_date)["Close"]
    
    # Alles auf einen gemeinsamen Index (Daten) bringen
    combined = pd.DataFrame(index=spy.index)
    combined["SP500_Price"] = spy
    combined["Portfolio_Value"] = 0.0
    
    for _, row in df_portfolio.iterrows():
        t, shares = row["ticker"], row["shares"]
        if t in hist_data.columns:
            combined["Portfolio_Value"] += hist_data[t].ffill() * shares

    # 4. NORMALISIERUNG (Der wichtigste Part!)
    # Wir setzen den ersten Wert auf 100
    combined["SP500_Indexed"] = (combined["SP500_Price"] / combined["SP500_Price"].iloc[0]) * 100
    combined["Portfolio_Indexed"] = (combined["Portfolio_Value"] / combined["Portfolio_Value"].iloc[0]) * 100

    # 5. Visualisierung
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=combined.index, y=combined["Portfolio_Indexed"], name="Mein Portfolio", line=dict(color="#22c55e", width=3)))
    fig.add_trace(go.Scatter(x=combined.index, y=combined["SP500_Indexed"], name="S&P 500 Index", line=dict(color="white", dash='dot')))
    
    fig.update_layout(title="Relative Performance (Start = 100)", yaxis_title="Wertentwicklung in %", template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    # Fazit
    current_perf = combined["Portfolio_Indexed"].iloc[-1] - 100
    spy_perf = combined["SP500_Indexed"].iloc[-1] - 100
    st.write(f"Deine Performance: **{current_perf:.2f}%** | S&P 500 Performance: **{spy_perf:.2f}%**")