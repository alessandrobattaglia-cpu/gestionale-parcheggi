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
is_admin = (username.lower() == "admin")

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

# --- 4. VALORI DI CALIBRAZIONE VALIDI E DEFINITIVI ---
scale_x = 1.22
scale_y = 0.98
offset_x = 15
offset_y = 0

# --- COORDINATE BASE DEI POSTI ---
POSTI = {
    "Bassa-1": {"x": 40, "y": 288},   "Bassa-2": {"x": 72, "y": 272},
    "Bassa-3": {"x": 105, "y": 257},  "Bassa-4": {"x": 145, "y": 238},
    "Bassa-5": {"x": 178, "y": 222},  "Bassa-6": {"x": 210, "y": 207},
    "Bassa-7": {"x": 243, "y": 192},  "Bassa-8": {"x": 276, "y": 176},
    "Bassa-9": {"x": 308, "y": 160},  "Bassa-10": {"x": 341, "y": 145},
    "Bassa-11": {"x": 374, "y": 129}, "Bassa-12": {"x": 407, "y": 113},
    "Bassa-13": {"x": 440, "y": 98},  "Bassa-14": {"x": 472, "y": 82},
    "Bassa-15": {"x": 505, "y": 66},

    "Piazzale-1": {"x": 458, "y": 150}, "Piazzale-2": {"x": 418, "y": 178},
    "Piazzale-3": {"x": 393, "y": 215}, "Piazzale-4": {"x": 370, "y": 255},
    "Piazzale-5": {"x": 348, "y": 296}, "Piazzale-6": {"x": 382, "y": 360},

    "Studenti-7": {"x": 515, "y": 420}, "Studenti-8": {"x": 490, "y": 502},
    "Studenti-9": {"x": 510, "y": 570}, "Studenti-10": {"x": 510, "y": 630},
    "Studenti-11": {"x": 510, "y": 690}, "Studenti-12": {"x": 510, "y": 750},
    "Studenti-13": {"x": 510, "y": 810}, "Studenti-14": {"x": 510, "y": 870},
    
    "Alloggi-13": {"x": 59.8, "y": 739.9}, 
    "Alloggi-12": {"x": 59.8, "y": 777.6}, 
    "Alloggi-11": {"x": 59.8, "y": 815.6}, 
    "Alloggi-10": {"x": 59.8, "y": 853.8}, 
    "Alloggi-9":  {"x": 59.8, "y": 890.5}, 
    "Alloggi-8":  {"x": 59.8, "y": 927.6}, 
    "Alloggi-7":  {"x": 59.8, "y": 965.8}, 
    "Alloggi-6":  {"x": 59.8, "y": 1004.8},

    "Alloggi-5": {"x": 196.6, "y": 982.0}, 
    "Alloggi-4": {"x": 251.6, "y": 982.0}, 
    "Alloggi-3": {"x": 306.4, "y": 982.0}, 
    "Alloggi-2": {"x": 361.9, "y": 982.0}, 
    "Alloggi-1": {"x": 415.5, "y": 982.0},
    
    "Alta-1": {"x": 845, "y": 502}, "Alta-2": {"x": 845, "y": 537},
    "Alta-3": {"x": 845, "y": 572}, "Alta-4": {"x": 845, "y": 607},
    "Alta-5": {"x": 845, "y": 642}, "Alta-6": {"x": 845, "y": 677},
    "Alta-7": {"x": 845, "y": 712},
    
    "Alta-8":  {"x": 1065, "y": 456}, "Alta-9":  {"x": 1065, "y": 492},
    "Alta-10": {"x": 1065, "y": 528}, "Alta-11": {"x": 1065, "y": 564},
    "Alta-12": {"x": 1065, "y": 600}, "Alta-13": {"x": 1065, "y": 636},
    "Alta-14": {"x": 1065, "y": 672}, "Alta-15": {"x": 1065, "y": 708},
    "Alta-16": {"x": 1065, "y": 744}, "Alta-17": {"x": 1065, "y": 780},
    "Alta-18": {"x": 1065, "y": 816}, "Alta-19": {"x": 1065, "y": 852},
    "Alta-20": {"x": 1065, "y": 888}
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

# --- 6. RENDERIZZAZIONE MAPPA E APPLICAZIONE CALIBRAZIONE ---
img = Image.open("mappa.png")

scelte_x, choices_y, colori, testi, chiavi_posto = [], [], [], [], []

for codice_posto, coord in POSTI.items():
    chiavi_posto.append(codice_posto)
    
    x_calibrato = (coord["x"] * scale_x) + offset_x
    y_calibrato = (coord["y"] * scale_y) + offset_y
    
    scelte_x.append(x_calibrato)
    choices_y.append(y_calibrato)
    
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
    x=scelte_x, y=choices_y,
    mode="markers",
    marker=dict(size=14, color=colori, line=dict(width=1.5, color="white")),
    text=testi,
    hoverinfo="text",
    customdata=chiavi_posto
))

fig.update_xaxes(range=[0, img.width], showgrid=False, zeroline=False, visible=False, constrain="domain")
fig.update_yaxes(range=[img.height, 0], showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1)

# Ottimizzazione altezza: impostiamo 850 pixel fissi per dare spazio all'immagine di respirare ed essere nitida
fig.update_layout(
    height=850, 
    margin=dict(l=0, r=0, t=0, b=0), 
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
