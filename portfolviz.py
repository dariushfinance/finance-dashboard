import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import yfinance as yf
from datetime import datetime
import requests

ALPHA_VANTAGE_KEY = "1GYL3R16Q3QTXQAT"

# --- 1. Datenbank Setup ---
@st.cache_resource
def get_connection():
    conn = sqlite3.connect("portfolio.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'default',
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            buy_price REAL NOT NULL,
            buy_date TEXT NOT NULL
        )
    """)
    try:
        cursor.execute("ALTER TABLE portfolio ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")
    except:
        pass 
    conn.commit()
    return conn

conn = get_connection()

# --- 2. Logik-Funktionen ---
def add_position(user_id, ticker, shares, buy_price, buy_date):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO portfolio (user_id, ticker, shares, buy_price, buy_date)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id.lower(), ticker.upper(), shares, buy_price, str(buy_date)))
    conn.commit()

def delete_position(position_id, user_id):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM portfolio WHERE id = ? AND user_id = ?", (position_id, user_id.lower()))
    conn.commit()

@st.cache_data(ttl=300)
def get_current_price(ticker):
    try:
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={ALPHA_VANTAGE_KEY}"
        response = requests.get(url)
        data = response.json()
        if "Global Quote" in data and "05. price" in data["Global Quote"]:
            return float(data["Global Quote"]["05. price"])
    except:
        pass

    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        if not hist.empty:
            return hist["Close"].iloc[-1]
    except:
        pass
    return 0.0

def get_portfolio_data(user_id):
    query = "SELECT * FROM portfolio WHERE user_id = ?"
    df = pd.read_sql(query, conn, params=(user_id.lower(),))
    if df.empty:
        return df
    df["current_price"] = df["ticker"].apply(get_current_price)
    df["invested"] = df["shares"] * df["buy_price"]
    df["current_value"] = df["shares"] * df["current_price"]
    df["pnl"] = df["current_value"] - df["invested"]
    df["return_%"] = ((df["current_price"] - df["buy_price"]) / df["buy_price"] * 100).round(2)
    return df

def plot_portfolio_history_accurate(df):
    if df.empty:
        return
    st.subheader("📈 Portfolio-Wertentwicklung (Zeitstrahl)")
    with st.spinner("Historie wird präzise berechnet..."):
        tickers = df["ticker"].unique().tolist()
        earliest_date = pd.to_datetime(df["buy_date"]).min()
        hist_data = yf.download(tickers, start=earliest_date, interval="1d")["Close"]
        if len(tickers) == 1:
            hist_data = hist_data.to_frame(name=tickers[0])
        
        daily_values = pd.DataFrame(index=hist_data.index)
        daily_values["Total_Value"] = 0.0
        for _, row in df.iterrows():
            ticker = row["ticker"]
            shares = row["shares"]
            buy_date = pd.to_datetime(row["buy_date"])
            if ticker in hist_data.columns:
                mask = hist_data.index >= buy_date
                daily_values.loc[mask, "Total_Value"] += hist_data.loc[mask, ticker] * shares
        
        fig = px.area(daily_values, y="Total_Value", title="Dein tatsächlicher Vermögensverlauf")
        st.plotly_chart(fig, use_container_width=True)

# --- 3. Streamlit UI ---
st.set_page_config(page_title="Portfolio Tool", layout="wide")
st.title("📈 Portfolio Intelligence Tool")

with st.sidebar:
    st.header("👤 Benutzerprofil")
    current_user = st.text_input("Dein Portfolio-Name", value="MeinPortfolio").strip()
    st.divider()
    st.header("➕ Position hinzufügen")
    ticker = st.text_input("Ticker", placeholder="z.B. AAPL").upper()
    shares = st.number_input("Anzahl Aktien", min_value=0.01, value=1.0, step=0.01)
    buy_price = st.number_input("Kaufpreis ($)", min_value=0.01, value=100.0)
    buy_date = st.date_input("Kaufdatum", value=datetime.now())
    if st.button("✅ Hinzufügen", use_container_width=True):
        if ticker and current_user:
            add_position(current_user, ticker, shares, buy_price, buy_date)
            st.success(f"{ticker} gespeichert!")
            st.cache_data.clear()
            st.rerun()

df = get_portfolio_data(current_user)

if not current_user:
    st.warning("Bitte gib einen Portfolio-Namen ein.")
elif df.empty:
    st.info(f"Das Portfolio '{current_user}' ist leer.")
else:
    # Metriken
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
    st.subheader(f"📋 Positionen von: {current_user}")
    
    # Tabelle anzeigen
    st.dataframe(df[["id", "ticker", "shares", "buy_price", "current_price", "pnl", "return_%"]], use_container_width=True, hide_index=True)

    # Charts
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("🍕 Verteilung")
        fig_pie = px.pie(df, values='current_value', names='ticker', hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col_right:
        # Kleinerer Lösch-Bereich
        st.subheader("🗑️ Position löschen")
        with st.expander("Klicke zum Löschen"):
            del_id = st.selectbox("ID wählen", options=df["id"].tolist())
            if st.button("🗑️ Löschen bestätigen"):
                delete_position(del_id, current_user)
                st.cache_data.clear()
                st.rerun()

    st.divider()
    # Hier wird die Historie aufgerufen
    plot_portfolio_history_accurate(df)

# --- ADMIN BEREICH ---
st.sidebar.divider()
admin_key = st.sidebar.text_input("Admin-Passwort", type="password")
if admin_key == "Dariush2007":
    st.divider()
    st.header("🕵️ Master-Datenbank")
    all_data_df = pd.read_sql("SELECT * FROM portfolio ORDER BY user_id ASC", conn)
    user_list = ["ALLE ANZEIGEN"] + sorted(all_data_df["user_id"].unique().tolist())
    selected_user = st.selectbox("Filter nach User:", options=user_list)
    view_df = all_data_df if selected_user == "ALLE ANZEIGEN" else all_data_df[all_data_df["user_id"] == selected_user]
    st.dataframe(view_df, use_container_width=True, hide_index=True)
