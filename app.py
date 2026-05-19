import streamlit as st
from datetime import date
from supabase import create_client, Client

# --- 1. CONNESSIONE AL DATABASE ---
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- 2. CONFIGURAZIONE INTERFACCIA WEB ---
st.set_page_config(page_title="Parcheggi Symposium", page_icon="🚗", layout="centered")
st.title("🚗 Parcheggi Symposium")

# Stato della sessione per il login
if "utente_autenticato" not in st.session_state:
    st.session_state["utente_autenticato"] = None

# --- 3. SCHERMATA DI LOGIN ---
if st.session_state["utente_autenticato"] is None:
    st.subheader("🔑 Accesso Riservato")
    st.write("Inserisci le tue credenziali aziendali per accedere.")
    
    with st.form("form_login"):
        username_inserito = st.text_input("Username o Email:")
        password_inserita = st.text_input("Password:", type="password")
        bottone_login = st.form_submit_button("Accedi 🔓", use_container_width=True)
        
        if bottone_login:
            if username_inserito and password_inserita:
                risposta = supabase.table("utenti").select("id, username, targa, gruppo_id").eq("username", username_inserito).eq("password", password_inserita).execute()
                
                if risposta.data:
                    st.session_state["utente_autenticato"] = risposta.data[0]
                    st.success("Accesso eseguito!")
                    st.rerun()
                else:
                    st.error("❌ Username o Password errati.")
            else:
                st.warning("Compila entrambi i campi.")
                
    st.stop()

# Recupero dati dell'utente loggato
utente_loggato = st.session_state["utente_autenticato"]
username = utente_loggato["username"]

# Gestione pulsante di Log out globale nella sidebar
st.sidebar.header("👤 Account")
st.sidebar.write(f"Loggato come: **{username}**")
if st.sidebar.button("Log out ❌"):
    st.session_state["utente_autenticato"] = None
    st.rerun()

st.divider()

# --- 4. PANNELLO AMMINISTRATORE (Se l'utente è "Admin") ---
if username.lower() == "admin":
    st.subheader("📊 Tabellone Generale Prenotazioni (Admin)")
    st.write("Qui puoi vedere tutte le prenotazioni future effettuate dai dipendenti.")
    
    oggi_str = date.today().strftime("%Y-%m-%d")
    
    # Recuperiamo tutte le prenotazioni da oggi in poi, includendo i dati degli utenti (grazie alle relazioni di Supabase)
    # Nota: per far funzionare l'unione dei dati, chiediamo a Supabase di includere i campi dell'utente associato
    risposta_p = supabase.table("prenotazioni").select("data, utenti(username, targa)").gte("data", oggi_str).order("data").execute()
    
    if risposta_p.data:
        # Organizziamo i dati in una tabella pulita
        dati_tabella = []
        for p in risposta_p.data:
            # Gestione di sicurezza nel caso un utente sia stato cancellato ma la prenotazione esista ancora
            info_utente = p.get("utenti")
            nome_collega = info_utente.get("username", "Sconosciuto") if info_utente else "Sconosciuto"
            targa_collega = info_utente.get("targa", "-") if info_utente else "-"
            
            dati_tabella.append({
                "Data": p["data"],
                "Dipendente": nome_collega,
                "Targa Auto": targa_collega
            })
        
        # Mostra i dati sotto forma di tabella interattiva ed elegante
        st.dataframe(dati_tabella, use_container_width=True, hide_index=True)
    else:
        st.info("Al momento non ci sono prenotazioni future nel sistema.")
        
    st.stop() # L'admin si ferma qui, non deve vedere il form di prenotazione personale

# --- 5. INTERFACCIA UTENTE NORMALE (Prenotazione) ---
u_id = utente_loggato["id"]
targa = utente_loggato["targa"]
g_id = utente_loggato["gruppo_id"]

info_gruppo = supabase.table("gruppi").select("nome, quota").eq("id", g_id).execute()
if info_gruppo.data:
    nome_gruppo = info_gruppo.data[0]["nome"]
    quota = info_gruppo.data[0]["quota"]
else:
    nome_gruppo = "Sconosciuto"
    quota = 0

st.sidebar.write(f"🏷️ **Targa:** {targa}")
st.sidebar.write(f"🏢 **Gruppo:** {nome_gruppo}")

st.subheader("📅 Nuova Prenotazione")
oggi = date.today()
data_scelta = st.date_input("Seleziona il giorno:", min_value=oggi)
data_str = data_scelta.strftime("%Y-%m-%d")

if st.button("Conferma Posto 🟢", use_container_width=True):
    utenti_gruppo = supabase.table("utenti").select("id").eq("gruppo_id", g_id).execute()
    ids_gruppo = [u["id"] for u in utenti_gruppo.data]
    
    p_attive = supabase.table("prenotazioni").select("id").eq("data", data_str).in_("utente_id", ids_gruppo).execute()
    posti_occupati = len(p_attive.data)
    
    if posti_occupati >= quota:
        st.error(f"⛔ Posti esauriti per il tuo gruppo ({nome_gruppo}) in data {data_str}.")
    else:
        gia_prenotato = supabase.table("prenotazioni").select("id").eq("utente_id", u_id).eq("data", data_str).execute()
        if gia_prenotato.data:
            st.warning("⚠️ Hai già prenotato per questa data.")
        else:
            supabase.table("prenotazioni").insert({"utente_id": u_id, "data": data_str}).execute()
            st.success(f"✅ Posto confermato per il {data_str}!")
            st.rerun()

st.divider()

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
    st.info("Nessuna prenotazione futura attiva a tuo nome.")
