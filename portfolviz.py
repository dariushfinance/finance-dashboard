# --- Vorhandene Charts (Pie Chart) ---
    st.subheader("🍕 Portfolio-Verteilung")
    fig = px.pie(df, values='current_value', names='ticker', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
    st.plotly_chart(fig, use_container_width=True)

    # --- JETZT NEU: Den Zeitstrahl aufrufen ---
    st.divider()
    plot_portfolio_history_accurate(df) 
    # ^-- Dieser Befehl hat gefehlt!

    st.divider()

    # --- Lösch-Bereich (Korrigierte Einrückung) ---
    st.subheader("🗑️ Position löschen")
    if not df.empty:
        col_del1, col_del2 = st.columns([1, 3])
        with col_del1:
            delete_id = st.selectbox("ID wählen", options=df["id"].tolist())
        with col_del2:
            if st.button("🗑️ Diese Position löschen", type="secondary"):
                delete_position(delete_id, current_user)
                st.success(f"Position {delete_id} wurde entfernt.")
                st.cache_data.clear()
                st.rerun()
