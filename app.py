import streamlit as st
import datetime
from datetime import date
from supabase import create_client, Client
import pandas as pd
import io
import json
import base64
import streamlit.components.v1 as components

# --- 1. CONNESSIONE AL DATABASE ---
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- CONFIGURAZIONE RESTRIZIONI GRUPPI STUDENTI ---
RESTRIZIONI_GRUPPI = {
    "Marketing 1":    {"giorni_consentiti": [0, 1, 2], "max_posti": 5},
    "Marketing 2":    {"giorni_consentiti": [0, 1, 2], "max_posti": 5},
    "Agro 1":         {"giorni_consentiti": [2, 3, 4], "max_posti": 4},
    "Agro 2":         {"giorni_consentiti": [2, 3, 4], "max_posti": 4},
    "Food 1":         {"giorni_consentiti": [0, 1, 4], "max_posti": 3},
    "Food 2":         {"giorni_consentiti": [0, 1, 4], "max_posti": 3},
    "Zootecnia 1":    {"giorni_consentiti": [1, 2, 3], "max_posti": 4},
    "Zootecnia 2":    {"giorni_consentiti": [1, 2, 3], "max_posti": 4},
    "Viticoltura 1":  {"giorni_consentiti": [0, 3, 4], "max_posti": 3},
    "Viticoltura 2":  {"giorni_consentiti": [0, 3, 4], "max_posti": 3},
}

# --- 2. CONFIGURAZIONE INTERFACCIA ---
st.set_page_config(page_title="Parcheggi Symposium", page_icon="🚗", layout="wide")
st.title("🚗 Parcheggi Symposium - Gestione Assegnazioni")

if "utente_autenticato" not in st.session_state:
    st.session_state["utente_autenticato"] = None

# --- 3. LOGIN ---
if st.session_state["utente_autenticato"] is None:
    st.subheader("🔑 Accesso Riservato")
    with st.form("form_login"):
        username_inserito = st.text_input("Username:")
        password_inserita = st.text_input("Password:", type="password")
        if st.form_submit_button("Accedi 🔓", use_container_width=True):
            if username_inserito and password_inserita:
                risposta = supabase.table("utenti").select("id, username, targa, gruppo").eq("username", username_inserito).eq("password", password_inserita).execute()
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
gruppo_utente = utente_loggato.get("gruppo", "Marketing 1")
targa_utente = utente_loggato.get("targa", "")
is_admin = (username.lower() == "admin")

# --- SIDEBAR DI CONTROLLO & GESTIONE TARGA ---
st.sidebar.header("👤 Account")
st.sidebar.write(f"Utente: **{username}**")
st.sidebar.write(f"Gruppo: **{gruppo_utente}**")
st.sidebar.write(f"Targa attuale: **{targa_utente if targa_utente else 'Non impostata'}**")

# Modifica Targa Personale
with st.sidebar.expander("✏️ Modifica la tua Targa"):
    nuova_targa = st.text_input("Nuova Targa:", value=targa_utente, key="input_targa")
    if st.button("Salva Targa 💾", use_container_width=True):
        if nuova_targa.strip():
            supabase.table("utenti").update({"targa": nuova_targa.strip().upper()}).eq("id", utente_loggato["id"]).execute()
            st.session_state["utente_autenticato"]["targa"] = nuova_targa.strip().upper()
            st.success("Targa aggiornata!")
            st.rerun()
        else:
            st.warning("Inserisci una targa valida.")

st.sidebar.divider()
st.sidebar.subheader("📅 Seleziona il Giorno")
oggi = date.today()

# Finestra prenotazioni 2 settimane per studenti/alloggi
gruppi_con_finestra = list(RESTRIZIONI_GRUPPI.keys()) + ["Alloggi"]

if gruppo_utente in gruppi_con_finestra and not is_admin:
    max_data = oggi + datetime.timedelta(days=14)
else:
    max_data = oggi + datetime.timedelta(days=365)

data_scelta = st.sidebar.date_input("Vedi prenotazioni del:", min_value=oggi, max_value=max_data, format="DD/MM/YYYY")
data_str = data_scelta.strftime("%Y-%m-%d")
data_visiva = data_scelta.strftime("%d/%m/%Y")

if st.sidebar.button("Log out ❌", use_container_width=True):
    st.session_state["utente_autenticato"] = None
    st.rerun()

# Auto-cancellazione dati vecchi (3 giorni fa)
try:
    data_limite = oggi - datetime.timedelta(days=3)
    supabase.table("prenotazioni").delete().lt("data", data_limite.strftime("%Y-%m-%d")).execute()
except Exception:
    pass

# --- 4. LISTA CHIAVI POSTI ---
POSTI = {
    # Zona Verde Chiaro (Studenti / Generici)
    **{f"Bassa-{i}": {} for i in range(1, 16)},
    **{f"Alta-{i}": {} for i in range(1, 21)},
    **{f"Piazzale-{i}": {} for i in range(1, 20)},
    
    # Zona Staff (22 Posti)
    **{f"Staff-{i}": {} for i in range(1, 23)},
    
    # Zona Docenti (5 Posti)
    **{f"Docenti-{i}": {} for i in range(1, 6)},
    
    # Zona Alloggi (11 Posti)
    **{f"Alloggi-{i}": {} for i in range(1, 12)}
}

# --- 5. RECUPERO PRENOTAZIONI DEL GIORNO + PERMANENTI STAFF ---
prenotazioni_giorno = {}

# 1. Recupera prenotazioni ordinarie
risposta_p = supabase.table("prenotazioni").select("id, posto_id, utente_id, utenti(username, targa, gruppo)").eq("data", data_str).execute()

if risposta_p.data:
    for p in risposta_p.data:
        p_id = p.get("posto_id")
        if p_id:
            info_u = p.get("utenti") or {}
            prenotazioni_giorno[p_id] = {
                "id_prenotazione": p.get("id"),
                "utente_id": p.get("utente_id"),
                "username": info_u.get("username", "Occupato"),
                "targa": info_u.get("targa", "-"),
                "gruppo": info_u.get("gruppo", ""),
                "tipo": "giornaliera"
            }

# 2. Recupera eventuali prenotazioni permanenti (fissee per Staff/Docenti)
risposta_perm = supabase.table("prenotazioni").select("id, posto_id, utente_id, utenti(username, targa, gruppo)").eq("data", "PERMANENTE").execute()
if risposta_perm.data:
    for p in risposta_perm.data:
        p_id = p.get("posto_id")
        if p_id and p_id not in prenotazioni_giorno:
            info_u = p.get("utenti") or {}
            prenotazioni_giorno[p_id] = {
                "id_prenotazione": p.get("id"),
                "utente_id": p.get("utente_id"),
                "username": info_u.get("username", "Occupato"),
                "targa": info_u.get("targa", "-"),
                "gruppo": info_u.get("gruppo", ""),
                "tipo": "permanente"
            }

# --- 6. RENDERING MAPPA INTERATTIVA HTML ---
st.subheader(f"🗺️ Mappa Parcheggi Interattiva - Giorno: {data_visiva}")

stato_posti_json = json.dumps(prenotazioni_giorno)

def get_base64_image(image_path):
    try:
        with open(image_path, "rb") as img_file:
            encoded = base64.b64encode(img_file.read()).decode()
            return f"data:image/png;base64,{encoded}"
    except FileNotFoundError:
        st.warning(f"Immagine '{image_path}' non trovata nella cartella.")
        return ""

bg_image_base64 = get_base64_image("Screenshot 2026-09-30 alle 14.20.10.png")

try:
    with open("mappa.html", "r", encoding="utf-8") as f:
        html_raw = f.read()
    
    html_ready = html_raw.replace("ST_PRENOTAZIONI_JSON_PLACEHOLDER", stato_posti_json)
    html_ready = html_ready.replace("ST_BACKGROUND_IMAGE_PLACEHOLDER", bg_image_base64)
    
    components.html(html_ready, height=800, scrolling=True)
except FileNotFoundError:
    st.error("⚠️ ERRORE: File 'mappa.html' non trovato.")
except Exception as e:
    st.error(f"⚠️️ Impossibile caricare la mappa: {e}")

# --- 7. LOGICA PRENOTAZIONE E ASSEGNAZIONE ---
st.divider()

if not is_admin:
    # Controlla se l'utente ha già una prenotazione per questo giorno o permanente
    ha_gia_prenotato = supabase.table("prenotazioni").select("id, posto_id, data").eq("utente_id", utente_loggato["id"]).in_("data", [data_str, "PERMANENTE"]).execute()
    
    if ha_gia_prenotato.data:
        p_info = ha_gia_prenotato.data[0]
        tipo_str = "Permanente" if p_info["data"] == "PERMANENTE" else f"per il giorno {data_visiva}"
        st.warning(f"🏷️ Hai già assegnato il **Posto: {p_info['posto_id']}** ({tipo_str}).")
        if st.button("Cancella la mia prenotazione ❌", use_container_width=True):
            supabase.table("prenotazioni").delete().eq("id", p_info["id"]).execute()
            st.success("Prenotazione annullata!")
            st.rerun()
            
    else:
        st.subheader("📌 Prenota il tuo Posto Auto")

        # CASO 1: DOCENTI (5 Posti dedicati)
        if gruppo_utente == "Docenti":
            posti_docenti_liberi = [p for p in POSTI.keys() if p.startswith("Docenti-") and p not in prenotazioni_giorno]
            if posti_docenti_liberi:
                posto_scelto = st.selectbox("Seleziona un Posto Docenti libero:", ["-- Seleziona --"] + posti_docenti_liberi)
                if posto_scelto != "-- Seleziona --":
                    if st.button(f"Conferma Prenotazione {posto_scelto} 🟢", use_container_width=True):
                        supabase.table("prenotazioni").insert({"utente_id": utente_loggato["id"], "data": data_str, "posto_id": posto_scelto}).execute()
                        st.success(f"Posto {posto_scelto} prenotato!")
                        st.rerun()
            else:
                st.error("❌ Nessun Posto Docenti libero per questa data.")

        # CASO 2: STAFF (22 Posti con opzione Assegnazione Permanente)
        elif gruppo_utente == "Staff":
            st.info("ℹ️ Come membro dello Staff puoi scegliere una prenotazione giornaliera oppure un'assegnazione fissa/permanente.")
            posti_staff_liberi = [p for p in POSTI.keys() if p.startswith("Staff-") and p not in prenotazioni_giorno]
            
            if posti_staff_liberi:
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    posto_scelto_staff = st.selectbox("Seleziona Posto Staff:", ["-- Seleziona --"] + posti_staff_liberi)
                with col_s2:
                    tipo_prenotazione = st.radio("Tipo Assegnazione:", ["Giornaliera (Solo per il giorno selezionato)", "Fissa Permanente (Sempre occupato per te)"])
                
                if posto_scelto_staff != "-- Seleziona --":
                    if st.button(f"Conferma Assegnazione {posto_scelto_staff} 🟢", use_container_width=True):
                        data_salvataggio = "PERMANENTE" if "Permanente" in tipo_prenotazione else data_str
                        supabase.table("prenotazioni").insert({"utente_id": utente_loggato["id"], "data": data_salvataggio, "posto_id": posto_scelto_staff}).execute()
                        st.success(f"Posto {posto_scelto_staff} assegnato con successo!")
                        st.rerun()
            else:
                st.error("❌ Nessun Posto Staff libero disponibile.")

        # CASO 3: ALLOGGI (11 Posti)
        elif gruppo_utente == "Alloggi":
            st.info("ℹ️ Ti verrà assegnato automaticamente un posto nella zona Alloggi.")
            if st.button("Richiedi Assegnazione Posto Alloggi 🚗", use_container_width=True):
                posti_alloggi = [k for k in POSTI.keys() if k.startswith("Alloggi-")]
                posto_trovato = next((p for p in posti_alloggi if p not in prenotazioni_giorno), None)
                
                if posto_trovato:
                    supabase.table("prenotazioni").insert({"utente_id": utente_loggato["id"], "data": data_str, "posto_id": posto_trovato}).execute()
                    st.success(f"🎉 Ti è stato assegnato il **Posto {posto_trovato}**!")
                    st.rerun()
                else:
                    st.error("❌ Tutti i posti Alloggi sono esauriti per oggi.")

        # CASO 4: STUDENTI (Zona Verde Chiaro: Bassa, Alta, Piazzale)
        else:
            if gruppo_utente in RESTRIZIONI_GRUPPI:
                restrizione = RESTRIZIONI_GRUPPI[gruppo_utente]
                giorno_settimana = data_scelta.weekday()
                nomi_giorni = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
                
                if giorno_settimana not in restrizione["giorni_consentiti"]:
                    giorni_ok = ", ".join([nomi_giorni[g] for g in restrizione["giorni_consentiti"]])
                    st.error(f"❌ Il gruppo **{gruppo_utente}** non può prenotare di {nomi_giorni[giorno_settimana]}. Giorni consentiti: **{giorni_ok}**")
                    st.stop()
                
                posti_occupati_dal_gruppo = sum(1 for info in prenotazioni_giorno.values() if info["gruppo"] == gruppo_utente)
                if posti_occupati_dal_gruppo >= restrizione["max_posti"]:
                    st.error(f"❌ Limite raggiunto! Il tuo gruppo (**{gruppo_utente}**) ha esaurito la quota massima di **{restrizione['max_posti']}** posti per oggi.")
                    st.stop()
            
            st.info(f"ℹ️ Come studente del gruppo **{gruppo_utente}**, ti verrà assegnato un posto nelle zone verdi (Bassa, Alta o Piazzale).")
            if st.button("Prenota Posto Auto Studenti 🚗", use_container_width=True):
                posti_studenti = [k for k in POSTI.keys() if k.startswith("Bassa-") or k.startswith("Alta-") or k.startswith("Piazzale-")]
                posto_trovato = next((p for p in posti_studenti if p not in prenotazioni_giorno), None)
                
                if posto_trovato:
                    supabase.table("prenotazioni").insert({"utente_id": utente_loggato["id"], "data": data_str, "posto_id": posto_trovato}).execute()
                    st.success(f"🎉 Ti è stato assegnato il **Posto {posto_trovato}**!")
                    st.rerun()
                else:
                    st.error("❌ Posti auto esauriti nelle zone verdi per questa data.")

# --- PANNELLO AMMINISTRATORE ---
else:
    st.divider()
    st.subheader("🛠️ Pannello Amministrazione Parcheggi")
    
    colA, colB = st.columns(2)
    with colA:
        posto_admin = st.selectbox("Seleziona un Posto da gestire:", ["-- Seleziona --"] + list(POSTI.keys()))
        
    with colB:
        if posto_admin != "-- Seleziona --":
            if posto_admin not in prenotazioni_giorno:
                st.success(f"Il **Posto {posto_admin}** è LIBERO.")
                if st.button(f"Blocca/Rendi NON DISPONIBILE il Posto {posto_admin} ⛔", use_container_width=True):
                    supabase.table("prenotazioni").insert({"utente_id": utente_loggato["id"], "data": data_str, "posto_id": posto_admin}).execute()
                    st.success("Posto bloccato!")
                    st.rerun()
            else:
                info_p = prenotazioni_giorno[posto_admin]
                nome_occ = info_p["username"]
                
                if nome_occ.lower() == "admin":
                    st.warning(f"Il **Posto {posto_admin}** è bloccato dall'Admin.")
                    if st.button(f"Sblocca Posto {posto_admin} 🔓", use_container_width=True):
                        supabase.table("prenotazioni").delete().eq("id", info_p["id_prenotazione"]).execute()
                        st.success("Posto sbloccato!")
                        st.rerun()
                else:
                    st.error(f"Occupato da: **{nome_occ}** ({info_p['gruppo']})")
                    if st.button(f"Cancella prenotazione di {nome_occ} 🗑️", use_container_width=True):
                        supabase.table("prenotazioni").delete().eq("id", info_p["id_prenotazione"]).execute()
                        st.success("Prenotazione rimossa!")
                        st.rerun()

    st.divider()
    st.subheader("📋 Esporta Report Excel")
    risposta_t = supabase.table("prenotazioni").select("data, posto_id, utenti(username, targa, gruppo)").execute()
    
    if risposta_t.data:
        lista_excel = []
        for item in risposta_t.data:
            u_info = item.get("utenti") or {}
            p_data_raw = item.get("data")
            p_user = u_info.get("username", "Occupato")
            
            lista_excel.append({
                "Data": "PERMANENTE" if p_data_raw == "PERMANENTE" else p_data_raw,
                "Posto": item.get("posto_id"),
                "Utente": "BLOCCATO (Admin)" if p_user.lower() == 'admin' else p_user,
                "Gruppo": u_info.get("gruppo", "-") if p_user.lower() != 'admin' else "-",
                "Targa": u_info.get("targa", "-") if p_user.lower() != 'admin' else "-"
            })
        
        df_excel = pd.DataFrame(lista_excel)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_excel.to_excel(writer, index=False, sheet_name='Prenotazioni')
        buffer.seek(0)
        
        st.download_button(
            label="📥 Scarica tutte le prenotazioni in Excel (.xlsx)",
            data=buffer,
            file_name=f"report_parcheggi_{date.today().strftime('%d_%m_%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
