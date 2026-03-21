import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import yfinance as yf
from datetime import datetime
# --- 1. Datenbank Setup ---
# Ich nutze @st.cache_resource damit die Verbindung
# nicht bei jedem Klick neu aufgebaut wird

@st.cache_resource
def get_connection():
    conn = sqlite3.connect("portfolio.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            buy_price REAL NOT NULL,
            buy_date TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn
conn = get_connection()
# --- 2. Logik-Funktionen (identisch zu deinem Code) ---
def add_position(ticker, shares, buy_price, buy_date):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO portfolio (ticker, shares, buy_price, buy_date)
        VALUES (?, ?, ?, ?)
    """, (ticker.upper(), shares, buy_price, str(buy_date)))
    conn.commit()
def delete_position(position_id):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM portfolio WHERE id = ?", (position_id,))
    conn.commit()
# Ich cache die Preise damit nicht bei jedem
# Klick Yahoo Finance neu angefragt wird (ttl = 5 Minuten)
@st.cache_data(ttl=300)
def get_current_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        return hist["Close"].iloc[-1] if not hist.empty else 0.0
    except:
        return 0.0
def get_portfolio_data():
    df = pd.read_sql("SELECT * FROM portfolio", conn)
    if df.empty:
        return df
    df["current_price"] = df["ticker"].apply(get_current_price)
    df["invested"] = df["shares"] * df["buy_price"]
    df["current_value"] = df["shares"] * df["current_price"]
    df["pnl"] = df["current_value"] - df["invested"]
    df["return_%"] = ((df["current_price"] - df["buy_price"]) / df["buy_price"] * 100).round(2)
    return df
# --- 3. Streamlit UI ---
st.title("📈 Portfolio Intelligence Tool")
st.divider()
# Sidebar für Eingabe
# Ich nutze die Sidebar damit die Eingabe immer sichtbar ist
# egal auf welcher Seite du bist
with st.sidebar:
    st.header("➕ Position hinzufügen")
    ticker = st.text_input("Ticker", placeholder="z.B. AAPL").upper()
    shares = st.number_input("Anzahl Aktien", min_value=0.01, value=1.0)
    buy_price = st.number_input("Kaufpreis ($)", min_value=0.01, value=100.0)
    buy_date = st.date_input("Kaufdatum", value=datetime.now())
    if st.button("✅ Hinzufügen", use_container_width=True):
        if ticker:
            add_position(ticker, shares, buy_price, buy_date)
            st.success(f"{ticker} wurde gespeichert!")
            # Cache leeren damit neue Daten sofort erscheinen
            st.cache_data.clear()
        else:
            st.warning("Bitte Ticker eingeben!")
# Hauptbereich
df = get_portfolio_data()
if df.empty:
    st.info("Noch keine Positionen. Füge links deine erste Position hinzu!")
else:
    # --- Kennzahlen oben ---
    # st.columns teilt die Seite in gleich breite Spalten
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "💼 Gesamtwert", 
        f"${df['current_value'].sum():,.2f}"
    )
    col2.metric(
        "💰 Investiert", 
        f"${df['invested'].sum():,.2f}"
    )
    col3.metric(
        "📊 P&L", 
        f"${df['pnl'].sum():,.2f}",
        delta=f"{df['pnl'].sum():,.2f}"  # Grün/Rot Indikator
    )
    col4.metric(
        "📈 Return", 
        f"{((df['current_value'].sum() / df['invested'].sum() - 1) * 100):.2f}%"
    )
    st.divider()
    # --- Portfolio Tabelle mit schöner Formatierung ---
    st.subheader("📋 Positionen")

    # Wir erstellen eine Kopie für die Anzeige
    display_df = df[["id", "ticker", "shares", "buy_price", "current_price", "pnl", "return_%"]].copy()

    # Farben definieren
    def color_pnl(val):
        color = "green" if val > 0 else "red"
        return f"color: {color}"

    # Die Tabelle mit Formatierung ausgeben
    st.dataframe(
        display_df.style.map(color_pnl, subset=["pnl", "return_%"])
        .format({
            "shares": "{:.2f}",
            "buy_price": "${:.2f}",
            "current_price": "${:.2f}",
            "pnl": "${:.2f}",
            "return_%": "{:.2f}%"
        }),
        use_container_width=True,
        hide_index=True
    )
        
    st.subheader("🍕 Portfolio-Verteilung")
    fig = px.pie(df, values='current_value', names='ticker', hole=0.4)
    st.plotly_chart(fig, use_container_width=True)
    # --- Position löschen ---
    st.divider()  
    st.subheader("🗑️ Position löschen")
    col1, col2 = st.columns([1, 3])
    with col1:
        delete_id = st.number_input("ID", min_value=1, step=1)
    with col2:
        if st.button("Löschen", type="secondary"):
            delete_position(delete_id)
            st.cache_data.clear()
            st.rerun()  # Seite neu laden nach Löschen
