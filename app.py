import streamlit as st
from datetime import date

# --- 1. CONNESSIONE AL DATABASE ONLINE (SUPABASE) ---
# Streamlit leggerà le credenziali in modo sicuro dai "Secrets" del cloud
conn = st.connection("postgresql", type="sql")

# --- 2. CONFIGURAZIONE INTERFACCIA WEB ---
st.set_page_config(page_title="Prenotazione Parcheggi", page_icon="🚗", layout="centered")
st.title("🚗 Gestionale Parcheggio Aziendale")

# Recupero la lista degli utenti da Supabase per il login simulato
utenti_df = conn.query("SELECT username FROM utenti ORDER BY username;", ttl=0)
lista_utenti = utenti_df["username"].tolist()

st.sidebar.header("🔑 Accesso")
utente_loggato = st.sidebar.selectbox("Seleziona il tuo utente:", lista_utenti)

# --- 3. LOGICA DI PRENOTAZIONE ---
if utente_loggato:
    # Recupera i dati dell'utente dal database online
    info_df = conn.query("""
        SELECT u.id, u.targa, g.nome as gruppo_nome, g.quota, g.id as gruppo_id
        FROM utenti u
        JOIN gruppi g ON u.gruppo_id = g.id
        WHERE u.username = :username;
    """, params={"username": utente_loggato}, ttl=0)

    if not info_df.empty:
        u_id = int(info_df["id"].iloc[0])
        targa = info_df["targa"].iloc[0]
        nome_gruppo = info_df["gruppo_nome"].iloc[0]
        quota = int(info_df["quota"].iloc[0])
        g_id = int(info_df["gruppo_id"].iloc[0])

        st.sidebar.success(f"Loggato come: {utente_loggato}")
        st.sidebar.write(f"🏷️ **Targa:** {targa}")
        st.sidebar.write(f"🏢 **Gruppo:** {nome_gruppo} (Quota: {quota} posti)")
        
        st.divider()
        
        # Area Selezione Data
        st.subheader("📅 Nuova Prenotazione")
        oggi = date.today()
        data_scelta = st.date_input("Seleziona il giorno:", min_value=oggi)
        data_str = data_scelta.strftime("%Y-%m-%d")
        
        if st.button("Conferma Posto 🟢", use_container_width=True):
            # Controllo disponibilità quote in tempo reale
            conta_df = conn.query("""
                SELECT COUNT(*) as occupati FROM prenotazioni p
                JOIN utenti u ON p.utente_id = u.id
                WHERE u.gruppo_id = :g_id AND p.data = :data;
            """, params={"g_id": g_id, "data": data_str}, ttl=0)
            posti_occupati = int(conta_df["occupati"].iloc[0])
            
            if posti_occupati >= quota:
                st.error(f"⛔ Impossibile prenotare. Il gruppo {nome_gruppo} ha esaurito i posti per il {data_str}.")
            else:
                try:
                    # Inserimento sicuro della prenotazione tramite transazione
                    with conn.session as session:
                        session.execute(
                            "INSERT INTO prenotazioni (utente_id, data) VALUES (:u_id, :data);",
                            {"u_id": u_id, "data": data_str}
                        )
                        session.commit()
                    st.success(f"✅ Prenotazione confermata per il {data_str}!")
                    st.rerun()
                except Exception:
                    st.warning("⚠️ Hai già un posto prenotato per questa data.")

        st.divider()

        # --- 4. RIEPILOGO PRENOTAZIONI ATTIVE ---
        st.subheader("📋 I tuoi posti prenotati")
        mie_p_df = conn.query("""
            SELECT data FROM prenotazioni 
            WHERE utente_id = :u_id AND data >= :oggi 
            ORDER BY data;
        """, params={"u_id": u_id, "oggi": oggi.strftime("%Y-%m-%d")}, ttl=0)
        
        if not mie_p_df.empty:
            for p_data in mie_p_df["data"]:
                # Correzione formattazione data per display
                p_str = p_data.strftime("%Y-%m-%d") if hasattr(p_data, 'strftime') else str(p_data)
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"🚗 Posto riservato per il: **{p_str}**")
                with col2:
                    if st.button("❌ Cancella", key=f"del_{p_str}"):
                        with conn.session as session:
                            session.execute(
                                "DELETE FROM prenotazioni WHERE utente_id = :u_id AND data = :data;",
                                {"u_id": u_id, "data": p_str}
                            )
                            session.commit()
                        st.rerun()
        else:
            st.info("Nessuna prenotazione futura.")