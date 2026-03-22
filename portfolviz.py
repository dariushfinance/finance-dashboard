import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import yfinance as yf
from datetime import datetime
import requests
import plotly.express as px

ALPHA_VANTAGE_KEY = "1GYL3R16Q3QTXQAT"

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

def delete_position(position_id, user_id):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM portfolio WHERE id = ? AND user_id = ?", (position_id, user_id.lower()))
    conn.commit()

@st.cache_data(ttl=300)


@st.cache_data(ttl=300)
def get_current_price(ticker):
    # 1. Versuch mit Alpha Vantage (Gut für SIX/ETFs)
    # Beispiel Ticker für SIX: "ROG.SW" -> bei Alpha Vantage oft "ROG.SWI"
    try:
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={ALPHA_VANTAGE_KEY}"
        response = requests.get(url)
        data = response.json()
        
        if "Global Quote" in data and "05. price" in data["Global Quote"]:
            return float(data["Global Quote"]["05. price"])
    except Exception as e:
        print(f"Alpha Vantage Fehler für {ticker}: {e}")

    # 2. Fallback auf Yahoo Finance (wenn Alpha Vantage nichts liefert oder Limit erreicht)
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        if not hist.empty:
            return hist["Close"].iloc[-1]
    except:
        pass

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

def plot_portfolio_history_accurate(df):
    if df.empty:
        return

    st.subheader("📈 Portfolio-Wertentwicklung (Zeitstrahl)")
    
    with st.spinner("Historie wird präzise berechnet..."):
        # 1. Alle Ticker und das früheste Kaufdatum finden
        tickers = df["ticker"].unique().tolist()
        earliest_date = pd.to_datetime(df["buy_date"]).min()
        
        # 2. Historische Kurse ab dem frühesten Kaufdatum laden
        hist_data = yf.download(tickers, start=earliest_date, interval="1d")["Close"]
        
        if len(tickers) == 1:
            hist_data = hist_data.to_frame(name=tickers[0])

        # 3. Daily Portfolio Value mit "Buy-Date-Check"
        daily_values = pd.DataFrame(index=hist_data.index)
        daily_values["Total_Value"] = 0.0

        for _, row in df.iterrows():
            ticker = row["ticker"]
            shares = row["shares"]
            buy_date = pd.to_datetime(row["buy_date"])
            
            if ticker in hist_data.columns:
                # Wir erstellen eine Maske: Nur Tage AB dem Kaufdatum zählen
                mask = hist_data.index >= buy_date
                # Nur für diese Tage addieren wir (Kurs * Anteile)
                daily_values.loc[mask, "Total_Value"] += hist_data.loc[mask, ticker] * shares

        # 4. Chart zeichnen
        fig = px.area( # 'area' sieht oft schicker aus für Vermögensaufbau
            daily_values, 
            y="Total_Value",
            title="Dein tatsächlicher Vermögensverlauf",
            labels={"Total_Value": "Wert", "index": "Datum"}
        )
        st.plotly_chart(fig, use_container_width=True)
    

    # Löschen
    if not df.empty:
        col_del1, col_del2 = st.columns([1, 3])
    with col_del1:
        # Wir zeigen im Dropdown nur die IDs an, die dem User SOWIESO gehören
        delete_id = st.selectbox("ID wählen", options=df["id"].tolist())
    with col_del2:
        if st.button("🗑️ Diese Position löschen", type="secondary"):
            # Hier übergeben wir jetzt die ID UND den aktuellen Namen
            delete_position(delete_id, current_user)
            st.success(f"Position {delete_id} wurde entfernt.")
            st.cache_data.clear()
            st.rerun()
        else:
            st.write("Keine Positionen zum Löschen vorhanden.")

# Ganz am Ende der Datei einfügen
# --- ADMIN BEREICH (Ganz unten) ---
st.sidebar.divider()
admin_key = st.sidebar.text_input("Admin-Passwort", type="password")

if admin_key == "Dariush2007": # <--- Hier dein Passwort eintragen
    st.divider()
    st.header("🕵️ Master-Datenbank")

    # 1. Alle Daten aus der DB ziehen
    all_data_df = pd.read_sql("SELECT * FROM portfolio ORDER BY user_id ASC", conn)

    if not all_data_df.empty:
        # 2. Filter-Optionen erstellen
        # Wir holen alle einzigartigen User-Namen für das Dropdown
        user_list = ["ALLE ANZEIGEN"] + sorted(all_data_df["user_id"].unique().tolist())
        
        selected_user = st.selectbox("Filter nach User:", options=user_list)

        # 3. Daten filtern
        if selected_user == "ALLE ANZEIGEN":
            view_df = all_data_df
        else:
            view_df = all_data_df[all_data_df["user_id"] == selected_user]

        # 4. Zusammenfassung für den Admin
        col_a, col_b = st.columns(2)
        col_a.metric("Anzahl Positionen", len(view_df))
        col_b.metric("Aktive User", len(all_data_df["user_id"].unique()))

        # 5. Die Tabelle anzeigen
        st.write(f"Datensätze für: **{selected_user}**")
        st.dataframe(view_df, use_container_width=True, hide_index=True)
        
        # 6. Kleiner "Lösch-Schutz" Hinweis
        st.caption("Hinweis: Als Admin siehst du hier die Rohdaten inklusive der Datenbank-IDs.")
    else:
        st.info("Die Datenbank ist noch komplett leer.")
