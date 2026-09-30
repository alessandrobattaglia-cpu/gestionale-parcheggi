import streamlit as st
import datetime
from datetime import date
from supabase import create_client, Client
import pandas as pd
import io
import json
import streamlit.components.v1 as components

# --- 1. CONNESSIONE AL DATABASE ---
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- CONFIGURAZIONE RESTRIZIONI GRUPPI ---
RESTRIZIONI_GRUPPI = {
    "Marketing 1":   {"giorni_consentiti": [0, 1, 2], "max_posti": 5},
    "Marketing 2":   {"giorni_consentiti": [0, 1, 2], "max_posti": 5},
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
is_admin = (username.lower() == "admin")

# Sidebar di controllo standard
st.sidebar.header("👤 Account")
st.sidebar.write(f"Utente: **{username}**")
st.sidebar.write(f"Gruppo: **{gruppo_utente}**")

st.sidebar.divider()
st.sidebar.subheader("📅 Seleziona il Giorno")
oggi = date.today()

# --- CONTROLLO FINESTRA PRENOTAZIONI 2 SETTIMANE ---
gruppi_con_finestra = [
    "Alloggi", "Marketing 1", "Marketing 2", "Agro 1", "Agro 2", 
    "Food 1", "Food 2", "Zootecnia 1", "Zootecnia 2", "Viticoltura 1", "Viticoltura 2"
]

if gruppo_utente in gruppi_con_finestra and not is_admin:
    max_data = oggi + datetime.timedelta(days=14)
else:
    max_data = oggi + datetime.timedelta(days=365)

data_scelta = st.sidebar.date_input("Vedi prenotazioni del:", min_value=oggi, max_value=max_data, format="DD/MM/YYYY")
data_str = data_scelta.strftime("%Y-%m-%d")         # Formato per il database Supabase
data_visiva = data_scelta.strftime("%d/%m/%Y")      # Formato per la visualizzazione utente (Giorno/Mese/Anno)

if st.sidebar.button("Log out ❌", use_container_width=True):
    st.session_state["utente_autenticato"] = None
    st.rerun()

# --- AUTO-ANNULLAMENTO DOPO 3 GIORNI ---
try:
    # Calcola la data limite (3 giorni fa rispetto a oggi)
    data_limite = oggi - datetime.timedelta(days=3)
    # Cancella solo le prenotazioni antecedenti a 'data_limite'
    supabase.table("prenotazioni").delete().lt("data", data_limite.strftime("%Y-%m-%d")).execute()
except Exception:
    pass

# --- 4. LISTA CHIAVI POSTI (Serve per validazioni interne e tendine) ---
POSTI = {
    "Bassa-1": {}, "Bassa-2": {}, "Bassa-3": {}, "Bassa-4": {}, "Bassa-5": {},
    "Bassa-6": {}, "Bassa-7": {}, "Bassa-8": {}, "Bassa-9": {}, "Bassa-10": {},
    "Bassa-11": {}, "Bassa-12": {}, "Bassa-13": {}, "Bassa-14": {}, "Bassa-15": {},
    "Piazzale-1": {}, "Piazzale-2": {}, "Piazzale-3": {}, "Piazzale-4": {},
    "Piazzale-5": {}, "Piazzale-6": {},
    "Studenti-1": {}, "Studenti-2": {}, "Studenti-3": {}, "Studenti-4": {},
    "Studenti-5": {}, "Studenti-6": {}, "Studenti-7": {}, "Studenti-8": {},
    "Studenti-9": {}, "Studenti-10": {}, "Studenti-11": {}, "Studenti-12": {},
    "Studenti-13": {}, "Studenti-14": {}, 
    "Alloggi-13": {}, "Alloggi-12": {}, "Alloggi-11": {}, "Alloggi-10": {}, 
    "Alloggi-9": {}, "Alloggi-8": {}, "Alloggi-7": {}, "Alloggi-6": {},
    "Alloggi-5": {}, "Alloggi-4": {}, "Alloggi-3": {}, "Alloggi-2": {}, "Alloggi-1": {},
    "Alta-1": {}, "Alta-2": {}, "Alta-3": {}, "Alta-4": {}, "Alta-5": {},
    "Alta-6": {}, "Alta-7": {}, "Alta-8": {}, "Alta-9": {}, "Alta-10": {},
    "Alta-11": {}, "Alta-12": {}, "Alta-13": {}, "Alta-14": {}, "Alta-15": {},
    "Alta-16": {}, "Alta-17": {}, "Alta-18": {}, "Alta-19": {}, "Alta-20": {}
}

# --- 5. RECUPERO PRENOTAZIONI DEL GIORNO ---
prenotazioni_giorno = {}
risposta_p = supabase.table("prenotazioni").select("id, posto_id, utente_id, passeggeri, numero_persone, utenti(username, targa, gruppo)").eq("data", data_str).execute()

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
                "passeggeri": p.get("passeggeri") or "Nessuno",
                "numero_persone": p.get("numero_persone") or 1
            }

# --- 6. INIEZIONE DATI E DISEGNO MAPPA VETTORIALE HTML ---
st.subheader(f"🗺️ Mappa Parcheggi Interattiva - Giorno: {data_visiva}")

# Convertiamo il dizionario delle prenotazioni in formato JSON
stato_posti_json = json.dumps(prenotazioni_giorno)

# Carichiamo il file HTML e sostituiamo il segnaposto con i dati veri
try:
    with open("mappa.html", "r", encoding="utf-8") as f:
        html_raw = f.read()
    
    # Iniettiamo il JSON nel codice JavaScript della mappa
    html_ready = html_raw.replace("ST_PRENOTAZIONI_JSON_PLACEHOLDER", stato_posti_json)
    
    # Renderizziamo la mappa all'interno dell'app Streamlit
    components.html(html_ready, height=800, scrolling=True)
except FileNotFoundError:
    st.error("⚠️ ERRORE: File 'mappa.html' non trovato. Assicurati di aver creato il file nella stessa cartella di app.py.")
except Exception as e:
    st.error(f"⚠️ Impossibile caricare la mappa. Dettagli errore: {e}")

# --- 7. LOGICA ASSEGNAZIONE E PRENOTAZIONE ---
if not is_admin:
    ha_gia_prenotato = supabase.table("prenotazioni").select("id, posto_id").eq("utente_id", utente_loggato["id"]).eq("data", data_str).execute()
    
    if ha_gia_prenotato.data:
        posto_occupato_ora = ha_gia_prenotato.data[0]["posto_id"]
        st.warning(f"🏷️ Hai già riservato il posto: **{posto_occupato_ora}** per il giorno {data_visiva}.")
        if st.button("Cancella la mia prenotazione ❌", use_container_width=True):
            supabase.table("prenotazioni").delete().eq("id", ha_gia_prenotato.data[0]["id"]).execute()
            st.success("Prenotazione annullata con successo!")
            st.rerun()
            
    else:
        passeggeri_input = ""
        quanti_input = 1
        
        if gruppo_utente in gruppi_con_finestra:
            st.subheader("📝 Dettagli del Viaggio Obbligatori")
            col1, col2 = st.columns(2)
            with col1:
                passeggeri_input = st.text_input("Chi c'è in auto? (Scrivi Nome e Cognome dei presenti separati da virgola):", placeholder="es. Mario Rossi, Luca Bianchi")
            with col2:
                quanti_input = st.number_input("In quanti siete in auto in totale? (Compreso te alla guida)", min_value=1, max_value=9, value=1)

        # CASO A: IL PERSONALE
        if gruppo_utente == "Personale":
            st.info("💡 **Modalità Personale:** Seleziona un posto libero dal menu a tendina qui sotto.")
            posti_liberi = [p for p in POSTI.keys() if p not in prenotazioni_giorno]
            posto_scelto = st.selectbox("Seleziona uno stallo disponibile:", ["-- Seleziona --"] + posti_liberi)

            if posto_scelto != "-- Seleziona --":
                if st.button(f"Conferma Prenotazione Posto {posto_scelto} 🟢", use_container_width=True):
                    supabase.table("prenotazioni").insert({"utente_id": utente_loggato["id"], "data": data_str, "posto_id": posto_scelto}).execute()
                    st.success(f"Posto {posto_scelto} riservato!")
                    st.rerun()

        # CASO B: GLI ALLOGGI
        elif gruppo_utente == "Alloggi":
            st.info("ℹ️ I membri del gruppo Alloggi ricevono un posto automatico nella zona verde dedicata.")
            if st.button("Richiedi Assegnazione Posto Alloggi 🚗", use_container_width=True):
                if not passeggeri_input:
                    st.error("⚠️ Compila il campo 'Chi c'è in auto?' prima di procedere.")
                else:
                    posti_alloggi = [k for k in POSTI.keys() if k.startswith("Alloggi-")]
                    posto_trovato = None
                    for p in posti_alloggi:
                        if p not in prenotazioni_giorno:
                            posto_trovato = p
                            break
                    
                    if posto_trovato:
                        supabase.table("prenotazioni").insert({"utente_id": utente_loggato["id"], "data": data_str, "posto_id": posto_trovato, "passeggeri": passeggeri_input, "numero_persone": quanti_input}).execute()
                        st.success(f"🎉 Sistema: Ti è stato assegnato il posto **{posto_trovato}**!")
                        st.rerun()
                    else:
                        st.error("❌ Purtroppo tutti i posti Alloggi sono esauriti per questa data.")

        # CASO C: TUTTI GLI ALTRI GRUPPI
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
                    st.error(f"❌ Limite raggiunto! Il tuo gruppo (**{gruppo_utente}**) ha già esaurito la quota massima di **{restrizione['max_posti']}** parcheggi per oggi.")
                    st.stop()
            
            st.info(f"ℹ️ Come membro del gruppo **{gruppo_utente}**, il sistema ti assegnerà automaticamente un posto libero tra la Zona Studenti, Bassa o Alta.")
            if st.button("Richiedi Assegnazione Posto Auto 🚗", use_container_width=True):
                if not passeggeri_input:
                    st.error("⚠️ Compila il campo 'Chi c'è in auto?' prima di procedere.")
                else:
                    posti_comuni = [k for k in POSTI.keys() if not k.startswith("Alloggi-")]
                    posto_trovato = None
                    for p in posti_comuni:
                        if p not in prenotazioni_giorno:
                            posto_trovato = p
                            break
                    
                    if posto_trovato:
                        supabase.table("prenotazioni").insert({"utente_id": utente_loggato["id"], "data": data_str, "posto_id": posto_trovato, "passeggeri": passeggeri_input, "numero_persone": quanti_input}).execute()
                        st.success(f"🎉 Sistema: Ti è stato assegnato il posto **{posto_trovato}**!")
                        st.rerun()
                    else:
                        st.error("❌ Posti auto esauriti per oggi nelle zone Studenti/Bassa/Alta.")

# --- PANNELLO DI CONTROLLO AMMINISTRATORE ---
else:
    st.divider()
    st.subheader("🛠️ Strumenti di Amministrazione Mappa")
    st.info("💡 **Istruzioni Admin:** Seleziona un posto dal menu per Modificarlo, Bloccarlo o Liberarlo.")
    
    colA, colB = st.columns(2)
    
    with colA:
        posto_admin = st.selectbox("Seleziona uno stallo da gestire:", ["-- Seleziona --"] + list(POSTI.keys()))
        
    with colB:
        if posto_admin != "-- Seleziona --":
            st.write("### Azioni disponibili:")
            
            # Se il posto è LIBERO
            if posto_admin not in prenotazioni_giorno:
                st.success(f"Il posto **{posto_admin}** attualmente è LIBERO.")
                if st.button(f"Rendi NON DISPONIBILE il posto {posto_admin} ⛔", use_container_width=True):
                    supabase.table("prenotazioni").insert({"utente_id": utente_loggato["id"], "data": data_str, "posto_id": posto_admin}).execute()
                    st.success("Posto bloccato con successo!")
                    st.rerun()
                    
            # Se il posto è OCCUPATO O BLOCCATO
            else:
                info_p = prenotazioni_giorno[posto_admin]
                nome_occ = info_p["username"]
                
                if nome_occ.lower() == "admin":
                    st.warning(f"Il posto **{posto_admin}** è bloccato da te (NON DISPONIBILE).")
                    if st.button(f"Rendi nuovamente DISPONIBILE {posto_admin} 🔓", use_container_width=True):
                        supabase.table("prenotazioni").delete().eq("id", info_p["id_prenotazione"]).execute()
                        st.success("Posto sbloccato con successo!")
                        st.rerun()
                else:
                    st.error(f"Posto occupato da: **{nome_occ}** (Gruppo: {info_p['gruppo']})")
                    if st.button(f"Cancella d'autorità la prenotazione di {nome_occ} 🗑️", use_container_width=True):
                        supabase.table("prenotazioni").delete().eq("id", info_p["id_prenotazione"]).execute()
                        st.success("Prenotazione rimossa con successo!")
                        st.rerun()

    st.divider()
    st.subheader("📋 Registro Generale Prenotazioni")
    
    # --- LOGICA ESTRAZIONE E DOWNLOAD EXCEL ---
    risposta_t = supabase.table("prenotazioni").select("data, posto_id, passeggeri, numero_persone, utenti(username, targa, gruppo)").order("data", desc=False).execute()
    
    if risposta_t.data:
        lista_excel = []
        for item in risposta_t.data:
            u_info = item.get("utenti") or {}
            p_data_raw = item.get("data")
            
            try:
                dt = datetime.datetime.strptime(p_data_raw, "%Y-%m-%d")
                p_data_visiva = dt.strftime("%d/%m/%Y")
            except Exception:
                p_data_visiva = p_data_raw
                
            p_user = u_info.get("username", "Occupato")
            
            lista_excel.append({
                "Data": p_data_visiva,
                "Posto": item.get("posto_id"),
                "Stato / Utente": "BLOCCATO (Admin)" if p_user.lower() == 'admin' else p_user,
                "Gruppo": u_info.get("gruppo", "-") if p_user.lower() != 'admin' else "-",
                "Targa": u_info.get("targa", "-") if p_user.lower() != 'admin' else "-",
                "Numero Persone": item.get("numero_persone", 1) if p_user.lower() != 'admin' else "-",
                "Passeggeri a Bordo": item.get("passeggeri", "Nessuno") if p_user.lower() != 'admin' else "-"
            })
        
        df_excel = pd.DataFrame(lista_excel)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_excel.to_excel(writer, index=False, sheet_name='Prenotazioni')
        buffer.seek(0)
        
        st.download_button(
            label="📥 Scarica tutte le prenotazioni in Excel (.xlsx)",
            data=buffer,
            file_name=f"report_prenotazioni_{date.today().strftime('%d_%m_%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    else:
        st.info("Nessun dato disponibile da esportare in Excel.")

    st.write("") 
    vista_totale = st.checkbox("🔄 Mostra lo storico TOTALE a schermo (non solo oggi)", value=False)
    
    if vista_totale:
        st.write("### 📊 Registro Complessivo di Tutte le Prenotazioni Attive")
        if risposta_t.data:
            for item in risposta_t.data:
                u_info = item.get("utenti") or {}
                p_data_raw = item.get("data")
                
                try:
                    dt = datetime.datetime.strptime(p_data_raw, "%Y-%m-%d")
                    p_data_visiva = dt.strftime("%d/%m/%Y")
                except Exception:
                    p_data_visiva = p_data_raw
                
                p_posto = item.get("posto_id")
                p_user = u_info.get("username", "Occupato")
                p_group = u_info.get("gruppo", "-")
                p_targa = u_info.get("targa", "-")
                p_pass = item.get("passeggeri") or "Nessuno"
                p_num = item.get("numero_persone") or 1
                
                if p_user.lower() == 'admin':
                    st.write(f"📅 **{p_data_visiva}** ➔ 🚫 Posto **{p_posto}** BLOCCATO dall'Amministratore")
                else:
                    st.write(f"📅 **{p_data_visiva}** ➔ 🚗 Posto **{p_posto}** di **{p_user}** ({p_group} | Targa: {p_targa}) ➔ *A bordo ({p_num} persone): {p_pass}*")
        else:
            st.info("Nessuna prenotazione presente nell'intero database.")
    else:
        st.write(f"### 📅 Prenotazioni estratte per il giorno: {data_visiva}")
        if prenotazioni_giorno:
            for p_id, info in prenotazioni_giorno.items():
                if info['username'].lower() == 'admin':
                    st.write(f"🚫 Posto **{p_id}** ➔ **NON DISPONIBILE** (Bloccato dall'Amministratore)")
                else:
                    st.write(f"🚗 Posto **{p_id}** ➔ Occupato da **{info['username']}** (Gruppo: *{info['gruppo']}* | Targa: {info['targa']}) ➔ *A bordo ({info['numero_persone']} persone): {info['passeggeri']}*")
        else:
            st.info(f"Nessuna prenotazione o blocco registrato per la data del {data_visiva}.")
