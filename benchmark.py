import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go

def show_benchmark(df_portfolio):
    st.subheader("🏆 Portfolio vs. S&P 500 Vergleich")
    
    if df_portfolio.empty:
        st.info("Füge erst Positionen hinzu, um den Vergleich zu sehen.")
        return

    # Startdatum ermitteln
    start_date = pd.to_datetime(df_portfolio["buy_date"]).min()
    
    # S&P 500 laden
    with st.spinner('Lade Benchmark-Daten...'):
        # Wir holen den Kurs des S&P 500
        spy = yf.download("^GSPC", start=start_date)["Close"]
        
        # Wir brauchen die Kurse deiner Ticker für den Vergleich
        tickers = df_portfolio["ticker"].unique().tolist()
        hist_data = yf.download(tickers, start=start_date)["Close"]
    
    # Falls hist_data nur ein Ticker ist, wird es als Series geliefert -> Umwandeln in DataFrame
    if isinstance(hist_data, pd.Series):
        hist_data = hist_data.to_frame(name=tickers[0])

    # Berechnung der Performance
    combined = pd.DataFrame(index=spy.index)
    combined["SP500_Price"] = spy
    combined["Portfolio_Value"] = 0.0
    
    for _, row in df_portfolio.iterrows():
        t, shares = row["ticker"], row["shares"]
        if t in hist_data.columns:
            # Multipliziere Anteile mit historischem Kurs
            combined["Portfolio_Value"] += hist_data[t].ffill() * shares

    # Normalisierung auf 100
    combined["SP500_Indexed"] = (combined["SP500_Price"] / combined["SP500_Price"].iloc[0]) * 100
    combined["Portfolio_Indexed"] = (combined["Portfolio_Value"] / combined["Portfolio_Value"].iloc[0]) * 100

    # Chart erstellen
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=combined.index, y=combined["Portfolio_Indexed"], 
                             name="Mein Portfolio", line=dict(color="#22c55e", width=3)))
    fig.add_trace(go.Scatter(x=combined.index, y=combined["SP500_Indexed"], 
                             name="S&P 500 Index", line=dict(color="white", dash='dot')))
    
    fig.update_layout(title="Relative Performance (Startdatum des ersten Kaufs = 100)",
                      yaxis_title="Wertentwicklung indexiert",
                      template="plotly_dark",
                      legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01))
    
    st.plotly_chart(fig, use_container_width=True)
