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
    
    # Disattivato fino a Febbraio
    "Enologia e Viticoltura 2": {"giorni_default": []}, 
    
    "Precision Farming 1":      {"giorni_default": [2, 3, 4]},
    "Agricoltura 4.0 2":        {"giorni_default": [2, 3, 4]},
}

MAPPA_GIORNI_SETTIMANA = {
    "Lunedì": 0, 
    "Martedì": 1, 
    "Mercoledì": 2, 
    "Giovedì": 3, 
    "Venerdì": 4, 
    "Sabato": 5, 
    "Domenica": 6
}

TOTALE_POSTI_STUDENTI = 15 + 20 + 19  # 54 Posti (Bassa, Alta, Piazzale)
DATA_PERMANENTE = "2099-12-31"        # Data usata per assegnazioni fisse

POSTI_PER_ZONA = {
    "Bassa": [f"Bassa-{i}" for i in range(1, 16)],
    "Alta": [f"Alta-{i}" for i in range(1, 21)],
    "Piazzale": [f"Piazzale-{i}" for i in range(1, 20)],
    "Staff": [f"Staff-{i}" for i in range(1, 23)],
    "Docenti": [f"Docenti-{i}" for i in range(1, 6)],
    "Alloggi": [f"Alloggi-{i}" for i in range(1, 12)]
}

POSTI = {}
for lista in POSTI_PER_ZONA.values():
    for p in lista:
        POSTI[p] = {}

# --- FUNZIONI UTILITY UTENTI ---
def check_is_alloggi(u_dict):
    """Verifica se un utente è alloggiato da vari campi possibili."""
    if not isinstance(u_dict, dict):
        return False
    if u_dict.get("is_alloggi") or u_dict.get("alloggi"):
        return True
    grp = str(u_dict.get("gruppo", ""))
    return grp.startswith("Alloggi")

# --- FUNZIONI DI CALCOLO DINAMICO ---
def get_corsi_presenti(data_obj):
    giorno_sett = data_obj.weekday()
    data_str = data_obj.strftime("%Y-%m-%d")
    presenti = set([grp for grp, info in GRUPPI_STUDENTI.items() if giorno_sett in info["giorni_default"]])
    
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
    """Conteggia gli studenti escludendo chi risiede negli alloggi."""
    counts = {grp: 0 for grp in GRUPPI_STUDENTI.keys()}
    try:
        res = supabase.table("utenti").select("*").execute()
        if res.data:
            for u in res.data:
                grp = u.get("gruppo")
                if not check_is_alloggi(u) and grp in counts:
                    counts[grp] += 1
    except Exception:
        pass
    return counts

def calcola_quote_posti(data_obj):
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
        quota_equa = max(1, TOTALE_POSTI_STUDENTI // len(corsi_pres)) if corsi_pres else 0
        quote = {g: quota_equa for g in corsi_pres}
        
    return quote, corsi_pres, studenti_counts

def get_eventi_giorno(data_str):
    """Recupera gli eventi attivi per la data selezionata."""
    try:
        res = supabase.table("eventi").select("*").eq("data", data_str).execute()
        return res.data if res.data else []
    except Exception:
        return []

def get_posti_bloccati_evento(data_str, is_staff_or_admin=False):
    """Restituisce la mappa dei posti bloccati dagli eventi con gestione privacy per singoli posti."""
    eventi = get_eventi_giorno(data_str)
    bloccati = {}
    for ev in eventi:
        ev_id = ev.get("id")
        ev_nome = ev.get("nome_evento", "Evento")
        ev_note = ev.get("note", "")
        ev_blocchi = ev.get("blocchi", "TUTTI")
        
        # Recupera dettagli dei singoli posti
        ev_dettagli = ev.get("dettagli_posti") or {}
        if isinstance(ev_dettagli, str):
            try:
                ev_dettagli = json.loads(ev_dettagli)
            except Exception:
                ev_dettagli = {}
        elif not isinstance(ev_dettagli, dict):
            ev_dettagli = {}

        if isinstance(ev_blocchi, str):
            blocchi_list = [b.strip() for b in ev_blocchi.split(",")]
        else:
            blocchi_list = ev_blocchi if isinstance(ev_blocchi, list) else ["TUTTI"]
            
        for p_id in POSTI.keys():
            prefisso = p_id.split("-")[0]
            if "TUTTI" in blocchi_list or prefisso in blocchi_list:
                # Testo specifico per il posto, se specificato
                testo_specifico = ev_dettagli.get(p_id, "").strip()
                if not testo_specifico:
                    testo_specifico = ev_note if ev_note else "Riservato Evento"

                # PRIVACY: Solo Admin e Staff vedono la nota specifica del singolo posto
                targa_visibile = testo_specifico if is_staff_or_admin else "Riservato Evento"

                bloccati[p_id] = {
                    "id_prenotazione": f"ev_{ev_id}",
                    "utente_id": None,
                    "username": f"🎉 {ev_nome}",
                    "targa": targa_visibile,
                    "gruppo": "EVENTO",
                    "turno": "TUTTO_IL_GIORNO"
                }
    return bloccati

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
                try:
                    risposta = supabase.table("utenti").select("*").eq("username", username_inserito).eq("password", password_inserita).execute()
                    if risposta.data:
                        st.session_state["utente_autenticato"] = risposta.data[0]
                        st.rerun()
                    else:
                        st.error("❌ Credenziali errate.")
                except Exception as e_login:
                    st.error(f"❌ Errore durante l'accesso al database: {e_login}")
            else:
                st.warning("Compila entrambi i campi.")
    st.stop()

utente_loggato = st.session_state["utente_autenticato"]
username = utente_loggato.get("username", "")
gruppo_utente = utente_loggato.get("gruppo", "Marketing 1")
targa_utente = utente_loggato.get("targa", "")
is_admin = (username.lower() == "admin")
is_alloggi_user = check_is_alloggi(utente_loggato)
is_staff_or_admin = is_admin or (gruppo_utente == "Staff")

# --- SIDEBAR DI CONTROLLO & GESTIONE ---
st.sidebar.header("👤 Account")
st.sidebar.write(f"Utente: **{username}**")
st.sidebar.write(f"Corso/Gruppo: **{gruppo_utente}**")
if is_alloggi_user:
    st.sidebar.info("🏠 **Residente Alloggi**")
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
st.sidebar.subheader("📅 Seleziona Giorno")
oggi = date.today()

# Finestra prenotazioni
max_data = oggi + datetime.timedelta(days=14) if (not is_admin and not is_alloggi_user) else oggi + datetime.timedelta(days=365)

data_scelta = st.sidebar.date_input("Data:", min_value=oggi, max_value=max_data, format="DD/MM/YYYY")
data_str = data_scelta.strftime("%Y-%m-%d")
data_visiva = data_scelta.strftime("%d/%m/%Y")

if st.sidebar.button("Log out ❌", use_container_width=True):
    st.session_state["utente_autenticato"] = None
    st.rerun()

# Pulizia vecchi dati (3 giorni fa, escludendo permanenti)
try:
    data_limite = oggi - datetime.timedelta(days=3)
    supabase.table("prenotazioni").delete().lt("data", data_limite.strftime("%Y-%m-%d")).neq("data", DATA_PERMANENTE).execute()
except Exception:
    pass

# --- 4. RECUPERO PRENOTAZIONI DAL DATABASE ---
prenotazioni_raw = []
try:
    resp_p = supabase.table("prenotazioni").select("id, posto_id, utente_id, data, turno, utenti(*)").in_("data", [data_str, DATA_PERMANENTE]).execute()
    if resp_p.data:
        prenotazioni_raw = resp_p.data
except Exception:
    try:
        resp_p = supabase.table("prenotazioni").select("id, posto_id, utente_id, data, utenti(*)").in_("data", [data_str, DATA_PERMANENTE]).execute()
        if resp_p.data:
            prenotazioni_raw = resp_p.data
    except Exception:
        pass

# --- 5. PREPARAZIONE DATI PER MAPPA CON EVENTI E PRIVACY STAFF ---
posti_bloccati_eventi = get_posti_bloccati_evento(data_str, is_staff_or_admin=is_staff_or_admin)
prenotazioni_visibili = {}

# Inserisci blocchi eventi
for p_id, info_ev in posti_bloccati_eventi.items():
    prenotazioni_visibili[p_id] = info_ev

# Inserisci prenotazioni reali del DB se non sovrascritte da eventi
for p in prenotazioni_raw:
    p_id = p.get("posto_id")
    if p_id and p_id not in posti_bloccati_eventi:
        info_u = p.get("utenti") or {}
        
        is_staff_spot = str(p_id).startswith("Staff") or info_u.get("gruppo") == "Staff"
        
        if is_staff_spot and not is_admin and gruppo_utente != "Staff":
            username_disp = "Staff"
            targa_disp = "-"
            gruppo_disp = "Staff"
        else:
            username_disp = info_u.get("username", "Occupato")
            targa_disp = info_u.get("targa", "-")
            gruppo_disp = info_u.get("gruppo", "")

        prenotazioni_visibili[p_id] = {
            "id_prenotazione": p.get("id"),
            "utente_id": p.get("utente_id"),
            "username": username_disp,
            "targa": targa_disp,
            "gruppo": gruppo_disp,
            "turno": "TUTTO_IL_GIORNO"
        }

# --- 6. MAPPA INTERATTIVA ---
st.subheader(f"🗺️ Mappa Parcheggi - {data_visiva}")

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

# --- 7. LOGICA PRENOTAZIONI UTENTI ---
st.divider()

quote_dinamiche, corsi_presenti_oggi, numero_iscritti = calcola_quote_posti(data_scelta)

def trova_posto_libero(prefisso_lista):
    for p in prefisso_lista:
        if p in posti_bloccati_eventi:
            continue
        prenotazioni_posto = [pr for pr in prenotazioni_raw if pr["posto_id"] == p]
        if not prenotazioni_posto:
            return p
    return None

if not is_admin:
    mie_prenotazioni = [p for p in prenotazioni_raw if p["utente_id"] == utente_loggato["id"]]
    
    if mie_prenotazioni:
        st.warning("🏷️ Hai la seguente prenotazione/assegnazione per questo giorno:")
        for mp in mie_prenotazioni:
            is_perm = mp.get("data") == DATA_PERMANENTE
            dt_txt = "Permanente" if is_perm else data_visiva
            st.write(f"- **Posto {mp['posto_id']}** ({dt_txt})")
            
            if not is_alloggi_user:
                if st.button(f"Cancella Prenotazione {mp['posto_id']} ❌", key=f"del_{mp['id']}"):
                    supabase.table("prenotazioni").delete().eq("id", mp["id"]).execute()
                    st.success("Prenotazione annullata!")
                    st.rerun()
    else:
        st.subheader("📌 Prenota il tuo Posto Auto")

        if is_alloggi_user:
            st.info("🏠 **Sei un utente residente negli Alloggi.** I posti parcheggio alloggiati vengono assegnati direttamente dall'Amministrazione. Non hai ancora un posto assegnato per questa data.")

        elif gruppo_utente == "Staff":
            st.info("ℹ️ Come membro dello Staff puoi riservare un posto giornaliero o permanente.")
            posti_staff = POSTI_PER_ZONA["Staff"]
            posto_trovato = trova_posto_libero(posti_staff)
            
            tipo_staff = st.radio("Tipo Assegnazione Staff:", ["Giornaliera", "Permanente (Fissa)"])
            
            if posto_trovato:
                if st.button(f"Conferma Assegnazione Posto {posto_trovato} 🟢", use_container_width=True):
                    d_save = DATA_PERMANENTE if tipo_staff == "Permanente (Fissa)" else data_str
                    data_insert = {
                        "utente_id": utente_loggato["id"],
                        "data": d_save,
                        "posto_id": posto_trovato,
                        "turno": "TUTTO_IL_GIORNO"
                    }
                    supabase.table("prenotazioni").insert(data_insert).execute()
                    st.success(f"Posto {posto_trovato} riservato con successo!")
                    st.rerun()
            else:
                st.error("❌ Nessun Posto Staff libero per oggi (o posti riservati per evento).")

        elif gruppo_utente == "Docenti":
            posti_doc = POSTI_PER_ZONA["Docenti"]
            posto_trovato = trova_posto_libero(posti_doc)
            if posto_trovato:
                if st.button(f"Prenota Posto Docenti ({posto_trovato}) 🟢", use_container_width=True):
                    supabase.table("prenotazioni").insert({
                        "utente_id": utente_loggato["id"],
                        "data": data_str,
                        "posto_id": posto_trovato,
                        "turno": "TUTTO_IL_GIORNO"
                    }).execute()
                    st.success(f"Posto {posto_trovato} prenotato!")
                    st.rerun()
            else:
                st.error("❌ Nessun Posto Docenti libero per oggi.")

        else:
            if gruppo_utente not in corsi_presenti_oggi:
                st.error(f"❌ Il gruppo **{gruppo_utente}** non risulta presente/in lezione il giorno **{data_visiva}**.")
                st.stop()
            
            max_quota = quote_dinamiche.get(gruppo_utente, 0)
            
            occupati_gruppo = 0
            for pr in prenotazioni_raw:
                u_inf = pr.get("utenti") or {}
                u_grp = u_inf.get("gruppo")
                if u_grp == gruppo_utente and not check_is_alloggi(u_inf):
                    occupati_gruppo += 1
            
            st.info(f"📊 **Quota del tuo corso ({gruppo_utente}) per oggi**: **{occupati_gruppo}/{max_quota}** posti prenotati.")
            
            if occupati_gruppo >= max_quota:
                st.error(f"❌ Limite raggiunto! Il gruppo **{gruppo_utente}** ha esaurito la quota massima di **{max_quota}** posti per oggi.")
            else:
                if st.button("Prenota Posto Auto Studenti 🚗", use_container_width=True):
                    posti_studenti = POSTI_PER_ZONA["Bassa"] + POSTI_PER_ZONA["Alta"] + POSTI_PER_ZONA["Piazzale"]
                    posto_trovato = trova_posto_libero(posti_studenti)
                    
                    if posto_trovato:
                        supabase.table("prenotazioni").insert({
                            "utente_id": utente_loggato["id"],
                            "data": data_str,
                            "posto_id": posto_trovato,
                            "turno": "TUTTO_IL_GIORNO"
                        }).execute()
                        st.success(f"🎉 Ti è stato assegnato il **Posto {posto_trovato}**!")
                        st.rerun()
                    else:
                        st.error("❌ Tutti i posti studenti sono occupati o bloccati per eventi.")

# --- 8. PANNELLO AMMINISTRATORE ---
else:
    st.divider()
    st.subheader("🛠 Pannello Amministrazione Parcheggi")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📌 Gestione Posti", 
        "💼 Assegnazione Staff & Alloggi", 
        "🎉 Gestione Eventi",
        "📅 Presenze Corsi", 
        "📋 Report & Quote"
    ])
    
    # TAB 1: GESTIONE INDIVIDUALE POSTI
    with tab1:
        colA, colB = st.columns(2)
        with colA:
            posto_admin = st.selectbox("Seleziona un Posto da gestire:", ["-- Seleziona --"] + list(POSTI.keys()))
            
        with colB:
            if posto_admin != "-- Seleziona --":
                if posto_admin in posti_bloccati_eventi:
                    info_p = posti_bloccati_eventi[posto_admin]
                    st.warning(f"Il posto **{posto_admin}** è bloccato da un Evento ({info_p['username']}) - Riservato: `{info_p['targa']}`")
                else:
                    pr_esistenti = [pr for pr in prenotazioni_raw if pr["posto_id"] == posto_admin]
                    if not pr_esistenti:
                        st.success(f"Il **Posto {posto_admin}** è LIBERO per il {data_visiva}.")
                        if st.button(f"Blocca Posto {posto_admin} ⛔", use_container_width=True):
                            supabase.table("prenotazioni").insert({
                                "utente_id": utente_loggato["id"],
                                "data": data_str,
                                "posto_id": posto_admin,
                                "turno": "TUTTO_IL_GIORNO"
                            }).execute()
                            st.success("Posto bloccato!")
                            st.rerun()
                    else:
                        occ = pr_esistenti[0]
                        u_info = occ.get("utenti") or {}
                        n_occ = u_info.get("username", "Occupato")
                        st.error(f"Occupato da: **{n_occ}**")
                        if st.button(f"Rimuovi Prenotazione 🗑️", use_container_width=True):
                            supabase.table("prenotazioni").delete().eq("id", occ["id"]).execute()
                            st.success("Prenotazione rimossa!")
                            st.rerun()

    # TAB 2: ASSEGNAZIONE STAFF & ALLOGGI
    with tab2:
        st.write("### 💼 Assegnazione Diretta Staff & Alloggiati")
        
        utenti_speciali = []
        try:
            res_u = supabase.table("utenti").select("*").execute()
            if res_u.data:
                for u in res_u.data:
                    if u.get("gruppo") == "Staff" or check_is_alloggi(u):
                        utenti_speciali.append(u)
        except Exception:
            pass

        if not utenti_speciali:
            st.warning("⚠ Nessun utente Staff o Alloggiato trovato nel sistema.")
        else:
            col_s1, col_s2 = st.columns(2)
            
            with col_s1:
                membro_scelto = st.selectbox(
                    "Seleziona Utente (Staff / Alloggiato):",
                    options=utenti_speciali,
                    format_func=lambda u: f"{u['username']} ({'Alloggi' if check_is_alloggi(u) else u.get('gruppo')}) - Targa: {u.get('targa', '-')}",
                    key="sb_staff_member"
                )
                
                modalita_assegnazione = st.radio(
                    "Modalità di Assegnazione:",
                    ["Giorni Ricorrenti", "Singola Data", "Permanente (Fissa)"],
                    key="radio_mod_staff"
                )
                
            with col_s2:
                is_membro_alloggi = check_is_alloggi(membro_scelto)
                posti_suggeriti = POSTI_PER_ZONA["Alloggi"] if is_membro_alloggi else POSTI_PER_ZONA["Staff"]
                altri_posti = [p for p in POSTI.keys() if p not in posti_suggeriti]
                
                posto_staff_scelto = st.selectbox("Seleziona Posto da Assegnare:", posti_suggeriti + altri_posti, key="sb_staff_spot")

            date_da_inserire = []
            if modalita_assegnazione == "Singola Data":
                data_singola = st.date_input("Seleziona la Data:", value=data_scelta, min_value=oggi, key="dt_staff_singola")
                date_da_inserire.append(data_singola.strftime("%Y-%m-%d"))
                
            elif modalita_assegnazione == "Permanente (Fissa)":
                st.info("📌 Il posto verrà riservato a tempo indeterminato (data speciale 2099-12-31).")
                date_da_inserire.append(DATA_PERMANENTE)
                
            else: # Giorni Ricorrenti
                giorni_selezionati = st.multiselect(
                    "Giorni della settimana:",
                    options=["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"],
                    default=["Lunedì"],
                    key="ms_giorni_staff"
                )
                
                col_p1, col_p2 = st.columns(2)
                with col_p1:
                    d_inizio = st.date_input("Data Inizio:", value=oggi, min_value=oggi, key="dt_inizio_staff")
                with col_p2:
                    d_fine = st.date_input("Data Fine:", value=oggi + datetime.timedelta(days=90), min_value=d_inizio, key="dt_fine_staff")
                
                if giorni_selezionati and d_inizio <= d_fine:
                    giorni_nums = [MAPPA_GIORNI_SETTIMANA[g] for g in giorni_selezionati]
                    curr_d = d_inizio
                    while curr_d <= d_fine:
                        if curr_d.weekday() in giorni_nums:
                            date_da_inserire.append(curr_d.strftime("%Y-%m-%d"))
                        curr_d += datetime.timedelta(days=1)

            if st.button("Conferma Assegnazione 🟢", use_container_width=True, key="btn_confirm_staff"):
                if not date_da_inserire:
                    st.error("❌ Nessuna data valida selezionata.")
                else:
                    payload = [
                        {
                            "utente_id": membro_scelto["id"],
                            "data": d_val,
                            "posto_id": posto_staff_scelto,
                            "turno": "TUTTO_IL_GIORNO"
                        }
                        for d_val in date_da_inserire
                    ]
                    supabase.table("prenotazioni").insert(payload).execute()
                    st.success(f"🎉 Posto **{posto_staff_scelto}** assegnato a **{membro_scelto['username']}**!")
                    st.rerun()

            st.divider()
            st.write("### 🗑️ Gestione e Revoca Assegnazioni Speciali")
            
            try:
                res_all_s = supabase.table("prenotazioni").select("id, data, posto_id, utente_id, utenti(*)").execute()
                if res_all_s.data:
                    for r in res_all_s.data:
                        u_i = r.get("utenti") or {}
                        dt_r = r.get("data")
                        p_r = r.get("posto_id")
                        if str(p_r).startswith("Staff") or str(p_r).startswith("Alloggi") or u_i.get("gruppo") == "Staff":
                            col_r1, col_r2, col_r3, col_r4 = st.columns([3, 2, 2, 1])
                            col_r1.write(f"👤 **{u_i.get('username')}** ({u_i.get('targa', '-')})")
                            col_r2.write(f"🅿️ Posto: **{p_r}**")
                            col_r3.write(f"📅 `{ 'PERMANENTE' if dt_r == DATA_PERMANENTE else dt_r }`")
                            if col_r4.button("❌", key=f"del_spec_{r['id']}"):
                                supabase.table("prenotazioni").delete().eq("id", r["id"]).execute()
                                st.success("Assegnazione rimossa!")
                                st.rerun()
            except Exception as ex:
                st.error(f"Errore caricamento: {ex}")

    # TAB 3: MODALITÀ EVENTI CON TESTI PER SINGOLO PARCHEGGIO
    with tab3:
        st.write("### 🎉 Modalità Eventi e Blocco Parcheggi")
        st.info("Riserva intere zone o tutti i parcheggi per eventi e inserisci per quali ospiti/persone sono riservati i singoli posti (visibili solo ad Admin e Staff).")
        
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            data_evento = st.date_input("Data Evento:", value=data_scelta, min_value=oggi, key="dt_event")
            nome_evento = st.text_input("Nome Evento:", placeholder="Es. Convegno Viticoltura / Open Day")
        
        with col_e2:
            note_evento = st.text_area("Note Generali Evento:", placeholder="Es. Riservato Relatori / Ospiti Esterni")
            blocchi_selezionati = st.multiselect(
                "Blocchi Parcheggio da Bloccare:",
                options=["TUTTI", "Bassa", "Alta", "Piazzale", "Staff", "Docenti", "Alloggi"],
                default=["TUTTI"]
            )

        # Determina i posti interessati dai blocchi selezionati
        posti_interessati = []
        if "TUTTI" in blocchi_selezionati:
            posti_interessati = list(POSTI.keys())
        else:
            for b in blocchi_selezionati:
                if b in POSTI_PER_ZONA:
                    posti_interessati.extend(POSTI_PER_ZONA[b])

        dettagli_posti = {}
        if posti_interessati:
            with st.expander("✏️ Personalizza indicazione per singoli posti (Visibili solo ad Admin e Staff)"):
                st.caption("Lascia vuoto il campo per mostrare l'indicazione generica dell'evento o 'Riservato Evento'.")
                cols_ev = st.columns(3)
                for idx, p_id in enumerate(posti_interessati):
                    c_target = cols_ev[idx % 3]
                    txt_p = c_target.text_input(f"Posto {p_id}:", key=f"inp_ev_{p_id}", placeholder="Es. Prof. Rossi")
                    if txt_p.strip():
                        dettagli_posti[p_id] = txt_p.strip()

        if st.button("Crea Evento e Blocca Parcheggi 🚫", use_container_width=True):
            if not nome_evento.strip():
                st.error("Inserisci un nome per l'evento.")
            elif not blocchi_selezionati:
                st.error("Seleziona almeno un blocco di parcheggi da riservare.")
            else:
                str_blocchi = "TUTTI" if "TUTTI" in blocchi_selezionati else ",".join(blocchi_selezionati)
                payload_ev = {
                    "data": data_evento.strftime("%Y-%m-%d"),
                    "nome_evento": nome_evento.strip(),
                    "note": note_evento.strip(),
                    "blocchi": str_blocchi,
                    "dettagli_posti": json.dumps(dettagli_posti)
                }
                try:
                    supabase.table("eventi").insert(payload_ev).execute()
                    st.success(f"🎉 Evento '{nome_evento}' creato con successo per il {data_evento.strftime('%d/%m/%Y')}!")
                    st.rerun()
                except Exception as ex_ev:
                    st.error(f"⚠️ Errore salvataggio evento: verificare che la colonna 'dettagli_posti' sia presente su Supabase. Dettaglio: {ex_ev}")

        st.divider()
        st.write("### 📋 Eventi Programmati")
        
        try:
            res_ev_all = supabase.table("eventi").select("*").gte("data", oggi.strftime("%Y-%m-%d")).order("data").execute()
            if res_ev_all.data:
                for ev in res_ev_all.data:
                    col_ev1, col_ev2, col_ev3, col_ev4 = st.columns([2, 3, 3, 1])
                    col_ev1.write(f"📅 **{ev.get('data')}**")
                    col_ev2.write(f"🎉 **{ev.get('nome_evento')}**")
                    col_ev3.write(f"🚫 Blocchi: `{ev.get('blocchi')}` | Note: {ev.get('note', '-')}")
                    if col_ev4.button("🗑️", key=f"del_ev_{ev.get('id')}"):
                        supabase.table("eventi").delete().eq("id", ev.get("id")).execute()
                        st.success("Evento eliminato!")
                        st.rerun()
                    
                    # Dettaglio indicazioni singoli posti per l'Admin
                    det_p = ev.get("dettagli_posti") or {}
                    if isinstance(det_p, str):
                        try:
                            det_p = json.loads(det_p)
                        except Exception:
                            det_p = {}
                    if isinstance(det_p, dict) and det_p:
                        with st.expander(f"🔍 Riserve per singoli posti ({len(det_p)} personalizzati)"):
                            for pk, pv in det_p.items():
                                st.write(f"- **{pk}**: {pv}")
                    st.divider()
            else:
                st.info("Nessun evento futuro programmato.")
        except Exception:
            st.info("Nessuna tabella 'eventi' trovata in Supabase o nessun evento presente.")

    # TAB 4: CALENDARIO PRESENZE CORSI
    with tab4:
        st.write(f"### 🗓️ Presenza Corsi in Lezione - {data_visiva}")
        
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
                
                if scelta != stato_curr:
                    res_chk = supabase.table("presenze_corsi").select("data, gruppo").eq("data", data_str).eq("gruppo", grp).execute()
                    
                    if res_chk.data and len(res_chk.data) > 0:
                        supabase.table("presenze_corsi").update({"stato": scelta}).eq("data", data_str).eq("gruppo", grp).execute()
                    else:
                        supabase.table("presenze_corsi").insert({
                            "data": data_str,
                            "gruppo": grp,
                            "stato": scelta
                        }).execute()
                        
                    st.success(f"Aggiornata presenza per {grp}!")
                    st.rerun()

    # TAB 5: REPORT E QUOTE
    with tab5:
        st.write("### 📊 Quote Posti Calcolate per Oggi (Esclusi Alloggiati)")
        
        df_quote = pd.DataFrame([
            {
                "Corso": grp,
                "Stato Oggi": "PRESENTE 🟢" if grp in corsi_presenti_oggi else "ASSENTE 🔴",
                "Iscritti Totali (No Alloggi)": numero_iscritti.get(grp, 0),
                "Quota Posti Auto Assegnata": quote_dinamiche.get(grp, 0) if grp in corsi_presenti_oggi else 0
            }
            for grp in GRUPPI_STUDENTI.keys()
        ])
        st.dataframe(df_quote, use_container_width=True)
        
        st.divider()
        st.write("### 📋 Download Report Excel Completo")
        try:
            risposta_t = supabase.table("prenotazioni").select("data, posto_id, utenti(*)").execute()
            if risposta_t.data:
                lista_excel = []
                for item in risposta_t.data:
                    u_info = item.get("utenti") or {}
                    p_data_raw = str(item.get("data", ""))
                    p_user = u_info.get("username", "Occupato")
                    
                    lista_excel.append({
                        "Data": "PERMANENTE" if p_data_raw == DATA_PERMANENTE else p_data_raw,
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
                    label="📥 Scarica Report Excel (.xlsx)",
                    data=buffer,
                    file_name=f"report_parcheggi_{date.today().strftime('%d_%m_%Y')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        except Exception as ex_rep:
            st.error(f"Errore creazione report: {ex_rep}")
