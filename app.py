import streamlit as st
import datetime
from datetime import date
from supabase import create_client, Client
import pandas as pd
import io
import json
import base64
import math
import re
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

# REQUISITO 1: Piazzale diventa 17 posti, Docenti diventa 7 posti.
TOTALE_POSTI_STUDENTI = 15 + 20 + 17  # 52 Posti Studenti (Bassa, Alta, Piazzale)
DATA_PERMANENTE = "2099-12-31"        # Data usata per assegnazioni fisse

POSTI_PER_ZONA = {
    "Bassa": [f"Bassa-{i}" for i in range(1, 16)],
    "Alta": [f"Alta-{i}" for i in range(1, 21)],
    "Piazzale": [f"Piazzale-{i}" for i in range(1, 18)], # 17 posti
    "Staff": [f"Staff-{i}" for i in range(1, 24)],       # 23 posti
    "Docenti": [f"Docenti-{i}" for i in range(1, 8)],     # 7 posti
    "Alloggi": [f"Alloggi-{i}" for i in range(1, 14)]     # 13 posti
}

POSTI = {}
for lista in POSTI_PER_ZONA.values():
    for p in lista:
        POSTI[p] = {}

# --- FUNZIONI UTILITY ---
def is_valid_targa_italiana(targa_str):
    """REQUISITO 4: Verifica il formato targa italiano (2 lettere, 3 numeri, 2 lettere)."""
    if not targa_str:
        return False
    pattern = r"^[A-Z]{2}\d{3}[A-Z]{2}$"
    return bool(re.match(pattern, targa_str.strip().upper()))

def check_is_alloggi(u_dict):
    """Verifica se un utente è alloggiato da vari campi possibili."""
    if not isinstance(u_dict, dict):
        return False
    if u_dict.get("is_alloggi") or u_dict.get("alloggi"):
        return True
    grp = str(u_dict.get("gruppo", ""))
    return grp.startswith("Alloggi")

# --- CALCOLO DINAMICO QUOTE & PRESENZE ---
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
    for g in corsi_pres:
        n_stud = studenti_counts.get(g, 0)
        if n_stud == 0:
            quote[g] = 0
            continue
            
        cap_carpooling = math.ceil(n_stud / 3)
        
        if totale_studenti_oggi > 0:
            q_prop = max(1, round((n_stud / totale_studenti_oggi) * TOTALE_POSTI_STUDENTI))
        else:
            q_prop = max(1, TOTALE_POSTI_STUDENTI // len(corsi_pres))
            
        quote[g] = min(q_prop, cap_carpooling)
        
    return quote, corsi_pres, studenti_counts

def get_eventi_giorno(data_str):
    try:
        res = supabase.table("eventi").select("*").eq("data", data_str).execute()
        return res.data if res.data else []
    except Exception:
        return []

def get_posti_bloccati_evento(data_str, is_staff_or_admin=False):
    eventi = get_eventi_giorno(data_str)
    bloccati = {}
    for ev in eventi:
        ev_id = ev.get("id")
        ev_nome = ev.get("nome_evento", "Evento")
        ev_note = ev.get("note", "")
        ev_blocchi = ev.get("blocchi", "TUTTI")
        
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
                testo_specifico = ev_dettagli.get(p_id, "").strip()
                if not testo_specifico:
                    testo_specifico = ev_note if ev_note else "Riservato Evento"

                targa_visibile = testo_specifico if is_staff_or_admin else "Riservato Evento"

                bloccati[p_id] = {
                    "id_prenotazione": f"ev_{ev_id}",
                    "utente_id": None,
                    "username": f"🎉 {ev_nome}",
                    "targa": targa_visibile,
                    "gruppo": "EVENTO",
                    "turno": "TUTTO_IL_GIORNO",
                    "is_mine": False
                }
    return bloccati

# REQUISITO 7: Risoluzione concorrenza per prenotazioni simultanee
def prenotazione_atomica_sicura(utente_id, data_target, lista_candidati, testo_turno):
    """
    Controllo istantaneo in tempo reale del DB prima di inserire.
    Evita conflitti se due utenti cliccano insieme.
    """
    try:
        res_current = supabase.table("prenotazioni").select("posto_id").eq("data", data_target).execute()
        occupati_ora = set(r["posto_id"] for r in res_current.data) if res_current.data else set()
    except Exception:
        occupati_ora = set()

    for p_cand in lista_candidati:
        if p_cand in occupati_ora:
            continue  # Posto appena preso da altro utente, salta
        
        try:
            # Tenta inserimento
            supabase.table("prenotazioni").insert({
                "utente_id": utente_id,
                "data": data_target,
                "posto_id": p_cand,
                "turno": testo_turno
            }).execute()
            return True, p_cand
        except Exception:
            continue  # Se fallisce per vincolo di duplicato, tenta col prossimo
            
    return False, None

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
username = str(utente_loggato.get("username") or "")
gruppo_utente = str(utente_loggato.get("gruppo") or "Marketing 1")
targa_utente = str(utente_loggato.get("targa") or "")

is_admin = (username.lower() == "admin")
is_segreteria = (username.lower() == "segreteria" or gruppo_utente.lower() == "segreteria")
is_admin_or_segreteria = is_admin or is_segreteria
is_staff_or_admin = is_admin_or_segreteria or (gruppo_utente == "Staff")
is_alloggi_user = check_is_alloggi(utente_loggato)
is_student = (not is_admin_or_segreteria) and (gruppo_utente in GRUPPI_STUDENTI)

# --- SIDEBAR DI CONTROLLO & GESTIONE ---
st.sidebar.header("👤 Account")
st.sidebar.write(f"Utente: **{username}**")
st.sidebar.write(f"Ruolo/Corso: **{gruppo_utente}**")
if is_alloggi_user:
    st.sidebar.info("🏠 **Residente Alloggi**")

# REQUISITO 4: Controllo Validità Targa Italiana
targa_valida = is_valid_targa_italiana(targa_utente)
if targa_valida:
    st.sidebar.success(f"Targa: **{targa_utente}** 🟢")
else:
    st.sidebar.error("Targa: **Non valida o mancante!** 🔴")

# Modifica Targa
with st.sidebar.expander("✏️ Modifica la tua Targa (Formato IT)"):
    st.caption("Esempio valido: **AA123BB** (2 lettere, 3 cifre, 2 lettere)")
    nuova_targa = st.text_input("Nuova Targa:", value=targa_utente, key="input_targa")
    if st.button("Salva Targa 💾", use_container_width=True):
        t_clean = nuova_targa.strip().upper()
        if not is_valid_targa_italiana(t_clean):
            st.error("❌ Formato targa non valido! Inserisci 2 lettere, 3 cifre e 2 lettere (es. AA123BB).")
        else:
            supabase.table("utenti").update({"targa": t_clean}).eq("id", utente_loggato["id"]).execute()
            st.session_state["utente_autenticato"]["targa"] = t_clean
            st.success("Targa aggiornata con successo!")
            st.rerun()

# Cambio Password
with st.sidebar.expander("🔑 Modifica Password"):
    old_pwd = st.text_input("Password Attuale:", type="password", key="pwd_old")
    new_pwd = st.text_input("Nuova Password:", type="password", key="pwd_new")
    conf_pwd = st.text_input("Conferma Password:", type="password", key="pwd_conf")
    if st.button("Aggiorna Password 💾", use_container_width=True):
        if old_pwd != utente_loggato.get("password"):
            st.error("❌ La password attuale non è corretta.")
        elif not new_pwd or new_pwd != conf_pwd:
            st.error("❌ Le nuove password non coincidono o sono vuote.")
        else:
            supabase.table("utenti").update({"password": new_pwd}).eq("id", utente_loggato["id"]).execute()
            st.session_state["utente_autenticato"]["password"] = new_pwd
            st.success("🎉 Password aggiornata!")
            st.rerun()

st.sidebar.divider()
st.sidebar.subheader("📅 Seleziona Giorno")
oggi = date.today()

max_data = oggi + datetime.timedelta(days=14) if (not is_admin_or_segreteria and not is_alloggi_user) else oggi + datetime.timedelta(days=365)

data_scelta = st.sidebar.date_input("Data:", min_value=oggi, max_value=max_data, format="DD/MM/YYYY")
data_str = data_scelta.strftime("%Y-%m-%d")
data_visiva = data_scelta.strftime("%d/%m/%Y")

if st.sidebar.button("Log out ❌", use_container_width=True):
    st.session_state["utente_autenticato"] = None
    st.rerun()

# --- 4. RECUPERO PRENOTAZIONI DAL DATABASE ---
prenotazioni_raw = []
try:
    resp_p = supabase.table("prenotazioni").select("id, posto_id, utente_id, data, turno, utenti(*)").in_("data", [data_str, DATA_PERMANENTE]).execute()
    if resp_p.data:
        prenotazioni_raw = resp_p.data
except Exception:
    try:
        resp_p = supabase.table("prenotazioni").select("id, posto_id, utente_id, data, turno, utenti!fk_prenotazioni_utenti(*)").in_("data", [data_str, DATA_PERMANENTE]).execute()
        if resp_p.data:
            prenotazioni_raw = resp_p.data
    except Exception:
        pass

# --- 5. PREPARAZIONE DATI PER MAPPA CON PRIVACY & EVIDENZIAZIONE POSTO ---
posti_bloccati_eventi = get_posti_bloccati_evento(data_str, is_staff_or_admin=is_staff_or_admin)
prenotazioni_visibili = {}

# Inserisci blocchi eventi
for p_id, info_ev in posti_bloccati_eventi.items():
    prenotazioni_visibili[p_id] = info_ev

# Inserisci prenotazioni reali DB
for p in prenotazioni_raw:
    p_id = p.get("posto_id")
    if p_id and p_id not in posti_bloccati_eventi:
        u_id = p.get("utente_id")
        info_u = p.get("utenti") or {}
        u_grp = info_u.get("gruppo", "")
        u_name = info_u.get("username", "Occupato")
        
        # REQUISITO 2: Identifica se la prenotazione è dell'utente loggato
        is_own_booking = (u_id == utente_loggato.get("id"))
        is_staff_spot = str(p_id).startswith("Staff") or u_grp == "Staff"
        is_alloggi_spot = str(p_id).startswith("Alloggi") or check_is_alloggi(info_u)
        
        # Gestione testo passeggeri da turno
        turno_val = str(p.get("turno", ""))
        txt_pass = ""
        if "| Con:" in turno_val:
            txt_pass = turno_val.split("| Con:")[1].strip()

        # REQUISITO 3: Privacy Studenti
        if is_student and not is_own_booking:
            targa_disp = "-"
            if u_grp == gruppo_utente:
                username_disp = u_name
                gruppo_disp = u_grp
            else:
                username_disp = "Occupato"
                gruppo_disp = "Altro Corso"
        elif is_staff_spot and not is_staff_or_admin:
            username_disp = "Staff"
            targa_disp = "-"
            gruppo_disp = "Staff"
        else:
            username_disp = u_name
            targa_disp = info_u.get("targa", "-")
            gruppo_disp = u_grp

        prenotazioni_visibili[p_id] = {
            "id_prenotazione": p.get("id"),
            "utente_id": u_id,
            "username": username_disp,
            "targa": targa_disp,
            "gruppo": gruppo_disp,
            "turno": "TUTTO_IL_GIORNO",
            "is_mine": is_own_booking,                     # REQUISITO 2: Evidenzia posto
            "is_alloggi": is_alloggi_spot,                 # REQUISITO 6: Colore Alloggi
            "passeggeri": txt_pass                         # REQUISITO 5: Passeggeri
        }

# REQUISITO 3: Gli studenti vedono le zone no-studenti SEMPRE come "Riservato Zona" (Grigio)
if is_student:
    zone_non_studenti = POSTI_PER_ZONA["Staff"] + POSTI_PER_ZONA["Docenti"] + POSTI_PER_ZONA["Alloggi"]
    for p_id in zone_non_studenti:
        prenotazioni_visibili[p_id] = {
            "id_prenotazione": None,
            "utente_id": None,
            "username": "Riservato Zona",
            "targa": "-",
            "gruppo": "RISERVATO",
            "turno": "TUTTO_IL_GIORNO",
            "is_mine": False
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

def ottieni_posti_liberi_zona(prefisso_lista):
    """Restituisce la lista di posti attualmente non bloccati da eventi."""
    posti_liberi = []
    for p in prefisso_lista:
        if p in posti_bloccati_eventi:
            continue
        prenotazioni_posto = [pr for pr in prenotazioni_raw if pr["posto_id"] == p]
        if not prenotazioni_posto:
            posti_liberi.append(p)
    return posti_liberi

if not is_admin_or_segreteria:
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

        # REQUISITO 4: Controllo Targa Obbligatoria prima di mostrare i form
        if not targa_valida:
            st.error("⚠️ **TARGA NON IMPOSTATA O NON VALIDA!**")
            st.info("Per poter prenotare un posto auto devi registrare una targa italiana valida (es. **AA123BB** - 2 lettere, 3 cifre, 2 lettere) nella barra laterale a sinistra.")
            st.stop()

        if is_alloggi_user:
            st.info("🏠 **Sei un utente residente negli Alloggi.** I posti parcheggio alloggiati vengono assegnati direttamente dall'Amministrazione. Non hai ancora un posto assegnato per questa data.")

        elif gruppo_utente in ["Staff", "Segreteria"]:
            st.info("ℹ️ Come membro dello Staff / Segreteria puoi riservare un posto giornaliero o permanente.")
            candidati_staff = ottieni_posti_liberi_zona(POSTI_PER_ZONA["Staff"])
            tipo_staff = st.radio("Tipo Assegnazione:", ["Giornaliera", "Permanente (Fissa)"])
            
            if candidati_staff:
                if st.button(f"Conferma Assegnazione Posto ({candidati_staff[0]}) 🟢", use_container_width=True):
                    d_save = DATA_PERMANENTE if tipo_staff == "Permanente (Fissa)" else data_str
                    ok, p_assegnato = prenotazione_atomica_sicura(utente_loggato["id"], d_save, candidati_staff, "TUTTO_IL_GIORNO")
                    if ok:
                        st.success(f"Posto **{p_assegnato}** riservato con successo!")
                        st.rerun()
                    else:
                        st.error("❌ I posti liberi sono stati appena occupati. Riprova.")
            else:
                st.error("❌ Nessun Posto Staff libero per oggi.")

        elif gruppo_utente == "Docenti":
            candidati_doc = ottieni_posti_liberi_zona(POSTI_PER_ZONA["Docenti"])
            if candidati_doc:
                if st.button(f"Prenota Posto Docenti ({candidati_doc[0]}) 🟢", use_container_width=True):
                    ok, p_assegnato = prenotazione_atomica_sicura(utente_loggato["id"], data_str, candidati_doc, "TUTTO_IL_GIORNO")
                    if ok:
                        st.success(f"Posto **{p_assegnato}** prenotato con successo!")
                        st.rerun()
                    else:
                        st.error("❌ Nessun posto libero disponibile. Riprova.")
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
            
            st.info(f"📊 **Quota del tuo corso ({gruppo_utente}) per oggi**: **{occupati_gruppo}/{max_quota}** posti auto (regola min 3 persone/auto).")
            
            # REQUISITO 5: Inserimento Passeggeri
            passeggeri_input = st.text_input("👥 Con chi sei in auto? (Passeggeri/Note opzionali):", placeholder="Es. Mario Rossi, Luca Bianchi")

            if occupati_gruppo >= max_quota:
                st.error(f"❌ Limite raggiunto! Il gruppo **{gruppo_utente}** ha esaurito la quota massima di **{max_quota}** auto per oggi.")
            else:
                if st.button("Prenota Posto Auto Studenti 🚗", use_container_width=True):
                    candidati_studenti = ottieni_posti_liberi_zona(POSTI_PER_ZONA["Bassa"] + POSTI_PER_ZONA["Alta"] + POSTI_PER_ZONA["Piazzale"])
                    
                    if candidati_studenti:
                        txt_turno = f"TUTTO_IL_GIORNO | Con: {passeggeri_input.strip()}" if passeggeri_input.strip() else "TUTTO_IL_GIORNO"
                        
                        # REQUISITO 7: Esecuzione atomica sicura contro doppie prenotazioni
                        ok, p_assegnato = prenotazione_atomica_sicura(utente_loggato["id"], data_str, candidati_studenti, txt_turno)
                        
                        if ok:
                            st.success(f"🎉 Ti è stato assegnato il **Posto {p_assegnato}**!")
                            st.rerun()
                        else:
                            st.error("❌ Tutti i posti disponibili sono stati appena prenotati da altri utenti. Riprova.")
                    else:
                        st.error("❌ Tutti i posti studenti sono occupati o bloccati per eventi.")

# --- 8. PANNELLO AMMINISTRAZIONE & SEGRETERIA ---
else:
    st.divider()
    st.subheader("🛠 Pannello Amministrazione & Segreteria Parcheggi")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📌 Gestione Posti", 
        "💼 Assegnazione Staff & Alloggi", 
        "🎉 Gestione Eventi",
        "📅 Presenze Corsi", 
        "📋 Report & Quote"
    ])
    
    # TAB 1: GESTIONE INDIVIDUALE POSTI & SPOSTAMENTI
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

        st.divider()
        st.write("### ↔️ Sposta una Prenotazione Esistente")
        prenotazioni_spostabili = [pr for pr in prenotazioni_raw if pr.get("posto_id")]
        if prenotazioni_spostabili:
            col_mv1, col_mv2, col_mv3 = st.columns(3)
            with col_mv1:
                p_sposta = st.selectbox(
                    "Seleziona Prenotazione da spostare:",
                    options=prenotazioni_spostabili,
                    format_func=lambda x: f"Posto {x['posto_id']} - {(x.get('utenti') or {}).get('username', 'Occupato')}",
                    key="sb_mv_p"
                )
            with col_mv2:
                posti_occupati_oggi = set(pr["posto_id"] for pr in prenotazioni_raw) | set(posti_bloccati_eventi.keys())
                posti_liberi = [p for p in POSTI.keys() if p not in posti_occupati_oggi]
                nuovo_posto_target = st.selectbox("Seleziona Nuovo Posto:", posti_liberi, key="sb_mv_target")
            with col_mv3:
                st.write("")
                st.write("")
                if st.button("Sposta Prenotazione 🔄", use_container_width=True):
                    if nuovo_posto_target:
                        supabase.table("prenotazioni").update({"posto_id": nuovo_posto_target}).eq("id", p_sposta["id"]).execute()
                        st.success(f"Prenotazione spostata dal posto {p_sposta['posto_id']} al posto {nuovo_posto_target}!")
                        st.rerun()
                    else:
                        st.error("Nessun posto libero disponibile.")
        else:
            st.info("Nessuna prenotazione attiva da spostare per questa data.")

    # TAB 2: ASSEGNAZIONE STAFF & ALLOGGI
    with tab2:
        st.write("### 💼 Assegnazione Diretta Staff & Alloggiati")
        utenti_speciali = []
        try:
            res_u = supabase.table("utenti").select("*").execute()
            if res_u.data:
                for u in res_u.data:
                    if u.get("gruppo") in ["Staff", "Segreteria"] or check_is_alloggi(u):
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
                modalita_assegnazione = st.radio("Modalità di Assegnazione:", ["Giorni Ricorrenti", "Singola Data", "Permanente (Fissa)"], key="radio_mod_staff")
                
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
                date_da_inserire.append(DATA_PERMANENTE)
            else:
                giorni_selezionati = st.multiselect("Giorni della settimana:", options=["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"], default=["Lunedì"], key="ms_giorni_staff")
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
                    payload = [{"utente_id": membro_scelto["id"], "data": d_val, "posto_id": posto_staff_scelto, "turno": "TUTTO_IL_GIORNO"} for d_val in date_da_inserire]
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
                        if str(p_r).startswith("Staff") or str(p_r).startswith("Alloggi") or u_i.get("gruppo") in ["Staff", "Segreteria"]:
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

    # TAB 3: GESTIONE EVENTI
    with tab3:
        st.write("### 🎉 Modalità Eventi e Blocco Parcheggi")
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            data_evento = st.date_input("Data Evento:", value=data_scelta, min_value=oggi, key="dt_event")
            nome_evento = st.text_input("Nome Evento:", placeholder="Es. Convegno Viticoltura / Open Day")
        with col_e2:
            note_evento = st.text_area("Note Generali Evento:", placeholder="Es. Riservato Relatori / Ospiti Esterni")
            blocchi_selezionati = st.multiselect("Blocchi Parcheggio da Bloccare:", options=["TUTTI", "Bassa", "Alta", "Piazzale", "Staff", "Docenti", "Alloggi"], default=["TUTTI"])

        posti_interessati = list(POSTI.keys()) if "TUTTI" in blocchi_selezionati else [p for b in blocchi_selezionati if b in POSTI_PER_ZONA for p in POSTI_PER_ZONA[b]]
        dettagli_posti = {}
        if posti_interessati:
            with st.expander("✏️ Personalizza indicazione per singoli posti"):
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
                st.error("Seleziona almeno un blocco di parcheggi.")
            else:
                str_blocchi = "TUTTI" if "TUTTI" in blocchi_selezionati else ",".join(blocchi_selezionati)
                supabase.table("eventi").insert({
                    "data": data_evento.strftime("%Y-%m-%d"),
                    "nome_evento": nome_evento.strip(),
                    "note": note_evento.strip(),
                    "blocchi": str_blocchi,
                    "dettagli_posti": json.dumps(dettagli_posti)
                }).execute()
                st.success(f"🎉 Evento '{nome_evento}' creato!")
                st.rerun()

        st.divider()
        st.write("### 📋 Eventi Programmati")
        try:
            res_ev_all = supabase.table("eventi").select("*").gte("data", oggi.strftime("%Y-%m-%d")).order("data").execute()
            if res_ev_all.data:
                for ev in res_ev_all.data:
                    ev_id = ev.get("id")
                    col_ev1, col_ev2, col_ev3, col_ev4 = st.columns([2, 3, 3, 1])
                    col_ev1.write(f"📅 **{ev.get('data')}**")
                    col_ev2.write(f"🎉 **{ev.get('nome_evento')}**")
                    col_ev3.write(f"🚫 Blocchi: `{ev.get('blocchi')}`")
                    if col_ev4.button("🗑️", key=f"del_ev_{ev_id}"):
                        supabase.table("eventi").delete().eq("id", ev_id).execute()
                        st.success("Evento eliminato!")
                        st.rerun()
        except Exception:
            pass

    # TAB 4: PRESENZE CORSI
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
                scelta = st.radio(f"**{grp}**:", ["PRESENTE", "ASSENTE"], index=0 if stato_curr == "PRESENTE" else 1, key=f"pres_{grp}_{data_str}", horizontal=True)
                if scelta != stato_curr:
                    res_chk = supabase.table("presenze_corsi").select("data, gruppo").eq("data", data_str).eq("gruppo", grp).execute()
                    if res_chk.data:
                        supabase.table("presenze_corsi").update({"stato": scelta}).eq("data", data_str).eq("gruppo", grp).execute()
                    else:
                        supabase.table("presenze_corsi").insert({"data": data_str, "gruppo": grp, "stato": scelta}).execute()
                    st.success(f"Aggiornata presenza per {grp}!")
                    st.rerun()

    # TAB 5: REPORT E QUOTE
    with tab5:
        st.write("### 📊 Quote Posti Calcolate per Oggi (Carpooling Applicato)")
        df_quote = pd.DataFrame([{
            "Corso": grp,
            "Stato Oggi": "PRESENTE 🟢" if grp in corsi_presenti_oggi else "ASSENTE 🔴",
            "Iscritti (No Alloggi)": numero_iscritti.get(grp, 0),
            "Quota Max Auto": quote_dinamiche.get(grp, 0) if grp in corsi_presenti_oggi else 0
        } for grp in GRUPPI_STUDENTI.keys()])
        st.dataframe(df_quote, use_container_width=True)
        
        st.divider()
        st.write("### 📋 Download Report Excel")
        tipo_report = st.radio("Ambito report:", ["Report Giornaliero (Data selezionata)", "Report Completo (Tutti i dati)"], horizontal=True)
        
        if st.button("Genera e Scarica Report Excel 📥", use_container_width=True):
            try:
                if "Giornaliero" in tipo_report:
                    risposta_t = supabase.table("prenotazioni").select("data, posto_id, turno, utenti(*)").in_("data", [data_str, DATA_PERMANENTE]).execute()
                else:
                    risposta_t = supabase.table("prenotazioni").select("data, posto_id, turno, utenti(*)").execute()
                
                if risposta_t.data:
                    lista_excel = []
                    for item in risposta_t.data:
                        u_info = item.get("utenti") or {}
                        p_data_raw = str(item.get("data", ""))
                        p_user = u_info.get("username", "Occupato")
                        
                        t_val = str(item.get("turno", ""))
                        pass_txt = t_val.split("| Con:")[1].strip() if "| Con:" in t_val else "-"

                        lista_excel.append({
                            "Data": "PERMANENTE" if p_data_raw == DATA_PERMANENTE else p_data_raw,
                            "Posto": item.get("posto_id"),
                            "Utente": "BLOCCATO (Admin)" if p_user.lower() == 'admin' else p_user,
                            "Gruppo": u_info.get("gruppo", "-") if p_user.lower() != 'admin' else "-",
                            "Targa": u_info.get("targa", "-") if p_user.lower() != 'admin' else "-",
                            "Passeggeri/Note": pass_txt
                        })
                    
                    df_excel = pd.DataFrame(lista_excel)
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_excel.to_excel(writer, index=False, sheet_name='Prenotazioni')
                    buffer.seek(0)
                    
                    st.download_button(
                        label="⬇️ Scarica File Excel",
                        data=buffer,
                        file_name=f"report_parcheggi_{data_str}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
            except Exception as ex_rep:
                st.error(f"Errore creazione report: {ex_rep}")
