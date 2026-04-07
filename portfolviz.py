import streamlit as st
import pandas as pd
import plotly.express as px
import psycopg2
from psycopg2.extras import RealDictCursor
import yfinance as yf
from datetime import datetime
import requests
import numpy as np
from benchmark import show_benchmark

# --- Konfiguration ---
st.set_page_config(page_title="Portfolio Intelligence", layout="wide")

# --- Datenbank Verbindung (OPTIMIERT) ---
@st.cache_resource
def get_connection():
    try:
        conn = psycopg2.connect(
            host=st.secrets["host"],
            port=st.secrets["port"],
            dbname=st.secrets["database"],
            user=st.secrets["user"],
            password=st.secrets["password"],
            sslmode=st.secrets["sslmode"]
        )
        return conn
    except Exception as e:
        st.error(f"Datenbank-Fehler: {e}")
        return None

conn = get_connection()

# --- Hilfsfunktionen ---
def add_position(user_id, ticker, shares, buy_price, buy_date):
    conn = get_connection()
    if conn is None: return
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO portfolio (user_id, ticker, shares, buy_price, buy_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id.lower(), ticker.upper(), shares, buy_price, str(buy_date)))
        conn.commit()
    except Exception as e:
        st.error(f"Fehler beim Speichern: {e}")
    finally:
        cursor.close()

def delete_position(position_id, user_id):
    conn = get_connection()
    if conn is None: return
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM portfolio WHERE id = %s AND user_id = %s", (position_id, user_id.lower()))
        conn.commit()
    except Exception as e:
        st.error(f"Fehler beim Löschen: {e}")
    finally:
        cursor.close()

@st.cache_data(ttl=300)
def get_current_price(ticker):
    # 1. Versuch: Alpha Vantage
    try:
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={st.secrets['ALPHA_VANTAGE_KEY']}"
        data = requests.get(url).json()
        if "Global Quote" in data and "05. price" in data["Global Quote"]:
            return float(data["Global Quote"]["05. price"])
    except:
        pass
    # 2. Versuch: Yahoo Finance
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        if not hist.empty:
            return hist["Close"].iloc[-1]
    except:
        pass
    return 0.0

def get_portfolio_data(user_id):
    conn = get_connection()
    if conn is None: return pd.DataFrame()
    query = "SELECT * FROM portfolio WHERE user_id = %s"
    df = pd.read_sql(query, conn, params=(user_id.lower(),))
    
    if df.empty:
        return df
    
    with st.spinner('Aktuelle Kurse werden geladen...'):
        df["current_price"] = df["ticker"].apply(get_current_price)
        df["invested"] = df["shares"] * df["buy_price"]
        df["current_value"] = df["shares"] * df["current_price"]
        df["pnl"] = df["current_value"] - df["invested"]
        df["return_%"] = ((df["current_price"] - df["buy_price"]) / df["buy_price"] * 100).round(2)
    return df

def plot_portfolio_history_accurate(df, current_user):
    if df.empty: return
    st.subheader("📈 Portfolio-Wertentwicklung")
    try:
        tickers = df["ticker"].unique().tolist()
        earliest_date = pd.to_datetime(df["buy_date"]).min().strftime('%Y-%m-%d')
        data = yf.download(tickers, start=earliest_date, interval="1d")
        if data.empty: return

        hist_data = data["Close"] if "Close" in data.columns else data
        if isinstance(hist_data, pd.Series):
            hist_data = hist_data.to_frame(name=tickers[0])

        daily_values = pd.DataFrame(index=hist_data.index)
        daily_values["Total_Value"] = 0.0

        for _, row in df.iterrows():
            t, shares = row["ticker"], row["shares"]
            buy_dt = pd.to_datetime(row["buy_date"])
            if t in hist_data.columns:
                prices = hist_data[t].ffill().fillna(0)
                if prices.index.tz is not None: prices.index = prices.index.tz_localize(None)
                if buy_dt.tzinfo is not None: buy_dt = buy_dt.tz_localize(None)
                mask = prices.index >= buy_dt
                daily_values.loc[mask, "Total_Value"] += prices.loc[mask] * shares

        fig = px.area(daily_values, y="Total_Value", title=f"Historie: {current_user}")
        fig.update_traces(line_color='#22c55e', fillcolor='rgba(34, 197, 94, 0.2)')
        st.plotly_chart(fig, use_container_width=True)

        daily_ret = daily_values["Total_Value"].pct_change().dropna()
        if len(daily_ret) > 1:
            excess = daily_ret - 0.04 / 252
            sharpe = (excess.mean() / excess.std()) * np.sqrt(252)
            volatility = daily_ret.std() * np.sqrt(252)
            sv1, sv2 = st.columns(2)
            sv1.metric("⚡ Sharpe Ratio", f"{sharpe:.2f}")
            sv2.metric("📉 Volatilität (ann.)", f"{volatility:.1%}")
    except Exception as e:
        st.error(f"Fehler im Chart: {e}")

# --- Fundamentals / Comps ---
@st.cache_data(ttl=3600)
def get_fundamentals(ticker):
    try:
        info = yf.Ticker(ticker).info
        market_cap = info.get("marketCap")
        fcf = info.get("freeCashflow")
        return {
            "Ticker": ticker,
            "P/E": info.get("trailingPE"),
            "EV/EBITDA": info.get("enterpriseToEbitda"),
            "P/S": info.get("priceToSalesTrailing12Months"),
            "Gross Margin": info.get("grossMargins"),
            "Net Margin": info.get("profitMargins"),
            "ROE": info.get("returnOnEquity"),
            "Debt/Equity": info.get("debtToEquity"),
            "Rev Growth": info.get("revenueGrowth"),
            "FCF Yield": (fcf / market_cap) if fcf and market_cap else None,
        }
    except Exception:
        return {"Ticker": ticker}

def show_fundamentals(df):
    st.subheader("🏦 Company Fundamentals")
    tickers = df["ticker"].unique().tolist()
    with st.spinner("Lade Fundamentaldaten..."):
        rows = [get_fundamentals(t) for t in tickers]
    comp_df = pd.DataFrame(rows).set_index("Ticker")

    def fmt_mult(x): return f"{x:.1f}x" if pd.notna(x) else "—"
    def fmt_pct(x):  return f"{x:.1%}" if pd.notna(x) else "—"

    fmt = {
        "P/E": fmt_mult, "EV/EBITDA": fmt_mult, "P/S": fmt_mult, "Debt/Equity": fmt_mult,
        "Gross Margin": fmt_pct, "Net Margin": fmt_pct, "ROE": fmt_pct,
        "Rev Growth": fmt_pct, "FCF Yield": fmt_pct,
    }
    styled = comp_df.style.format(fmt)
    for col in ["Gross Margin", "Net Margin", "ROE", "Rev Growth", "FCF Yield"]:
        if col in comp_df.columns and comp_df[col].notna().any():
            styled = styled.background_gradient(subset=[col], cmap="RdYlGn", vmin=0)
    for col in ["P/E", "EV/EBITDA", "P/S", "Debt/Equity"]:
        if col in comp_df.columns and comp_df[col].notna().any():
            styled = styled.background_gradient(subset=[col], cmap="RdYlGn_r")
    st.dataframe(styled, use_container_width=True)

    with st.expander("📖 Metric Guide"):
        st.markdown("""
| Metric | What it means | Benchmark |
|---|---|---|
| **EV/EBITDA** | Core IB valuation multiple | <10x cheap · >20x growth premium |
| **P/E** | Price / Earnings | Compare within sector |
| **P/S** | Price / Sales | Useful for unprofitable growth cos |
| **Gross Margin** | Revenue − COGS / Revenue | >40% = strong pricing power |
| **Net Margin** | Bottom-line profitability | >10% healthy |
| **ROE** | Return on equity | >15% (Buffett benchmark) |
| **Debt/Equity** | Leverage ratio | <2x comfortable for PE |
| **Rev Growth** | YoY revenue growth | |
| **FCF Yield** | Free Cash Flow / Market Cap | >5% = PE-attractive |
        """)

# --- UI ---
with st.sidebar:
    st.header("👤 Benutzerprofil")
    current_user = st.text_input("Portfolio-Name", value="MeinPortfolio").strip()
    st.divider()
    st.header("➕ Position hinzufügen")
    ticker = st.text_input("Ticker", placeholder="AAPL").upper()
    shares = st.number_input("Anzahl", min_value=0.01, value=1.0)
    buy_price = st.number_input("Kaufpreis ($)", min_value=0.01, value=100.0)
    buy_date = st.date_input("Kaufdatum", value=datetime.now())
    
    if st.button("✅ Hinzufügen", use_container_width=True):
        if ticker and current_user:
            if get_current_price(ticker) == 0.0:
                st.error(f"'{ticker}' nicht gefunden. Bitte gültiges Ticker-Symbol eingeben (z.B. AAPL, MSFT).")
            else:
                add_position(current_user, ticker, shares, buy_price, buy_date)
                st.cache_data.clear()
                st.rerun()

st.title("📈 Portfolio Intelligence Tool")

if not current_user:
    st.warning("Bitte gib einen Namen ein.")
    df = pd.DataFrame()
else:
    df = get_portfolio_data(current_user)
    if df.empty:
        st.info(f"Portfolio '{current_user}' ist noch leer.")
    else:
        # Metriken berechnen
        total_val = df['current_value'].sum()
        total_inv = df['invested'].sum()
        total_pnl = df['pnl'].sum()
        total_ret = ((total_val / total_inv - 1) * 100) if total_inv > 0 else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("💼 Gesamtwert", f"${total_val:,.2f}")
        m2.metric("💰 Investiert", f"${total_inv:,.2f}")
        m3.metric("📊 P&L", f"${total_pnl:,.2f}", delta=f"${total_pnl:,.2f}")
        m4.metric("📈 Return", f"{total_ret:.2f}%")

        st.divider()
        st.dataframe(df[["id", "ticker", "shares", "buy_price", "current_price", "pnl", "return_%"]], 
                     use_container_width=True, hide_index=True)

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(px.pie(df, values='current_value', names='ticker', hole=0.4, title="Verteilung"), use_container_width=True)
        with c2:
            st.subheader("🗑️ Löschen")
            del_id = st.selectbox("Position wählen", options=df["id"].tolist() if not df.empty else [])
            if st.button("🗑️ Löschen"):
                delete_position(del_id, current_user)
                st.cache_data.clear()
                st.rerun()

        st.divider()
        plot_portfolio_history_accurate(df, current_user)

# --- Admin ---
st.sidebar.divider()
admin_key = st.sidebar.text_input("Admin-Bereich", type="password")
if admin_key == st.secrets["ADMIN_PASSWORD"]:
    st.divider()
    st.header("🕵️ Master-Datenbank")
    all_data = pd.read_sql("SELECT * FROM portfolio", get_connection())
    st.dataframe(all_data, use_container_width=True)

st.divider()
if not df.empty:
    show_benchmark(df)

st.divider()
if not df.empty:
    show_fundamentals(df)
