import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import yfinance as yf
from datetime import datetime

# --- 1. Datenbank Setup ---
@st.cache_resource
def get_connection():
    conn = sqlite3.connect("portfolio.db", check_same_thread=False)
    cursor = conn.cursor()
    # Tabelle mit user_id erstellen
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
    # Sicherstellen, dass user_id Spalte existiert (falls Tabelle schon alt ist)
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

def delete_position(position_id):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM portfolio WHERE id = ?", (position_id,))
    conn.commit()

@st.cache_data(ttl=300)
def get_current_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        return hist["Close"].iloc[-1] if not hist.empty else 0.0
    except:
        return 0.0

def get_portfolio_data(user_id):
    # Nur Daten für den aktuellen Nutzer laden
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

# --- 3. Streamlit UI ---
st.set_page_config(page_title="Portfolio Tool", layout="wide")
st.title("📈 Portfolio Intelligence Tool")

# Sidebar
with st.sidebar:
    st.header("👤 Benutzerprofil")
    # Das ist der Schlüssel: Jeder gibt hier seinen Namen ein
    current_user = st.text_input("Dein Portfolio-Name", value="MeinPortfolio", help="Gib einen Namen ein, um dein eigenes Portfolio zu sehen.").strip()
    
    st.divider()
    st.header("➕ Position hinzufügen")
    ticker = st.text_input("Ticker", placeholder="z.B. AAPL").upper()
    shares = st.number_input("Anzahl Aktien", min_value=0.01, value=1.0, step=0.01)
    buy_price = st.number_input("Kaufpreis ($)", min_value=0.01, value=100.0)
    buy_date = st.date_input("Kaufdatum", value=datetime.now())
    
    if st.button("✅ Hinzufügen", use_container_width=True):
        if ticker and current_user:
            add_position(current_user, ticker, shares, buy_price, buy_date)
            st.success(f"{ticker} für {current_user} gespeichert!")
            st.cache_data.clear()
            st.rerun()
        else:
            st.warning("Bitte Ticker und Benutzername angeben!")

# Hauptbereich: Daten nur für den gewählten Nutzer laden
df = get_portfolio_data(current_user)

if not current_user:
    st.warning("Bitte gib links in der Sidebar einen Portfolio-Namen ein.")
elif df.empty:
    st.info(f"Das Portfolio '{current_user}' ist noch leer. Füge links eine Position hinzu!")
else:
    # Metriken
    col1, col2, col3, col4 = st.columns(4)
    total_val = df['current_value'].sum()
    total_inv = df['invested'].sum()
    total_pnl = df['pnl'].sum()
    total_ret = ((total_val / total_inv - 1) * 100) if total_inv > 0 else 0

    col1.metric("💼 Gesamtwert", f"${total_val:,.2f}")
    col2.metric("💰 Investiert", f"${total_inv:,.2f}")
    col3.metric("📊 P&L", f"${total_pnl:,.2f}", delta=f"${total_pnl:,.2f}")
    col4.metric("📈 Return", f"{total_ret:.2f}%")

    st.divider()

    # Tabelle
    st.subheader(f"📋 Positionen von: {current_user}")
    display_df = df[["id", "ticker", "shares", "buy_price", "current_price", "pnl", "return_%"]].copy()

    def color_pnl(val):
        return f"color: {'green' if val > 0 else 'red'}"

    st.dataframe(
        display_df.style.map(color_pnl, subset=["pnl", "return_%"])
        .format({
            "shares": "{:.2f}",
            "buy_price": "${:.2f}",
            "current_price": "${:.2f}",
            "pnl": "${:.2f}",
            "return_%": "{:.2f}%"
        }),
        use_container_width=True, hide_index=True
    )

    # Charts
    st.subheader("🍕 Portfolio-Verteilung")
    fig = px.pie(df, values='current_value', names='ticker', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
    st.plotly_chart(fig, use_container_width=True)

    # Löschen
    st.divider()
    st.subheader("🗑️ Position löschen")
    col_del1, col_del2 = st.columns([1, 3])
    with col_del1:
        # Nur IDs zur Auswahl geben, die dem Nutzer gehören
        delete_id = st.selectbox("ID zum Löschen wählen", options=df["id"].tolist())
    with col_del2:
        if st.button("🗑️ Position permanent löschen", type="secondary"):
            delete_position(delete_id)
            st.cache_data.clear()
            st.rerun()


# Ganz am Ende der Datei einfügen
st.sidebar.divider()
admin_key = st.sidebar.text_input("Admin-Passwort", type="password")

if admin_key == "Dariush2007": # Ändere "geheim123" in dein Wunschpasswort
    st.divider()
    st.header("🕵️ Master-Datenbank Ansicht")
    all_data = pd.read_sql("SELECT * FROM portfolio", conn)
    st.write("Hier sind alle Einträge aller Nutzer:")
    st.dataframe(all_data, use_container_width=True)
