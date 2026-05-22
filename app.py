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
            else:
                st.warning("Compila entrambi i campi.")
    st.stop()

utente_loggato = st.session_state["utente_autenticato"]
username = utente_loggato["username"]

# Sidebar di controllo
st.sidebar.header("👤 Account")
st.sidebar.write(f"Utente: **{username}**")

st.sidebar.divider()
st.sidebar.subheader("📅 Seleziona il Giorno")
oggi = date.today()
data_scelta = st.sidebar.date_input("Vedi prenotazioni del:", min_value=oggi)
data_str = data_scelta.strftime("%Y-%m-%d")

if st.sidebar.button("Log out ❌"):
    st.session_state["utente_autenticato"] = None
    st.rerun()

# --- 4. DATABASE COORDINATE DI TUTTI I POSTI (Docenti Esclusi) ---
POSTI = {
    # ZONA BASSA (Viola inclinato in alto - Calcolati lungo la diagonale)
    "Bassa-1": {"x": 35, "y": 235}, "Bassa-2": {"x": 67, "y": 218},
    "Bassa-3": {"x": 98, "y": 202}, "Bassa-4": {"x": 133, "y": 185},
    "Bassa-5": {"x": 164, "y": 170}, "Bassa-6": {"x": 195, "y": 155},
    "Bassa-7": {"x": 226, "y": 139}, "Bassa-8": {"x": 257, "y": 124},
    "Bassa-9": {"x": 288, "y": 109}, "Bassa-10": {"x": 319, "y": 94},
    "Bassa-11": {"x": 350, "y": 79}, "Bassa-12": {"x": 381, "y": 64},
    "Bassa-13": {"x": 412, "y": 49}, "Bassa-14": {"x": 444, "y": 34},
    "Bassa-15": {"x": 475, "y": 19},

    # INGRESSO PIAZZALE (Azzurri inclinati alti)
    "Piazzale-1": {"x": 450, "y": 113}, "Piazzale-2": {"x": 420, "y": 140},
    "Piazzale-3": {"x": 395, "y": 175}, "Piazzale-4": {"x": 372, "y": 215},
    "Piazzale-5": {"x": 350, "y": 255}, "Piazzale-6": {"x": 328, "y": 298},

    # ZONA CENTRALE STUDENTI (Azzurro verticale basso)
    "Studenti-7": {"x": 472, "y": 355},
    "Studenti-8": {"x": 445, "y": 425},
    "Studenti-9": {"x": 445, "y": 485},
    "Studenti-10": {"x": 445, "y": 530},
    "Studenti-11": {"x": 445, "y": 575},
    "Studenti-12": {"x": 445, "y": 622},
    "Studenti-13": {"x": 445, "y": 668},
    "Studenti-14": {"x": 445, "y": 715},
    
    # ZONA CENTRALE ALLOGGI (Verde colonna sinistra - Esclusi i primi Docenti)
    "Alloggi-6": {"x": 58, "y": 810}, "Alloggi-7": {"x": 58, "y": 768},
    "Alloggi-8": {"x": 58, "y": 725}, "Alloggi-9": {"x": 58, "y": 682},
    "Alloggi-10": {"x": 58, "y": 640}, "Alloggi-11": {"x": 58, "y": 598},
    "Alloggi-12": {"x": 58, "y": 555}, "Alloggi-13": {"x": 58, "y": 512},

    # ZONA CENTRALE ALLOGGI (Verde riga orizzontale in basso)
    "Alloggi-5": {"x": 182, "y": 828}, "Alloggi-4": {"x": 228, "y": 828},
    "Alloggi-3": {"x": 275, "y": 828}, "Alloggi-2": {"x": 322, "y": 828},
    "Alloggi-1": {"x": 369, "y": 828},
    
    # ZONA ALTA (Arancione a destra - Colonna 1)
    "Alta-1": {"x": 742, "y": 412}, "Alta-2": {"x": 742, "y": 440},
    "Alta-3": {"x": 742, "y": 468}, "Alta-4": {"x": 742, "y": 496},
    "Alta-5": {"x": 742, "y": 524}, "Alta-6": {"x": 742, "y": 552},
    "Alta-7": {"x": 742, "y": 580},
    
    # ZONA ALTA (Arancione a destra - Colonna 2)
    "Alta-8": {"x": 940, "y": 382}, "Alta-9": {"x": 940, "y": 408},
    "Alta-10": {"x": 940, "y": 434}, "Alta-11": {"x": 940, "y": 460},
    "Alta-12": {"x": 940, "y": 486}, "Alta-13": {"x": 940, "y": 512},
    "Alta-14": {"x": 940, "y": 538}, "Alta-15": {"x": 940, "y": 564},
    "Alta-16": {"x": 940, "y": 590}, "Alta-17": {"x": 940, "y": 616},
    "Alta-18": {"x": 940, "y": 642}, "Alta-19": {"x": 940, "y": 668},
    "Alta-20": {"x": 940, "y": 694}
}

# --- 5. RECUPERO PRENOTAZIONI ---
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

# --- 6. RENDERIZZAZIONE GRAFICA MAPPA ---
img = Image.open("mappa.png")

is_admin = (username.lower() == "admin")
scelte_x, scelte_y, colori, testi, chiavi_posto = [], [], [], [], []

for codice_posto, coord in POSTI.items():
    chiavi_posto.append(codice_posto)
    scelte_x.append(coord["x"])
    scelte_y.append(coord["y"])
    
    if codice_posto in prenotazioni_giorno:
        colori.append("red")
        if is_admin:
            testi.append(f"⛔ {codice_posto}<br>Occupato da: {prenotazioni_giorno[codice_posto]['username']}<br>Targa: {prenotazioni_giorno[codice_posto]['targa']}")
        else:
            testi.append(f"⛔ {codice_posto} (Occupato)")
    else:
        colori.append("green")
        testi.append(f"🟢 {codice_posto} (Libero - Clicca per prenotare)")

fig = go.Figure()
fig.add_trace(go.Image(z=img))

fig.add_trace(go.Scatter(
    x=scelte_x, y=scelte_y,
    mode="markers",
    marker=dict(size=14, color=colori, line=dict(width=1.5, color="white")),
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

st.subheader(f"Situazione Parcheggi per il giorno: {data_str}")
config = {'displayModeBar': False}
click_data = st.plotly_chart(fig, use_container_width=True, on_select="rerun", config=config)

# --- 7. LOGICA PRENOTAZIONE ---
if not is_admin:
    ha_gia_prenotato = supabase.table("prenotazioni").select("id, posto_id").eq("utente_id", utente_loggato["id"]).eq("data", data_str).execute()
    
    if ha_gia_prenotato.data:
        posto_occupato_ora = ha_gia_prenotato.data[0]["posto_id"]
        st.warning(f"🏷️ Hai già riservato il posto **{posto_occupato_ora}** per oggi.")
        if st.button("Cancella la mia prenotazione ❌", use_container_width=True):
            supabase.table("prenotazioni").delete().eq("id", ha_gia_prenotato.data[0]["id"]).execute()
            st.success("Prenotazione cancellata!")
            st.rerun()
    else:
        st.info("💡 **Come prenotare:** Fai click su un pallino **VERDE** direttamente sulla mappa per scegliere il tuo posto.")
        
        if click_data and "selection" in click_data and click_data["selection"]["points"]:
            punto_cliccato = click_data["selection"]["points"][0]
            indice_punto = punto_cliccato["pointNumber"]
            
            if indice_punto < len(chiavi_posto):
                posto_scelto = chiavi_posto[indice_punto]
                
                if posto_scelto not in prenotazioni_giorno:
                    st.success(f"Hai selezionato il posto: **{posto_scelto}**")
                    if st.button(f"Conferma Prenotazione Posto {posto_scelto} 🟢", use_container_width=True):
                        supabase.table("prenotazioni").insert({
                            "utente_id": utente_loggato["id"],
                            "data": data_str,
                            "posto_id": posto_scelto
                        }).execute()
                        st.success(f"Posto {posto_scelto} prenotato!")
                        st.rerun()
                else:
                    st.error("Questo posto è stato appena occupato. Scegline un altro verde.")
else:
    st.divider()
    st.subheader("📋 Riepilogo rapido admin")
    if prenotazioni_giorno:
        for p_id, info in prenotazioni_giorno.items():
            st.write(f"🚗 Posto **{p_id}** -> Occupato da **{info['username']}** (Targa: {info['targa']})")
    else:
        st.info("Nessun posto occupato in questa data.")
