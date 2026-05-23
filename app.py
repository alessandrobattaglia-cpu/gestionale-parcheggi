import streamlit as st
import datetime
from datetime import date
from supabase import create_client, Client
import plotly.graph_objects as go
from PIL import Image
import os
import pandas as pd  
import io

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

# --- 4. CALIBRAZIONE MAPPA DEFINITIVA ---
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
    
    "Alloggi-13": {"x": 59.8, "y": 739.9}, "Alloggi-12": {"x": 59.8, "y": 777.6}, 
    "Alloggi-11": {"x": 59.8, "y": 815.6}, "Alloggi-10": {"x": 59.8, "y": 853.8}, 
    "Alloggi-9":  {"x": 59.8, "y": 890.5}, "Alloggi-8":  {"x": 59.8, "y": 927.6}, 
    "Alloggi-7":  {"x": 59.8, "y": 965.8}, "Alloggi-6":  {"x": 59.8, "y": 1004.8},
    "Alloggi-5":  {"x": 196.6, "y": 982.0}, "Alloggi-4": {"x": 251.6, "y": 982.0}, 
    "Alloggi-3":  {"x": 306.4, "y": 982.0}, "Alloggi-2": {"x": 361.9, "y": 982.0}, 
    "Alloggi-1":  {"x": 415.5, "y": 982.0},
    
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

# --- 6. COSTRUZIONE E DISEGNO DELLA MAPPA ---
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
        info_p = prenotazioni_giorno[codice_posto]
        if info_p["username"].lower() == "admin":
            testi.append(f"⛔ {codice_posto} (NON DISPONIBILE)")
        elif is_admin or gruppo_utente == "Personale":
            testi.append(f"⛔ {codice_posto}<br>Occupato da: {info_p['username']} ({info_p['gruppo']})<br>Persone a bordo: {info_p['numero_persone']}")
        else:
            testi.append(f"⛔ {codice_posto} (Occupato)")
    else:
        colori.append("green")
        testi.append(f"🟢 {codice_posto} (Libero)")

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
fig.update_layout(height=850, margin=dict(l=0, r=0, t=0, b=0), clickmode="event+select")

st.subheader(f"Mappa Parcheggi per il giorno: {data_visiva}")
config = {'displayModeBar': False}

mappa_interattiva = (gruppo_utente == "Personale" or is_admin)
click_data = st.plotly_chart(fig, use_container_width=True, on_select="rerun" if mappa_interattiva else "ignore", config=config)

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
            st.info("💡 **Modalità Personale:** Fai click direttamente su un pallino **VERDE** nella mappa per selezionare la tua area.")
            if click_data and "selection" in click_data and click_data["selection"]["points"]:
                punto_cliccato = click_data["selection"]["points"][0]
                indice_punto = punto_cliccato.get("point_index", punto_cliccato.get("pointNumber"))
                
                if indice_punto is not None and indice_punto < len(chiavi_posto):
                    posto_scelto = chiavi_posto[indice_punto]
                    if posto_scelto not in prenotazioni_giorno:
                        st.success(f"Hai selezionato il posto: **{posto_scelto}**")
                        if st.button(f"Conferma Prenotazione Posto {posto_scelto} 🟢", use_container_width=True):
                            supabase.table("prenotazioni").insert({"utente_id": utente_loggato["id"], "data": data_str, "posto_id": posto_scelto}).execute()
                            st.success(f"Posto {posto_scelto} riservato!")
                            st.rerun()
                    else:
                        st.error("Posto già occupato o non disponibile, scegline un altro.")

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
    st.info("💡 **Istruzioni Admin:** Fai click su un pallino **VERDE** sulla mappa per bloccarlo. Clicca su un pallino **ROSSO** per sbloccarlo o forzare la cancellazione.")
    
    if click_data and "selection" in click_data and click_data["selection"]["points"]:
        punto_cliccato = click_data["selection"]["points"][0]
        indice_punto = punto_cliccato.get("point_index", punto_cliccato.get("pointNumber"))
        
        if indice_punto is not None and indice_punto < len(chiavi_posto):
            posto_scelto = chiavi_posto[indice_punto]
            
            if posto_scelto not in prenotazioni_giorno:
                st.success(f"Hai selezionato il posto libero: **{posto_scelto}**")
                if st.button(f"Rendi NON DISPONIBILE il posto {posto_scelto} ⛔", use_container_width=True):
                    supabase.table("prenotazioni").insert({"utente_id": utente_loggato["id"], "data": data_str, "posto_id": posto_scelto}).execute()
                    st.success(f"Posto {posto_scelto} bloccato!")
                    st.rerun()
            else:
                info_p = prenotazioni_giorno[posto_scelto]
                nome_occ = info_p["username"]
                
                if nome_occ.lower() == "admin":
                    st.warning(f"Il posto **{posto_scelto}** è attualmente impostato como NON DISPONIBILE.")
                    if st.button(f"Rendi nuovamente DISPONIBILE il posto {posto_scelto} 🔓", use_container_width=True):
                        supabase.table("prenotazioni").delete().eq("id", info_p["id_prenotazione"]).execute()
                        st.success(f"Posto {posto_scelto} sbloccato!")
                        st.rerun()
                else:
                    st.warning(f"Il posto **{posto_scelto}** è prenotato da: **{nome_occ}** (Gruppo: {info_p['gruppo']})")
                    if st.button(f"Cancella d'autorità la prenotazione di {nome_occ} 🗑️", use_container_width=True):
                        supabase.table("prenotazioni").delete().eq("id", info_p["id_prenotazione"]).execute()
                        st.success(f"Prenotazione rimossa con successo!")
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
