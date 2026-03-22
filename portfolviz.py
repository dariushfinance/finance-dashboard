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
        try:
            # 1. Ticker und frühestes Datum vorbereiten
            tickers = df["ticker"].unique().tolist()
            earliest_date = pd.to_datetime(df["buy_date"]).min().strftime('%Y-%m-%d')
            
            # 2. Daten laden
            # Wir nutzen 'multi_level_index=False', um eine flache Tabelle zu bekommen
            data = yf.download(tickers, start=earliest_date, interval="1d")
            
            if data.empty:
                st.warning("Keine historischen Daten gefunden.")
                return

            # WICHTIG: Wir extrahieren nur die Schlusskurse ('Close')
            # yfinance gibt bei einem Ticker oft eine Series zurück, bei vielen ein DF
            if "Close" in data.columns:
                hist_data = data["Close"]
            else:
                # Fallback für neuere yfinance Versionen bei Einzel-Tickern
                hist_data = data

            # Falls es eine Series ist (nur 1 Ticker), in DataFrame umwandeln
            if isinstance(hist_data, pd.Series):
                hist_data = hist_data.to_frame(name=tickers[0])

            # 3. Daily Portfolio Value berechnen
            daily_values = pd.DataFrame(index=hist_data.index)
            daily_values["Total_Value"] = 0.0

            for _, row in df.iterrows():
                t = row["ticker"]
                shares = row["shares"]
                buy_dt = pd.to_datetime(row["buy_date"])
                
                # Check ob Ticker in den Daten ist (manchmal fehlen Ticker bei Fehlern)
                if t in hist_data.columns:
                    # Preis-Daten für diesen Ticker holen & Lücken füllen
                    prices = hist_data[t].ffill().fillna(0)
                    
                    # Maske: Nur ab Kaufdatum
                    # Wir machen beide Indizes "timezone-naive", um Fehler zu vermeiden
                    prices.index = prices.index.tz_localize(None)
                    buy_dt = buy_dt.tz_localize(None)
                    
                    mask = prices.index >= buy_dt
                    daily_values.loc[mask, "Total_Value"] += prices.loc[mask] * shares

            # 4. Chart zeichnen
            if daily_values["Total_Value"].max() > 0:
                fig = px.area(
                    daily_values, 
                    y="Total_Value",
                    title=f"Gesamtwert-Entwicklung für {current_user}",
                    labels={"Total_Value": "Wert ($)", "index": "Datum"}
                )
                
                # Styling
                fig.update_layout(
                    xaxis_title="Datum",
                    yaxis_title="Portfolio Wert",
                    hovermode="x unified"
                )
                fig.update_traces(line_color='#22c55e', fillcolor='rgba(34, 197, 94, 0.2)')
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Historische Daten konnten nicht berechnet werden (evtl. liegt das Kaufdatum in der Zukunft oder Ticker ungültig).")
                
        except Exception as e:
            st.error(f"Fehler bei der Chart-Erstellung: {e}")
            # Optional: Zeige das Datenformat für Debugging (nur für dich als Entwickler)
            # st.write(data.head())
            
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
