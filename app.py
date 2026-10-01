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
DATA_PERMANENTE = "2099-12-31"        # Data usata per assegnazioni fisse Staff

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

# Gruppi limitati a 14 giorni di anticipo
gruppi_con_finestra = list(GRUPPI_STUDENTI.keys()) + ["Alloggi", "Alloggi 1", "Alloggi 2"]
max_data = oggi + datetime.timedelta(days=14) if (gruppo_utente in gruppi_con_finestra and not is_admin) else oggi + datetime.timedelta(days=365)

data_scelta = st.sidebar.date_input("Data:", min_value=oggi, max_value=max_data, format="DD/MM/YYYY")
data_str = data_scelta.strftime("%Y-%m-%d")
data_visiva = data_scelta.strftime("%d/%m/%Y")

fascia_visualizza = st.sidebar.selectbox("Fascia oraria da vedere:", ["Tutto il Giorno", "Mattino", "Pomeriggio"])

if st.sidebar.button("Log out ❌", use_container_width=True):
    st.session_state["utente_autenticato"] = None
    st.rerun()

# Pulizia vecchi dati (3 giorni fa, escludendo le assegnazioni permanenti)
try:
    data_limite = oggi - datetime.timedelta(days=3)
    supabase.table("prenotazioni").delete().lt("data", data_limite.strftime("%Y-%m-%d")).neq("data", DATA_PERMANENTE).execute()
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
prenotazioni_raw = []

try:
    resp_p = supabase.table("prenotazioni").select("id, posto_id, utente_id, data, turno, utenti(username, targa, gruppo)").in_("data", [data_str, DATA_PERMANENTE]).execute()
    if resp_p.data:
        prenotazioni_raw = resp_p.data
except Exception:
    resp_p = supabase.table("prenotazioni").select("id, posto_id, utente_id, data, utenti(username, targa, gruppo)").in_("data", [data_str, DATA_PERMANENTE]).execute()
    if resp_p.data:
        for p in resp_p.data:
            p["turno"] = "TUTTO_IL_GIORNO"
        prenotazioni_raw = resp_p.data

def occupato_in_fascia(prenotazioni_posto, fascia_target):
    for p in prenotazioni_posto:
        t = p.get("turno", "TUTTO_IL_GIORNO") or "TUTTO_IL_GIORNO"
        if t == "TUTTO_IL_GIORNO":
            return p
        if fascia_target == "Tutto il Giorno":
            return p
        if t == fascia_target:
            return p
    return None

# --- 6. PREPARAZIONE DATI PER MAPPA CON PRIVACY PER LO STAFF ---
prenotazioni_visibili = {}
for p in prenotazioni_raw:
    p_id = p.get("posto_id")
    p_turno = p.get("turno") or "TUTTO_IL_GIORNO"
    
    if fascia_visualizza == "Tutto il Giorno" or p_turno == "TUTTO_IL_GIORNO" or p_turno == fascia_visualizza:
        if p_id and p_id not in prenotazioni_visibili:
            info_u = p.get("utenti") or {}
            
            # Verifica se è un posto Staff o prenotato da un membro Staff
            is_staff_spot = str(p_id).startswith("Staff") or info_u.get("gruppo") == "Staff"
            
            # MASCHERAMENTO DATO: Studenti e Alloggi vedono solo "Staff"
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
                "turno": p_turno
            }

# --- 7. MAPPA INTERATTIVA ---
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

# --- 8. LOGICA PRENOTAZIONI UTENTI ---
st.divider()

quote_dinamiche, corsi_presenti_oggi, numero_iscritti = calcola_quote_posti(data_scelta)

if not is_admin:
    mie_prenotazioni = [p for p in prenotazioni_raw if p["utente_id"] == utente_loggato["id"]]
    
    if mie_prenotazioni:
        st.warning("🏷️ Hai già le seguenti prenotazioni per questo giorno:")
        for mp in mie_prenotazioni:
            f_str = mp.get("turno") or "TUTTO_IL_GIORNO"
            st.write(f"- **Posto {mp['posto_id']}** ({f_str})")
            if st.button(f"Cancella Prenotazione {mp['posto_id']} ({f_str}) ❌", key=f"del_{mp['id']}"):
                supabase.table("prenotazioni").delete().eq("id", mp["id"]).execute()
                st.success("Prenotazione annullata!")
                st.rerun()
    else:
        st.subheader("📌 Prenota il tuo Posto Auto")
        
        turno_richiesto = st.radio(
            "Seleziona la fascia oraria di cui hai bisogno:",
            ["Mattino", "Pomeriggio", "Tutto il Giorno"],
            horizontal=True
        )
        
        mappa_turno_db = {
            "Mattino": "MATTINO",
            "Pomeriggio": "POMERIGGIO",
            "Tutto il Giorno": "TUTTO_IL_GIORNO"
        }
        turno_db = mappa_turno_db[turno_richiesto]

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
                    data_insert = {
                        "utente_id": utente_loggato["id"],
                        "data": d_save,
                        "posto_id": posto_trovato,
                        "turno": turno_db
                    }
                    supabase.table("prenotazioni").insert(data_insert).execute()
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

        # CASO ALLOGGI (GESTIONE SOTTOGRUPPI 1 E 2)
        elif gruppo_utente in ["Alloggi", "Alloggi 1", "Alloggi 2"]:
            giorni_consentiti_alloggi = {
                "Alloggi 1": [0, 1, 2],  # Lunedì, Martedì, Mercoledì
                "Alloggi 2": [3, 4],     # Giovedì, Venerdì
                "Alloggi": [0, 1, 2, 3, 4] # Fallback
            }
            
            giorni_ok = giorni_consentiti_alloggi.get(gruppo_utente, [0, 1, 2, 3, 4])
            giorno_settimana = data_scelta.weekday()
            
            if giorno_settimana not in giorni_ok:
                str_giorni = "Lunedì, Martedì e Mercoledì" if gruppo_utente == "Alloggi 1" else "Giovedì e Venerdì"
                st.error(f"❌ Il gruppo **{gruppo_utente}** può prenotare un posto alloggi solo per i giorni: **{str_giorni}**.")
            else:
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
            
            occupati_gruppo = 0
            for pr in prenotazioni_raw:
                u_grp = (pr.get("utenti") or {}).get("gruppo")
                if u_grp == gruppo_utente:
                    t_pr = pr.get("turno") or "TUTTO_IL_GIORNO"
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

# --- 9. PANNELLO AMMINISTRATORE ---
else:
    st.divider()
    st.subheader("🛠️ Pannello Amministrazione Parcheggi")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📌 Gestione Posti", 
        "💼 Assegnazione Staff", 
        "📅 Presenze Corsi (Calendario)", 
        "📋 Report & Quote"
    ])
    
    # TAB 1: GESTIONE GENERALE POSTI
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
                    st.error(f"Occupato da: **{n_occ}** ({occ.get('turno', 'TUTTO_IL_GIORNO')})")
                    if st.button(f"Rimuovi Prenotazione 🗑️", use_container_width=True):
                        supabase.table("prenotazioni").delete().eq("id", occ["id"]).execute()
                        st.success("Prenotazione rimossa!")
                        st.rerun()

    # TAB 2: ASSEGNAZIONE RICORRENTE & REVOCA STAFF
    with tab2:
        st.write("### 💼 Assegnazione Diretta Posti Staff")
        st.info("Assegna posti Staff per un singolo giorno, per giorni ricorrenti (es. tutti i Giovedì) o in modo permanente.")
        
        utenti_staff = []
        try:
            res_s = supabase.table("utenti").select("id, username, targa").eq("gruppo", "Staff").execute()
            if res_s.data:
                utenti_staff = res_s.data
        except Exception:
            pass

        if not utenti_staff:
            st.warning("⚠ Nessun utente appartenente al gruppo 'Staff' trovato nel database.")
        else:
            col_s1, col_s2 = st.columns(2)
            
            with col_s1:
                membro_scelto = st.selectbox(
                    "Seleziona Membro Staff:",
                    options=utenti_staff,
                    format_func=lambda u: f"{u['username']} (Targa: {u.get('targa', '-')})",
                    key="sb_staff_member"
                )
                
                modalita_assegnazione = st.radio(
                    "Modalità di Assegnazione:",
                    ["Giorni Ricorrenti (es. tutti i Giovedì)", "Singola Data", "Permanente (Fissa)"],
                    key="radio_mod_staff"
                )
                
            with col_s2:
                posti_staff_lista = [f"Staff-{i}" for i in range(1, 23)]
                posto_staff_scelto = st.selectbox("Seleziona Posto Staff:", posti_staff_lista, key="sb_staff_spot")
                turno_staff_scelto = st.selectbox("Fascia Oraria Staff:", ["TUTTO_IL_GIORNO", "MATTINO", "POMERIGGIO"], key="sb_staff_turno")

            date_da_inserire = []
            
            if modalita_assegnazione == "Singola Data":
                data_singola = st.date_input("Seleziona la Data:", value=data_scelta, min_value=oggi, key="dt_staff_singola")
                date_da_inserire.append(data_singola.strftime("%Y-%m-%d"))
                
            elif modalita_assegnazione == "Permanente (Fissa)":
                st.info("📌 Il posto verrà riservato a tempo indeterminato (data speciale 2099-12-31).")
                date_da_inserire.append(DATA_PERMANENTE)
                
            else: # Giorni Ricorrenti
                st.write("**Seleziona i Giorni e il Periodo di Assegnazione:**")
                giorni_selezionati = st.multiselect(
                    "Giorni della settimana:",
                    options=["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"],
                    default=["Giovedì"],
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
                    st.caption(f"🗓️️ Verranno generate **{len(date_da_inserire)}** prenotazioni nell'intervallo selezionato.")

            if st.button("Assegna Posto Staff 🟢", use_container_width=True, key="btn_confirm_staff"):
                if not date_da_inserire:
                    st.error("❌ Nessuna data valida selezionata per l'assegnazione.")
                else:
                    try:
                        res_check = supabase.table("prenotazioni").select("data, posto_id, turno").eq("posto_id", posto_staff_scelto).in_("data", date_da_inserire).execute()
                        gia_occupate = [r["data"] for r in (res_check.data or []) if occupato_in_fascia([r], turno_staff_scelto)]
                    except Exception:
                        gia_occupate = []
                    
                    date_valide = [d for d in date_da_inserire if d not in gia_occupate]
                    
                    if gia_occupate:
                        st.warning(f"⚠️ Il posto **{posto_staff_scelto}** era già occupato in {len(gia_occupate)} date. Verrà assegnato solo per le date libere.")
                    
                    if date_valide:
                        payload = [
                            {
                                "utente_id": membro_scelto["id"],
                                "data": d_val,
                                "posto_id": posto_staff_scelto,
                                "turno": turno_staff_scelto
                            }
                            for d_val in date_valide
                        ]
                        supabase.table("prenotazioni").insert(payload).execute()
                        st.success(f"🎉 Assegnato il posto **{posto_staff_scelto}** a **{membro_scelto['username']}** per **{len(date_valide)}** giorni!")
                        st.rerun()
                    else:
                        st.error("❌ Nessuna data disponibile (tutte le date risultano già occupate per quel posto/turno).")

            st.divider()
            
            # --- SEZIONE GESTIONE E CANCELLAZIONE ASSEGNAZIONI STAFF ---
            st.write("### 🗑️ Gestione e Revoca Assegnazioni Staff")
            
            col_del1, col_del2 = st.columns(2)
            with col_del1:
                filtro_utente_del = st.selectbox(
                    "Filtra per Utente Staff da visualizzare/cancellare:",
                    options=["-- Tutti --"] + [u["username"] for u in utenti_staff],
                    key="sb_filtro_del_staff"
                )
            
            with col_del2:
                if filtro_utente_del != "-- Tutti --":
                    if st.button(f"Revoca TUTTE le prenotazioni di {filtro_utente_del} ⚠️", key="btn_del_all_user"):
                        u_target = next((u for u in utenti_staff if u["username"] == filtro_utente_del), None)
                        if u_target:
                            supabase.table("prenotazioni").delete().eq("utente_id", u_target["id"]).execute()
                            st.success(f"Tutte le assegnazioni di {filtro_utente_del} sono state revocate con successo!")
                            st.rerun()

            try:
                res_all_staff = supabase.table("prenotazioni").select("id, data, posto_id, turno, utente_id, utenti(username, targa, gruppo)").execute()
                staff_rows = []
                if res_all_staff.data:
                    for row in res_all_staff.data:
                        u_inf = row.get("utenti") or {}
                        if u_inf.get("gruppo") == "Staff" or str(row.get("posto_id")).startswith("Staff"):
                            if filtro_utente_del == "-- Tutti --" or u_inf.get("username") == filtro_utente_del:
                                dt_str = row.get("data")
                                staff_rows.append({
                                    "id": row["id"],
                                    "Utente": u_inf.get("username", "-"),
                                    "Targa": u_inf.get("targa", "-"),
                                    "Posto": row.get("posto_id"),
                                    "Data": "PERMANENTE" if dt_str == DATA_PERMANENTE else dt_str,
                                    "Fascia": row.get("turno", "TUTTO_IL_GIORNO")
                                })
                
                if staff_rows:
                    st.write(f"Trovate **{len(staff_rows)}** assegnazioni attive:")
                    
                    for row_s in staff_rows:
                        col_r1, col_r2, col_r3, col_r4, col_r5 = st.columns([2, 2, 2, 2, 1])
                        col_r1.write(f"👤 **{row_s['Utente']}** ({row_s['Targa']})")
                        col_r2.write(f"🅿️ Posto: **{row_s['Posto']}**")
                        col_r3.write(f"📅 Data: `{row_s['Data']}`")
                        col_r4.write(f"🕒 {row_s['Fascia']}")
                        if col_r5.button("❌", key=f"del_staff_{row_s['id']}"):
                            supabase.table("prenotazioni").delete().eq("id", row_s["id"]).execute()
                            st.success(f"Assegnazione {row_s['Posto']} rimossa!")
                            st.rerun()
                else:
                    st.info("Nessuna assegnazione Staff trovata con i filtri correnti.")
            except Exception as ex:
                st.error(f"Errore caricamento assegnazioni staff: {ex}")

    # TAB 3: CALENDARIO PRESENZE CORSI
    with tab3:
        st.write(f"### 🗓️ Gestione Presenza Corsi per il giorno **{data_visiva}**")
        st.info("Puoi segnare un corso come PRESENTE (es. lezioni straordinarie) o ASSENTE (es. gita/esami). Le quote posti si ricalcoleranno in automatico.")
        
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
                    supabase.table("presenze_corsi").upsert({
                        "data": data_str,
                        "gruppo": grp,
                        "stato": scelta
                    }).execute()
                    st.success(f"Aggiornata presenza per {grp}!")
                    st.rerun()

    # TAB 4: REPORT E QUOTE
    with tab4:
        st.write("### 📊 Quote Posti Calcolate per Oggi")
        
        df_quote = pd.DataFrame([
            {
                "Corso": grp,
                "Stato Oggi": "PRESENTE 🟢" if grp in corsi_presenti_oggi else "ASSENTE 🔴",
                "Iscritti Totali": numero_iscritti.get(grp, 0),
                "Quota Posti Auto Assegnata": quote_dinamiche.get(grp, 0) if grp in corsi_presenti_oggi else 0
            }
            for grp in GRUPPI_STUDENTI.keys()
        ])
        st.dataframe(df_quote, use_container_width=True)
        
        st.divider()
        st.write("### 📋 Download Report Excel Completo")
        try:
            risposta_t = supabase.table("prenotazioni").select("data, posto_id, turno, utenti(username, targa, gruppo)").execute()
        except Exception:
            risposta_t = supabase.table("prenotazioni").select("data, posto_id, utenti(username, targa, gruppo)").execute()
        
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
