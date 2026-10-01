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

# --- CONFIGURAZIONE GRUPPI STUDENTI & GIORNI PREDEFINITI ---
# Lunedì=0, Martedì=1, Mercoledì=2, Giovedì=3, Venerdì=4, Sabato=5, Domenica=6
GRUPPI_STUDENTI = {
    # GRUPPO 1: Lunedì - Martedì - Mercoledì
    "Marketing 1":              {"giorni_default": [0, 1, 2]},
    "Marketing 2":              {"giorni_default": [0, 1, 2]},
    "Wine Sales 1":             {"giorni_default": [0, 1, 2]},
    "Food Quality Management 1": {"giorni_default": [0, 1, 2]},
    "Filiere Gastronomiche 2":  {"giorni_default": [0, 1, 2]},

    # GRUPPO 2: Mercoledì - Giovedì - Venerdì
    "Sistemi Zootecnici 1":     {"giorni_default": [2, 3, 4]},
    "Sistemi Zootecnici 2":     {"giorni_default": [2, 3, 4]},
    "Enologia e Viticoltura 1": {"giorni_default": [2, 3, 4]},
    "Enologia e Viticoltura 2": {"giorni_default": [2, 3, 4]},
    "Precision Farming 1":      {"giorni_default": [2, 3, 4]},
    "Agricoltura 4.0 2":        {"giorni_default": [2, 3, 4]},
}

TOTALE_POSTI_STUDENTI = 15 + 20 + 19  # 54 Posti (Bassa, Alta, Piazzale)
DATA_PERMANENTE = "2099-12-31"        # Data usata per assegnazioni fisse Staff

# --- FUNZIONI DI CALCOLO DINAMICO ---
def get_corsi_presenti(data_obj):
    """Restituisce la lista dei corsi presenti per una data tenendo conto di calendario ed eccezioni Admin."""
    giorno_sett = data_obj.weekday()
    data_str = data_obj.strftime("%Y-%m-%d")
    
    # Corsi di default per il giorno della settimana
    presenti = set([grp for grp, info in GRUPPI_STUDENTI.items() if giorno_sett in info["giorni_default"]])
    
    # Sovrascritture dell'Admin
    try:
        res = supabase.table("presenze_corsi").select("gruppo, stato").eq("data", data_str).execute()
        if res.data:
            for row in res.data:
                grp, st_val = row["gruppo"], row["stato"]
                if st_val == "PRESENTE":
                    presenti.add(grp)
                elif st_val == "ASSENTE" and grp in presenti:
                    presenti.remove(grp)
    except Exception:
        pass
        
    return list(presenti)

def get_numero_studenti_per_gruppo():
    """Conta il numero reale di studenti registrati nel DB per ogni gruppo."""
    counts = {grp: 0 for grp in GRUPPI_STUDENTI.keys()}
    try:
        res = supabase.table("utenti").select("gruppo").execute()
        if res.data:
            for u in res.data:
                grp = u.get("gruppo")
                if grp in counts:
                    counts[grp] += 1
    except Exception:
        pass
    return counts

def calcola_quote_posti(data_obj):
    """Calcola i posti disponibili per ciascun corso in proporzione al numero di studenti presenti."""
    corsi_pres = get_corsi_presenti(data_obj)
    studenti_counts = get_numero_studenti_per_gruppo()
    
    totale_studenti_oggi = sum(studenti_counts.get(g, 0) for g in corsi_pres)
    
    quote = {}
    if totale_studenti_oggi > 0:
        for g in corsi_pres:
            n_stud = studenti_counts.get(g, 0)
            if n_stud > 0:
                q = max(1, round((n_stud / totale_studenti_oggi) * TOTALE_POSTI_STUDENTI))
                quote[g] = q
            else:
                quote[g] = 1
    else:
        # Ripartizione equa di backup se non ci sono iscritti
        quota_equa = max(1, TOTALE_POSTI_STUDENTI // len(corsi_pres)) if corsi_pres else 0
        quote = {g: quota_equa for g in corsi_pres}
        
    return quote, corsi_pres, studenti_counts

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

# --- SIDEBAR DI CONTROLLO & GESTIONE ---
st.sidebar.header("👤 Account")
st.sidebar.write(f"Utente: **{username}**")
st.sidebar.write(f"Gruppo: **{gruppo_utente}**")
st.sidebar.write(f"Targa: **{targa_utente if targa_utente else 'Non impostata'}**")

with st.sidebar.expander("✏️ Modifica la tua Targa"):
    nuova_targa = st.text_input("Nuova Targa:", value=targa_utente, key="input_targa")
    if st.button("Salva Targa 💾", use_container_width=True):
        if nuova_targa.strip():
            supabase.table("utenti").update({"targa": nuova_targa.strip().upper()}).eq("id", utente_loggato["id"]).execute()
            st.session_state["utente_autenticato"]["targa"] = nuova_targa.strip().upper()
            st.success("Targa aggiornata!")
            st.rerun()

st.sidebar.divider()
st.sidebar.subheader("📅 Seleziona Giorno e Fascia")
oggi = date.today()

gruppi_con_finestra = list(GRUPPI_STUDENTI.keys()) + ["Alloggi"]
max_data = oggi + datetime.timedelta(days=14) if (gruppo_utente in gruppi_con_finestra and not is_admin) else oggi + datetime.timedelta(days=365)

data_scelta = st.sidebar.date_input("Data:", min_value=oggi, max_value=max_data, format="DD/MM/YYYY")
data_str = data_scelta.strftime("%Y-%m-%d")
data_visiva = data_scelta.strftime("%d/%m/%Y")

fascia_visualizza = st.sidebar.selectbox("Fascia oraria da vedere:", ["Tutto il Giorno", "Mattino", "Pomeriggio"])

if st.sidebar.button("Log out ❌", use_container_width=True):
    st.session_state["utente_autenticato"] = None
    st.rerun()

# Pulizia vecchi dati (3 giorni fa)
try:
    data_limite = oggi - datetime.timedelta(days=3)
    supabase.table("prenotazioni").delete().lt("data", data_limite.strftime("%Y-%m-%d")).execute()
except Exception:
    pass

# --- 4. LISTA POSTI ---
POSTI = {
    **{f"Bassa-{i}": {} for i in range(1, 16)},
    **{f"Alta-{i}": {} for i in range(1, 21)},
    **{f"Piazzale-{i}": {} for i in range(1, 20)},
    **{f"Staff-{i}": {} for i in range(1, 23)},
    **{f"Docenti-{i}": {} for i in range(1, 6)},
    **{f"Alloggi-{i}": {} for i in range(1, 12)}
}

# --- 5. RECUPERO PRENOTAZIONI DAL DATABASE ---
# Formato: { posto_id: [ list_of_prenotazioni ] }
prenotazioni_raw = []

resp_p = supabase.table("prenotazioni").select("id, posto_id, utente_id, data, turno, utenti(username, targa, gruppo)").in_("data", [data_str, DATA_PERMANENTE]).execute()
if resp_p.data:
    prenotazioni_raw = resp_p.data

def occupato_in_fascia(prenotazioni_posto, fascia_target):
    """Controlla se un determinato posto è occupato per la fascia richiesta."""
    for p in prenotazioni_posto:
        t = p.get("turno", "TUTTO_IL_GIORNO")
        if t == "TUTTO_IL_GIORNO":
            return p
        if fascia_target == "Tutto il Giorno":
            return p
        if t == fascia_target:
            return p
    return None

# Mappa dello stato per la visualizzazione sulla mappa HTML
prenotazioni_visibili = {}
for p in prenotazioni_raw:
    p_id = p.get("posto_id")
    p_turno = p.get("turno", "TUTTO_IL_GIORNO")
    
    # Controlla se la prenotazione impatta la fascia selezionata
    if fascia_visualizza == "Tutto il Giorno" or p_turno == "TUTTO_IL_GIORNO" or p_turno == fascia_visualizza:
        if p_id and p_id not in prenotazioni_visibili:
            info_u = p.get("utenti") or {}
            prenotazioni_visibili[p_id] = {
                "id_prenotazione": p.get("id"),
                "utente_id": p.get("utente_id"),
                "username": info_u.get("username", "Occupato"),
                "targa": info_u.get("targa", "-"),
                "gruppo": info_u.get("gruppo", ""),
                "turno": p_turno
            }

# --- 6. MAPPA INTERATTIVA ---
st.subheader(f"🗺️ Mappa Parcheggi - {data_visiva} ({fascia_visualizza})")

def get_base64_image(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return f"data:image/png;base64,{base64.b64encode(img_file.read()).decode()}"
    except FileNotFoundError:
        return ""

bg_image_base64 = get_base64_image("Screenshot 2026-09-30 alle 14.20.10.png")

try:
    with open("mappa.html", "r", encoding="utf-8") as f:
        html_raw = f.read()
    
    html_ready = html_raw.replace("ST_PRENOTAZIONI_JSON_PLACEHOLDER", json.dumps(prenotazioni_visibili))
    html_ready = html_ready.replace("ST_BACKGROUND_IMAGE_PLACEHOLDER", bg_image_base64)
    components.html(html_ready, height=800, scrolling=True)
except Exception as e:
    st.error(f"⚠️ Impossibile caricare la mappa: {e}")

# --- 7. LOGICA PRENOTAZIONI ---
st.divider()

# Calcolo quote dinamiche per la giornata scelta
quote_dinamiche, corsi_presenti_oggi, numero_iscritti = calcola_quote_posti(data_scelta)

if not is_admin:
    # Controlla se l'utente ha già una prenotazione attiva per la data
    mie_prenotazioni = [p for p in prenotazioni_raw if p["utente_id"] == utente_loggato["id"]]
    
    if mie_prenotazioni:
        st.warning("🏷️ Hai già le seguenti prenotazioni per questo giorno:")
        for mp in mie_prenotazioni:
            f_str = mp.get("turno", "TUTTO_IL_GIORNO")
            st.write(f"- **Posto {mp['posto_id']}** ({f_str})")
            if st.button(f"Cancella Prenotazione {mp['posto_id']} ({f_str}) ❌", key=f"del_{mp['id']}"):
                supabase.table("prenotazioni").delete().eq("id", mp["id"]).execute()
                st.success("Prenotazione annullata!")
                st.rerun()
    else:
        st.subheader("📌 Prenota il tuo Posto Auto")
        
        # Scelta del Turno / Fascia Oraria
        turno_richiesto = st.radio(
            "Seleziona la fascia oraria di cui hai bisogno:",
            ["Mattino", "Pomeriggio", "Tutto il Giorno"],
            horizontal=True
        )
        
        # Mappatura testo -> DB
        mappa_turno_db = {
            "Mattino": "MATTINO",
            "Pomeriggio": "POMERIGGIO",
            "Tutto il Giorno": "TUTTO_IL_GIORNO"
        }
        turno_db = mappa_turno_db[turno_richiesto]

        # Funzione helper per verificare posti liberi rispettando i turni
        def trova_posto_libero(prefisso_lista):
            for p in prefisso_lista:
                prenotazioni_posto = [pr for pr in prenotazioni_raw if pr["posto_id"] == p]
                if not occupato_in_fascia(prenotazioni_posto, turno_richiesto):
                    return p
            return None

        # CASO STAFF
        if gruppo_utente == "Staff":
            st.info("ℹ️ Come membro dello Staff puoi riservare un posto giornaliero o permanente.")
            posti_staff = [f"Staff-{i}" for i in range(1, 23)]
            posto_trovato = trova_posto_libero(posti_staff)
            
            tipo_staff = st.radio("Tipo Assegnazione Staff:", ["Giornaliera", "Permanente (Fissa)"])
            
            if posto_trovato:
                if st.button(f"Conferma Assegnazione Posto {posto_trovato} 🟢", use_container_width=True):
                    d_save = DATA_PERMANENTE if tipo_staff == "Permanente (Fissa)" else data_str
                    supabase.table("prenotazioni").insert({
                        "utente_id": utente_loggato["id"],
                        "data": d_save,
                        "posto_id": posto_trovato,
                        "turno": turno_db
                    }).execute()
                    st.success(f"Posto {posto_trovato} riservato con successo!")
                    st.rerun()
            else:
                st.error("❌ Nessun Posto Staff libero per questa fascia oraria.")

        # CASO DOCENTI
        elif gruppo_utente == "Docenti":
            posti_doc = [f"Docenti-{i}" for i in range(1, 6)]
            posto_trovato = trova_posto_libero(posti_doc)
            if posto_trovato:
                if st.button(f"Prenota Posto Docenti ({posto_trovato}) 🟢", use_container_width=True):
                    supabase.table("prenotazioni").insert({
                        "utente_id": utente_loggato["id"],
                        "data": data_str,
                        "posto_id": posto_trovato,
                        "turno": turno_db
                    }).execute()
                    st.success(f"Posto {posto_trovato} prenotato!")
                    st.rerun()
            else:
                st.error("❌ Nessun Posto Docenti libero per questa fascia oraria.")

        # CASO ALLOGGI
        elif gruppo_utente == "Alloggi":
            posti_all = [f"Alloggi-{i}" for i in range(1, 12)]
            posto_trovato = trova_posto_libero(posti_all)
            if posto_trovato:
                if st.button(f"Prenota Posto Alloggi ({posto_trovato}) 🚗", use_container_width=True):
                    supabase.table("prenotazioni").insert({
                        "utente_id": utente_loggato["id"],
                        "data": data_str,
                        "posto_id": posto_trovato,
                        "turno": turno_db
                    }).execute()
                    st.success(f"🎉 Posto {posto_trovato} assegnato!")
                    st.rerun()
            else:
                st.error("❌ Posti Alloggi esauriti per la fascia selezionata.")

        # CASO STUDENTI (CON VERIFICA PRESENZA E QUOTA DINAMICA)
        else:
            if gruppo_utente not in corsi_presenti_oggi:
                st.error(f"❌ Il gruppo **{gruppo_utente}** non risulta presente/in lezione il giorno **{data_visiva}**.")
                st.stop()
            
            max_quota = quote_dinamiche.get(gruppo_utente, 0)
            
            # Conteggio posti occupati dal gruppo nella fascia oraria richiesta
            occupati_gruppo = 0
            for pr in prenotazioni_raw:
                u_grp = (pr.get("utenti") or {}).get("gruppo")
                if u_grp == gruppo_utente:
                    t_pr = pr.get("turno", "TUTTO_IL_GIORNO")
                    if turno_db == "TUTTO_IL_GIORNO" or t_pr == "TUTTO_IL_GIORNO" or t_pr == turno_db:
                        occupati_gruppo += 1
            
            st.info(f"📊 **Quota del tuo corso ({gruppo_utente}) per oggi**: **{occupati_gruppo}/{max_quota}** posti prenotati.")
            
            if occupati_gruppo >= max_quota:
                st.error(f"❌ Limite raggiunto! Il gruppo **{gruppo_utente}** ha esaurito la quota massima di **{max_quota}** posti per la fascia **{turno_richiesto}**.")
            else:
                if st.button("Prenota Posto Auto Studenti 🚗", use_container_width=True):
                    posti_studenti = [f"Bassa-{i}" for i in range(1, 16)] + [f"Alta-{i}" for i in range(1, 21)] + [f"Piazzale-{i}" for i in range(1, 20)]
                    posto_trovato = trova_posto_libero(posti_studenti)
                    
                    if posto_trovato:
                        supabase.table("prenotazioni").insert({
                            "utente_id": utente_loggato["id"],
                            "data": data_str,
                            "posto_id": posto_trovato,
                            "turno": turno_db
                        }).execute()
                        st.success(f"🎉 Ti è stato assegnato il **Posto {posto_trovato}** ({turno_richiesto})!")
                        st.rerun()
                    else:
                        st.error("❌ Tutti i posti studenti nelle zone verdi sono occupati per questa fascia oraria.")

# --- PANNELLO AMMINISTRATORE ---
else:
    st.divider()
    st.subheader("🛠️ Pannello Amministrazione Parcheggi")
    
    tab1, tab2, tab3 = st.tabs(["📌 Gestione Posti", "📅 Presenze Corsi (Calendario)", "📋 Report & Quote"])
    
    with tab1:
        colA, colB = st.columns(2)
        with colA:
            posto_admin = st.selectbox("Seleziona un Posto da gestire:", ["-- Seleziona --"] + list(POSTI.keys()))
            turno_admin = st.selectbox("Fascia da gestire:", ["MATTINO", "POMERIGGIO", "TUTTO_IL_GIORNO"])
            
        with colB:
            if posto_admin != "-- Seleziona --":
                pr_esistenti = [pr for pr in prenotazioni_raw if pr["posto_id"] == posto_admin]
                occ = occupato_in_fascia(pr_esistenti, turno_admin)
                
                if not occ:
                    st.success(f"Il **Posto {posto_admin}** è LIBERO per {turno_admin}.")
                    if st.button(f"Blocca Posto {posto_admin} ⛔", use_container_width=True):
                        supabase.table("prenotazioni").insert({
                            "utente_id": utente_loggato["id"],
                            "data": data_str,
                            "posto_id": posto_admin,
                            "turno": turno_admin
                        }).execute()
                        st.success("Posto bloccato!")
                        st.rerun()
                else:
                    u_info = occ.get("utenti") or {}
                    n_occ = u_info.get("username", "Occupato")
                    st.error(f"Occupato da: **{n_occ}** ({occ.get('turno')})")
                    if st.button(f"Rimuovi Prenotazione 🗑️", use_container_width=True):
                        supabase.table("prenotazioni").delete().eq("id", occ["id"]).execute()
                        st.success("Prenotazione rimossa!")
                        st.rerun()

    with tab2:
        st.write(f"### 🗓️ Gestione Presenza Corsi per il giorno **{data_visiva}**")
        st.info("Puoi segnare un corso come PRESENTE (es. lezioni straordinarie) o ASSENTE (es. gita/esami). Le quote posti si ricalcoleranno in automatico.")
        
        # Recupera lo stato attuale per il giorno scelto
        res_eccez = {}
        try:
            r_ec = supabase.table("presenze_corsi").select("gruppo, stato").eq("data", data_str).execute()
            if r_ec.data:
                res_eccez = {row["gruppo"]: row["stato"] for row in r_ec.data}
        except Exception:
            pass
        
        col_c1, col_c2 = st.columns(2)
        idx = 0
        for grp in GRUPPI_STUDENTI.keys():
            col_target = col_c1 if idx % 2 == 0 else col_c2
            idx += 1
            
            is_def = data_scelta.weekday() in GRUPPI_STUDENTI[grp]["giorni_default"]
            stato_curr = res_eccez.get(grp, "PRESENTE" if is_def else "ASSENTE")
            
            with col_target:
                scelta = st.radio(
                    f"**{grp}** (Standard: {'Presente' if is_def else 'Assente'}):",
                    ["PRESENTE", "ASSENTE"],
                    index=0 if stato_curr == "PRESENTE" else 1,
                    key=f"pres_{grp}_{data_str}",
                    horizontal=True
                )
                
                # Se lo stato modificato differisce dal default o c'era un override, salva su DB
                if scelta != stato_curr:
                    supabase.table("presenze_corsi").upsert({
                        "data": data_str,
                        "gruppo": grp,
                        "stato": scelta
                    }).execute()
                    st.success(f"Aggiornata presenza per {grp}!")
                    st.rerun()

    with tab3:
        st.write("### 📊 Quote Posti Calcolate per Oggi")
        
        df_quote = pd.DataFrame([
            {
                "Corso": grp,
                "Stato Oggi": "PRESENTE 🟢" if grp in corsi_presenti_oggi else "ASSENTE 🔴",
                "Iscritti Totali": numero_iscritti.get(grp, 0),
                "Quota Posti Auto Assignata": quote_dinamiche.get(grp, 0) if grp in corsi_presenti_oggi else 0
            }
            for grp in GRUPPI_STUDENTI.keys()
        ])
        st.dataframe(df_quote, use_container_width=True)
        
        st.divider()
        st.write("### 📋 Download Report Excel Completo")
        risposta_t = supabase.table("prenotazioni").select("data, posto_id, turno, utenti(username, targa, gruppo)").execute()
        
        if risposta_t.data:
            lista_excel = []
            for item in risposta_t.data:
                u_info = item.get("utenti") or {}
                p_data_raw = str(item.get("data", ""))
                p_user = u_info.get("username", "Occupato")
                
                lista_excel.append({
                    "Data": "PERMANENTE" if p_data_raw == DATA_PERMANENTE else p_data_raw,
                    "Fascia Oraria": item.get("turno", "TUTTO_IL_GIORNO"),
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
