import streamlit as st
from datetime import date
from supabase import create_client, Client

# --- 1. CONNESSIONE COMPATIBILE AL DATABASE ONLINE ---
# Recuperiamo le chiavi di sicurezza dai Secrets di Streamlit
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- 2. CONFIGURAZIONE INTERFACCIA WEB ---
st.set_page_config(page_title="Prenotazione Parcheggi", page_icon="🚗", layout="centered")
st.title("🚗 Gestionale Parcheggio Aziendale")

# Recupero la lista degli utenti
try:
    utenti_response = supabase.table("utenti").select("username").order("username").execute()
    lista_utenti = [u["username"] for u in utenti_response.data]
except Exception as e:
    st.error(f"Errore di connessione al database: {e}")
    st.stop()

st.sidebar.header("🔑 Accesso")
utente_loggato = st.sidebar.selectbox("Seleziona il tuo utente:", lista_utenti)

# --- 3. LOGICA DI PRENOTAZIONE ---
if utente_loggato:
    # Recupera i dati dell'utente
    info = supabase.table("utenti").select("id, targa, gruppi(id, nome, quota)").eq("username", utente_loggato).execute()
    
    if info.data:
        dati_utente = info.data[0]
        u_id = dati_utente["id"]
        targa = dati_utente["targa"]
        nome_gruppo = dati_utente["gruppi"]["nome"]
        quota = dati_utente["gruppi"]["quota"]
        g_id = dati_utente["gruppi"]["id"]

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
            # Conta prenotazioni attive per quel gruppo e data
            conta = supabase.table("prenotazioni").select("id", count="exact").eq("data", data_str).execute()
            # Filtriamo via codice per sicurezza e semplicità di quote
            utenti_gruppo = supabase.table("utenti").select("id").eq("gruppo_id", g_id).execute()
            ids_gruppo = [u["id"] for u in utenti_gruppo.data]
            
            p_attive = supabase.table("prenotazioni").select("id").eq("data", data_str).in_("utente_id", ids_gruppo).execute()
            posti_occupati = len(p_attive.data)
            
            if posti_occupati >= quota:
                st.error(f"⛔ Impossibile prenotare. Il gruppo {nome_gruppo} ha esaurito i posti per il {data_str}.")
            else:
                # Controlla se l'utente ha già prenotato in quel giorno
                gia_prenotato = supabase.table("prenotazioni").select("id").eq("utente_id", u_id).eq("data", data_str).execute()
                if gia_prenotato.data:
                    st.warning("⚠️ Hai già un posto prenotato per questa data.")
                else:
                    supabase.table("prenotazioni").insert({"utente_id": u_id, "data": data_str}).execute()
                    st.success(f"✅ Prenotazione confermata per il {data_str}!")
                    st.rerun()

        st.divider()

        # --- 4. RIEPILOGO PRENOTAZIONI ATTIVE ---
        st.subheader("📋 I tuoi posti prenotati")
        mie_p = supabase.table("prenotazioni").select("data").eq("utente_id", u_id).gte("data", oggi.strftime("%Y-%m-%d")).order("data").execute()
        
        if mie_p.data:
            for p in mie_p.data:
                p_str = p["data"]
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"🚗 Posto riservato per il: **{p_str}**")
                with col2:
                    if st.button("❌ Cancella", key=f"del_{p_str}"):
                        supabase.table("prenotazioni").delete().eq("utente_id", u_id).eq("data", p_str).execute()
                        st.rerun()
        else:
            st.info("Nessuna prenotazione futura.")
