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

# Usiamo lo "session_state" di Streamlit per ricordarci se l'utente ha già fatto il login
if "utente_autenticato" not in st.session_state:
    st.session_state["utente_autenticato"] = None

# --- 3. SCHERMATA DI LOGIN (Se non è già loggato) ---
if st.session_state["utente_autenticato"] is None:
    st.subheader("🔑 Accesso Riservato")
    st.write("Inserisci le tue credenziali aziendali per gestire la tua prenotazione.")
    
    with st.form("form_login"):
        username_inserito = st.text_input("Username o Email:")
        password_inserita = st.text_input("Password:", type="password")
        bottone_login = st.form_submit_button("Accedi 🔓", use_container_width=True)
        
        if bottone_login:
            if username_inserito and password_inserita:
                # Cerchiamo nel database se esiste un utente con quel nome E quella password
                risposta = supabase.table("utenti").select("id, username, targa, gruppo_id").eq("username", username_inserito).eq("password", password_inserita).execute()
                
                if risposta.data:
                    # Credenziali corrette! Salviamo i dati dell'utente nella sessione
                    st.session_state["utente_autenticato"] = risposta.data[0]
                    st.success("Accesso eseguito con successo!")
                    st.rerun()
                else:
                    st.error("❌ Username o Password errati. Riprova.")
            else:
                st.warning("Per favore, compila entrambi i campi.")
                
    st.stop() # Blocca l'esecuzione qui, non mostra il resto della pagina finché non fai il login

# --- 4. AREA RISERVATA (Accessibile solo dopo il Login) ---
utente_loggato = st.session_state["utente_autenticato"]
u_id = utente_loggato["id"]
username = utente_loggato["username"]
targa = utente_loggato["targa"]
g_id = utente_loggato["gruppo_id"]

# Recuperiamo le informazioni del gruppo (quota e nome) per questo specifico utente
info_gruppo = supabase.table("gruppi").select("nome, quota").eq("id", g_id).execute()
if info_gruppo.data:
    nome_gruppo = info_gruppo.data[0]["nome"]
    quota = info_gruppo.data[0]["quota"]
else:
    nome_gruppo = "Sconosciuto"
    quota = 0

# Sidebar con i dati personali nascosti agli altri
st.sidebar.header("👤 Il tuo Profilo")
st.sidebar.success(f"Benvenuto, {username}")
st.sidebar.write(f"🏷️ **Targa:** {targa}")
st.sidebar.write(f"🏢 **Gruppo:** {nome_gruppo}")

if st.sidebar.button("Log out ❌"):
    st.session_state["utente_autenticato"] = None
    st.rerun()

st.divider()

# --- 5. LOGICA DI PRENOTAZIONE ---
st.subheader("📅 Nuova Prenotazione")
oggi = date.today()
data_scelta = st.date_input("Seleziona il giorno:", min_value=oggi)
data_str = data_scelta.strftime("%Y-%m-%d")

if st.button("Conferma Posto 🟢", use_container_width=True):
    # Recuperiamo gli ID di tutti gli utenti che fanno parte dello stesso gruppo
    utenti_gruppo = supabase.table("utenti").select("id").eq("gruppo_id", g_id).execute()
    ids_gruppo = [u["id"] for u in utenti_gruppo.data]
    
    # Contiamo quante prenotazioni attive ci sono in quel giorno per questo specifico gruppo
    p_attive = supabase.table("prenotazioni").select("id").eq("data", data_str).in_("utente_id", ids_gruppo).execute()
    posti_occupati = len(p_attive.data)
    
    if posti_occupati >= quota:
        st.error(f"⛔ Impossibile prenotare. Il tuo gruppo ({nome_gruppo}) ha esaurito i posti per il {data_str}.")
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

# --- 6. RIEPILOGO PRENOTAZIONI PERSONALI ---
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
