import streamlit as st
from datetime import date
from supabase import create_client, Client
import plotly.express as px
from PIL import Image
import os

# --- 1. CONNESSIONE AL DATABASE ---
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- 2. CONFIGURAZIONE INTERFACCIA WEB ---
st.set_page_config(page_title="Parcheggi Symposium", page_icon="🚗", layout="wide") # Layout wide per vedere bene la mappa
st.title("🚗 Parcheggi Symposium")

# Stato della sessione per il login
if "utente_autenticato" not in st.session_state:
    st.session_state["utente_autenticato"] = None

# --- 3. SCHERMATA DI LOGIN ---
if st.session_state["utente_autenticato"] is None:
    st.subheader("🔑 Accesso Riservato")
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

# Dati utente loggato
utente_loggato = st.session_state["utente_autenticato"]
username = utente_loggato["username"]

# Sidebar
st.sidebar.header("👤 Account")
st.sidebar.write(f"Loggato come: **{username}**")
if st.sidebar.button("Log out ❌"):
    st.session_state["utente_autenticato"] = None
    st.rerun()

st.divider()

# --- 4. CONFIGURAZIONE PRELIMINARE MAPPA ---
# Verifichiamo che il file mappa.png esista nella cartella su GitHub
if not os.path.exists("mappa.png"):
    st.error("⚠️ Errore: Non trovo il file 'mappa.png' su GitHub. Assicurati di averlo caricato con il nome esatto.")
    st.stop()

img = Image.open("mappa.png")
larghezza, altezza = img.size

# --- 5. STRUMENTO TEMPORANEO DI CALIBRAZIONE COORDINATE ---
st.subheader("🛠️ Strumento Calibrazione Mappa (Sviluppatore)")
st.write("Clicca su un punto qualsiasi della mappa per scoprire le sue coordinate X e Y. Ti serviranno per posizionare i pallini dei parcheggi.")

# Creiamo il grafico interattivo di sfondo con Plotly
fig = px.imshow(img)
fig.update_layout(
    dragmode="drawcircle", 
    margin=dict(l=0, r=0, t=0, b=0),
    xaxis=dict(showgrid=False, zeroline=False, visible=False),
    yaxis=dict(showgrid=False, zeroline=False, visible=False)
)

# Mostriamo la mappa e catturiamo il click dell'utente
config = {'displayModeBar': False}
event_data = st.plotly_chart(fig, use_container_width=True, on_select="rerun", config=config)

# Se l'utente clicca sulla mappa, Streamlit legge il punto
if event_data and "selection" in event_data and event_data["selection"]["points"]:
    punto = event_data["selection"]["points"][0]
    click_x = punto["x"]
    click_y = punto["y"]
    st.success(f"📌 **Punto rilevato!** Copia questi numeri per questo posto: **X = {click_x}**, **Y = {click_y}**")
else:
    st.info("Fai click su un quadratino della mappa per vedere le sue coordinate apparire qui.")
