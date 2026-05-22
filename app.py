import streamlit as st
from datetime import date
from supabase import create_client, Client
import plotly.graph_objects as go
from PIL import Image
import os

# --- 1. CONNESSIONE AL DATABASE ---
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- 2. CONFIGURAZIONE INTERFACCIA ---
st.set_page_config(page_title="Parcheggi Symposium", page_icon="🚗", layout="wide")
st.title("🚗 Parcheggi Symposium - Mappa Interattiva")

if "utente_autenticato" not in st.session_state:
    st.session_state["utente_autenticato"] = None

# --- 3. LOGIN ---
if st.session_state["utente_autenticato"] is None:
    st.subheader("🔑 Accesso Riservato")
    with st.form("form_login"):
        username_inserito = st.text_input("Username o Email:")
        password_inserita = st.text_input("Password:", type="password")
        if st.form_submit_button("Accedi 🔓", use_container_width=True):
            if username_inserito and password_inserita:
                risposta = supabase.table("utenti").select("id, username, targa, gruppo_id").eq("username", username_inserito).eq("password", password_inserita).execute()
                if risposta.data:
                    st.session_state["utente_autenticato"] = risposta.data[0]
                    st.rerun()
                else:
                    st.error("❌ Credenziali errate.")
    st.stop()

utente_loggato = st.session_state["utente_autenticato"]
username = utente_loggato["username"]

# Sidebar di controllo
st.sidebar.header("👤 Account")
st.sidebar.write(f"Utente: **{username}**")

# Selezione della Data (Fondamentale per la mappa temporale)
st.sidebar.divider()
st.sidebar.subheader("📅 Seleziona il Giorno")
oggi = date.today()
data_scelta = st.sidebar.date_input("Vedi prenotazioni del:", min_value=oggi)
data_str = data_scelta.strftime("%Y-%m-%d")

if st.sidebar.button("Log out ❌"):
    st.session_state["utente_autenticato"] = None
    st.rerun()

# --- 4. MAPPA DEI POSTI (DATABASE COORDINATE) ---
# Griglia matematica basata sul punto di riferimento (X:339, Y:356 per Studenti-9)
POSTI = {
    # ZONA CENTRALE STUDENTI (Azzurro verticale)
    "Studenti-7": {"x": 372, "y": 387, "tipo": "studenti"},
    "Studenti-8": {"x": 356, "y": 425, "tipo": "studenti"},
    "Studenti-9": {"x": 339, "y": 465, "tipo": "studenti"},
    "Studenti-10": {"x": 339, "y": 508, "tipo": "studenti"},
    "Studenti-11": {"x": 339, "y": 551, "tipo": "studenti"},
    "Studenti-12": {"x": 339, "y": 594, "tipo": "studenti"},
    "Studenti-13": {"x": 339, "y": 637, "tipo": "studenti"},
    "Studenti-14": {"x": 339, "y": 680, "tipo": "studenti"},
    
    # ZONA CENTRALE ALLOGGI (Verde in basso)
    "Alloggi-1": {"x": 290, "y": 748, "tipo": "alloggi"},
    "Alloggi-2": {"x": 232, "y": 748, "tipo": "alloggi"},
    "Alloggi-3": {"x": 174, "y": 748, "tipo": "alloggi"},
    "Alloggi-4": {"x": 116, "y": 748, "tipo": "alloggi"},
    "Alloggi-5": {"x": 58, "y": 748, "tipo": "alloggi"},
    
    # ZONA ALTA (Arancione a destra - Colonna 1)
    "Alta-1": {"x": 634, "y": 435, "tipo": "alta"},
    "Alta-2": {"x": 634, "y": 465, "tipo": "alta"},
    "Alta-3": {"x": 634, "y": 495, "tipo": "alta"},
    "Alta-4": {"x": 634, "y": 525, "tipo": "alta"},
    "Alta-5": {"x": 634, "y": 555, "tipo": "alta"},
    "Alta-6": {"x": 634, "y": 585, "tipo": "alta"},
    "Alta-7": {"x": 634, "y": 615, "tipo": "alta"},
    
    # ZONA ALTA (Arancione a destra - Colonna 2)
    "Alta-8": {"x": 841, "y": 412, "tipo": "alta"},
    "Alta-9": {"x": 841, "y": 438, "tipo": "alta"},
    "Alta-10": {"x": 841, "y": 464, "tipo": "alta"},
    "Alta-11": {"x": 841, "y": 490, "tipo": "alta"},
    "Alta-12": {"x": 841, "y": 516, "tipo": "alta"},
    "Alta-13": {"x": 841, "y": 542, "tipo": "alta"},
    "Alta-14": {"x": 841, "y": 568, "tipo": "alta"},
    "Alta-15": {"x": 841, "y": 594, "tipo": "alta"},
    "Alta-16": {"x": 841, "y": 620, "tipo": "alta"},
    "Alta-17": {"x": 841, "y": 646, "tipo": "alta"},
    "Alta-18": {"x": 841, "y": 672, "tipo": "alta"},
    "Alta-19": {"x": 841, "y": 698, "tipo": "alta"},
    "Alta-20": {"x": 841, "y": 724, "tipo": "alta"}
}

# --- 5. RECUPERO PRENOTAZIONI DAL DATABASE ---
prenotazioni_giorno = {}
risposta_p = supabase.table("prenotazioni").select("posto_id, utenti(username, targa)").eq("data", data_str).execute()

if risposta_p.data:
    for p in risposta_p.data:
        p_id = p.get("posto_id")
        if p_id:
            info_u = p.get("utenti") or {}
            prenotazioni_giorno[p_id] = {
                "username": info_u.get("username", "Occupato"),
                "targa": info_u.get("targa", "-")
            }

# --- 6. RENDERIZZAZIONE GRAFICA MAPPA INTERATTIVA ---
img = Image.open("mappa.png")

# Prepariamo i punti da disegnare sulla mappa
is_admin = (username.lower() == "admin")
scelte_x, scelte_y, colori, testi, chiavi_posto = [], [], [], [], []

for codice_posto, coord in POSTI.items():
    chiavi_posto.append(codice_posto)
    scelte_x.append(coord["x"])
    scelte_y.append(coord["y"])
    
    if codice_posto in prenotazioni_giorno:
        colori.append("red") # Occupato
        if is_admin:
            testi.append(f"⛔ {codice_posto}<br>Occupato da: {prenotazioni_giorno[codice_posto]['username']}<br>Targa: {prenotazioni_giorno[codice_posto]['targa']}")
        else:
            testi.append(f"⛔ {codice_posto} (Occupato)")
    else:
        colori.append("green") # Libero
        testi.append(f"🟢 {codice_posto} (Libero - Clicca per prenotare)")

# Creiamo l'oggetto grafico mappa con Plotly go
fig = go.Figure()
fig.add_trace(go.Image(z=img))

fig.add_trace(go.Scatter(
    x=scelte_x, y=scelte_y,
    mode="markers",
    marker=dict(size=18, color=colori, line=dict(width=2, color="white")),
    text=testi,
    hoverinfo="text",
    customdata=chiavi_posto
))

fig.update_layout(
    margin=dict(l=0, r=0, t=0, b=0),
    xaxis=dict(visible=False),
    yaxis=dict(visible=False),
    clickmode="event+select"
)

# Mostriamo la mappa a schermo largo
st.subheader(f"Situazione Parcheggi per il giorno: {data_str}")
config = {'displayModeBar': False}
click_data = st.plotly_chart(fig, use_container_width=True, on_select="rerun", config=config)

# --- 7. LOGICA DI PRENOTAZIONE AL CLICK ---
if not is_admin:
    # Controlliamo se l'utente ha già una prenotazione in questo giorno
    ha_gia_prenotato = supabase.table("prenotazioni").select("id, posto_id").eq("utente_id", utente_loggato["id"]).eq("data", data_str).execute()
    
    if ha_gia_prenotato.data:
        posto_occupato_ora = ha_gia_prenotato.data[0]["posto_id"]
        st.warning(f"🏷️ Hai già riservato il posto **{posto_occupato_ora}** per oggi.")
        if st.button("Cancella la mia prenotazione ❌", use_container_width=True):
            supabase.table("prenotazioni").delete().eq("id", ha_gia_prenotato.data[0]["id"]).execute()
            st.success("Prenotazione cancellata!")
            st.rerun()
    else:
        st.info("💡 **Come prenotare:** Passa il mouse sopra i cerchietti della mappa e **fai click su un pallino VERDE** per scegliere il tuo posto.")
        
        # Se l'utente clicca su un punto della mappa
        if click_data and "selection" in click_data and click_data["selection"]["points"]:
            punto_cliccato = click_data["selection"]["points"][0]
            indice_punto = punto_cliccato["pointNumber"]
            
            # Recuperiamo il nome del posto corrispondente al pallino cliccato
            if indice_punto < len(chiavi_posto):
                posto_scelto = chiavi_posto[indice_punto]
                
                # Controllo di sicurezza dell'ultimo secondo se il posto è libero
                if posto_scelto not in prenotazioni_giorno:
                    st.success(f"Hai selezionato il posto: **{posto_scelto}**")
                    if st.button(f"Conferma Prenotazione Posto {posto_scelto} 🟢", use_container_width=True):
                        supabase.table("prenotazioni").insert({
                            "utente_id": utente_loggato["id"],
                            "data": data_str,
                            "posto_id": posto_scelto
                        }).execute()
                        st.success(f"Posto {posto_scelto} prenotato correttamente!")
                        st.rerun()
                else:
                    st.error("Questo posto è stato appena occupato. Scegline un altro verde.")
else:
    # Vista Admin: Riepilogo Testuale aggiuntivo sotto la mappa
    st.divider()
    st.subheader("📋 Riepilogo rapido admin")
    if prenotazioni_giorno:
        for p_id, info in prenotazioni_giorno.items():
            st.write(f"🚗 Posto **{p_id}** -> Occupato da **{info['username']}** (Targa: {info['targa']})")
    else:
        st.info("Nessun posto occupato in questa data.")
