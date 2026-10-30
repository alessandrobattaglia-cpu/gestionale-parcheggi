import streamlit as st
import datetime
from datetime import date, datetime as dt, time
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

# Totale effettivo posti prenotabili (15 Bassa + 17 Piazzale + 18 Alta - 2 Inagibili = 48 Posti)
TOTALE_POSTI_STUDENTI = 48  
DATA_PERMANENTE = "2099-12-31"

POSTI_PER_ZONA = {
    "Bassa": [f"Bassa-{i}" for i in range(1, 16)],
    "Piazzale": [f"Piazzale-{i}" for i in range(1, 18)],
    "Alta": [f"Alta-{i}" for i in range(1, 19)], # 1..18 (Alta-18 = Posto 50)
    "Staff": [f"Staff-{i}" for i in range(1, 25)],
    "Docenti": [f"Docenti-{i}" for i in range(1, 8)],
    "Alloggi": [f"Alloggi-{i}" for i in range(1, 14)]
}

POSTI = {}
for lista in POSTI_PER_ZONA.values():
    for p in lista:
        POSTI[p] = {}

PREFIX_MAP = {
    "Bassa": "B",
    "Alta": "A",
    "Piazzale": "P",
    "Staff": "S",
    "Docenti": "D",
    "Alloggi": "AL"
}

def get_codice_mappa(posto_id):
    if not posto_id or "-" not in posto_id:
        return posto_id
    parts = posto_id.split("-")
    pref = parts[0]
    num = int(parts[1]) if parts[1].isdigit() else 0
    if pref == "Bassa":
        return str(num)                # 1..15
    elif pref == "Piazzale":
        return str(15 + num)           # 16..32
    elif pref == "Alta":
        return str(15 + 17 + num)      # 33..50 (Alta-7 = 39, Alta-8 = 40, Alta-18 = 50)
    else:
        return f"{PREFIX_MAP.get(pref, pref[0])}{num}"

# --- FUNZIONI UTILITY TARGE, PASSEGGERI & ZONE EVENTO ---
def is_valid_targa_italiana(targa_str):
    if not targa_str:
        return False
    pattern = r"^[A-Z]{2}\d{3}[A-Z]{2}$"
    return bool(re.match(pattern, targa_str.strip().upper()))

def parse_targhe(targa_str):
    if not targa_str:
        return []
    raw = re.split(r"[,;\s]+", str(targa_str).upper())
    valid_list = []
    for t in raw:
        t_clean = t.strip()
        if is_valid_targa_italiana(t_clean) and t_clean not in valid_list:
            valid_list.append(t_clean)
    return valid_list

def parse_selected_targa(turno_str, default_targa_str):
    if turno_str and "| TARGA:" in turno_str:
        try:
            return turno_str.split("| TARGA:")[1].split("|")[0].strip()
        except Exception:
            pass
    t_list = parse_targhe(default_targa_str)
    return t_list[0] if t_list else "-"

def get_zona_evento(posto_id):
    if not posto_id:
        return "-"
    parts = posto_id.split("-")
    pref = parts[0]
    num = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    
    if pref == "Bassa":
        return "Zona Gialla"
    elif pref == "Alta":
        return "Zona Rossa"
    elif pref == "Piazzale" or pref == "Docenti":
        return "Zona Verde"
    elif pref == "Alloggi":
        return "Zona Blu"
    elif pref == "Staff":
        if (1 <= num <= 11) or num in [23, 24]:
            return "Zona Gialla"
        elif 12 <= num <= 17:
            return "Zona Verde"
        else:
            return "Zona Grigia"
    return "Zona Grigia"

def check_is_alloggi(u_dict):
    if not isinstance(u_dict, dict):
        return False
    if u_dict.get("is_alloggi") or u_dict.get("alloggi"):
        return True
    grp = str(u_dict.get("gruppo", ""))
    return grp.startswith("Alloggi")

def parse_passengers(turno_str):
    if not turno_str or "| PASSENGERS_IDS:" not in turno_str:
        return [], []
    try:
        parts = turno_str.split("|")
        ids_part = [p for p in parts if "PASSENGERS_IDS:" in p][0].split("PASSENGERS_IDS:")[1].strip()
        names_part = [p for p in parts if "PASSENGERS_NAMES:" in p][0].split("PASSENGERS_NAMES:")[1].strip()
        pass_ids = [int(i) for i in ids_part.split(",") if i.strip().isdigit()]
        pass_names = [n.strip() for n in names_part.split(",") if n.strip()]
        return pass_ids, pass_names
    except Exception:
        return [], []

def find_user_as_passenger(utente_id, prenotazioni_raw):
    for p in prenotazioni_raw:
        p_ids, p_names = parse_passengers(p.get("turno", ""))
        if utente_id in p_ids:
            u_driver = (p.get("utenti") or {}).get("username", "Un compagno")
            return True, u_driver, p.get("posto_id")
    return False, None, None

def get_lista_studenti(current_user_id):
    try:
        res = supabase.table("utenti").select("id, username, gruppo").execute()
        if res.data:
            return [u for u in res.data if u.get("gruppo") in GRUPPI_STUDENTI and u.get("id") != current_user_id]
    except Exception:
        pass
    return []

def is_booking_open_for_student(data_target, now_dt=None):
    if now_dt is None:
        now_dt = dt.now()
    
    target_monday = data_target - datetime.timedelta(days=data_target.weekday())
    opening_dt = dt.combine(target_monday - datetime.timedelta(days=3), time(9, 0))
    
    if now_dt >= opening_dt:
        return True, opening_dt
    else:
        return False, opening_dt

# --- FUNZIONE GENERAZIONE EXCEL PER EVENTI ---
def genera_excel_evento(ev, POSTI_PER_ZONA):
    det_posti = ev.get("dettagli_posti") or {}
    if isinstance(det_posti, str):
        try:
            det_posti = json.loads(det_posti)
        except Exception:
            det_posti = {}
    elif not isinstance(det_posti, dict):
        det_posti = {}

    blocchi = ev.get("blocchi", "TUTTI")
    blocchi_list = [b.strip() for b in blocchi.split(",")] if isinstance(blocchi, str) else blocchi

    rows = []
    zone_count = {}

    for zona_p, lista_p in POSTI_PER_ZONA.items():
        for p_id in lista_p:
            z_ev = get_zona_evento(p_id)
            if "TUTTI" in blocchi_list or zona_p in blocchi_list or z_ev in blocchi_list:
                cod_abbr = get_codice_mappa(p_id)
                ospite = det_posti.get(p_id, "").strip()
                if not ospite:
                    ospite = ev.get("note") if ev.get("note") else "Riservato Evento"
                
                rows.append({
                    "Codice Mappa": cod_abbr,
                    "Posto": p_id,
                    "Zona Evento": z_ev,
                    "Zona Parcheggio": zona_p,
                    "Ospite / Assegnazione Specifica": ospite,
                    "Stato": "Riservato Evento",
                    "Spunta Ingresso": "[   ]"
                })
                zone_count[z_ev] = zone_count.get(z_ev, 0) + 1

    df_posti = pd.DataFrame(rows)
    
    info_list = [
        {"Parametro": "Nome Evento", "Valore": ev.get("nome_evento")},
        {"Parametro": "Data Evento", "Valore": ev.get("data")},
        {"Parametro": "Zone Bloccate", "Valore": ev.get("blocchi")},
        {"Parametro": "Totale Posti Riservati", "Valore": len(rows)},
        {"Parametro": "Note Generali Evento", "Valore": ev.get("note", "")}
    ]
    for z_name, c_val in zone_count.items():
        info_list.append({"Parametro": f"Posti in {z_name}", "Valore": c_val})

    df_info = pd.DataFrame(info_list)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_posti.to_excel(writer, index=False, sheet_name='Posti Evento (Da Stampare)')
        df_info.to_excel(writer, index=False, sheet_name='Riepilogo Evento')
    buffer.seek(0)
    return buffer

# --- CALCOLO DINAMICO QUOTE & PRESENZE (MINIMO 2 STUDENTI PER AUTO) ---
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
            
        # Minimo 2 persone per auto
        cap_carpooling = math.ceil(n_stud / 2)
        
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
    
    # --- BLOCCO PERMANENTE AUTOMATICO DEI POSTI 39 (Alta-7) E 40 (Alta-8) PERCHÈ NON AGIBILI ---
    bloccati["Alta-7"] = {
        "id_prenotazione": "inagibile_39",
        "utente_id": None,
        "username": "⛔ NON AGIBILE",
        "targa": "-",
        "gruppo": "RISERVATO",
        "turno": "BLOCCATO",
        "is_mine": False,
        "is_event": False,
        "zona_evento": "Zona Rossa"
    }
    bloccati["Alta-8"] = {
        "id_prenotazione": "inagibile_40",
        "utente_id": None,
        "username": "⛔ NON AGIBILE",
        "targa": "-",
        "gruppo": "RISERVATO",
        "turno": "BLOCCATO",
        "is_mine": False,
        "is_event": False,
        "zona_evento": "Zona Rossa"
    }

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
            if p_id in ["Alta-7", "Alta-8"]:
                continue # Mantiene prioritario il blocco non agibile
            prefisso = p_id.split("-")[0]
            z_ev = get_zona_evento(p_id)
            if "TUTTI" in blocchi_list or prefisso in blocchi_list or z_ev in blocchi_list:
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
                    "is_mine": False,
                    "is_event": True,
                    "zona_evento": z_ev
                }
    return bloccati

def prenotazione_atomica_sicura(utente_id, data_target, lista_candidati, testo_turno):
    try:
        check_u = supabase.table("prenotazioni").select("id").eq("data", data_target).eq("utente_id", utente_id).execute()
        if check_u.data:
            return False, "HAI_GIA_PRENOTATO"
    except Exception:
        pass

    try:
        res_current = supabase.table("prenotazioni").select("posto_id").eq("data", data_target).execute()
        occupati_ora = set(r["posto_id"] for r in res_current.data) if res_current.data else set()
    except Exception:
        occupati_ora = set()

    for p_cand in lista_candidati:
        if p_cand in occupati_ora:
            continue
        
        try:
            res_ins = supabase.table("prenotazioni").insert({
                "utente_id": utente_id,
                "data": data_target,
                "posto_id": p_cand,
                "turno": testo_turno
            }).execute()
            
            if res_ins.data:
                return True, p_cand
        except Exception:
            occupati_ora.add(p_cand)
            continue
            
    return False, "NESSUN_POSTO_LIBERO"

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

# --- SIDEBAR DI CONTROLLO & GESTIONE MULTI-TARGA ---
st.sidebar.header("👤 Account")
st.sidebar.write(f"Utente: **{username}**")
st.sidebar.write(f"Ruolo/Corso: **{gruppo_utente}**")
if is_alloggi_user:
    st.sidebar.info("🏠 **Residente Alloggi**")

targhe_utente_list = parse_targhe(targa_utente)
targa_valida = len(targhe_utente_list) > 0

if targa_valida:
    st.sidebar.success(f"Targhe: **{', '.join(targhe_utente_list)}** 🟢")
else:
    st.sidebar.error("Targa: **Non valida o mancante!** 🔴")

with st.sidebar.expander("✏️ Gestisci le tue Targhe (Formato IT)"):
    st.caption("Puoi inserire più targhe separate da virgola (es. **AA123BB, CC456DD**)")
    nuova_targa_input = st.text_input("Targhe registrate:", value=", ".join(targhe_utente_list), key="input_targa")
    if st.button("Salva Targhe 💾", use_container_width=True):
        t_parsed = parse_targhe(nuova_targa_input)
        if not t_parsed:
            st.error("❌ Nessuna targa valida inserita! Usare il formato IT (es. AA123BB - 2 lettere, 3 cifre, 2 lettere).")
        else:
            str_salvata = ", ".join(t_parsed)
            supabase.table("utenti").update({"targa": str_salvata}).eq("id", utente_loggato["id"]).execute()
            st.session_state["utente_autenticato"]["targa"] = str_salvata
            st.success("Targhe aggiornate con successo!")
            st.rerun()

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

# --- 5. PREPARAZIONE DATI PER MAPPA CON PRIVACY & ZONE EVENTI ---
posti_bloccati_eventi = get_posti_bloccati_evento(data_str, is_staff_or_admin=is_staff_or_admin)
prenotazioni_visibili = {}

for p_id, info_ev in posti_bloccati_eventi.items():
    prenotazioni_visibili[p_id] = info_ev

for p in prenotazioni_raw:
    p_id = p.get("posto_id")
    if p_id and p_id not in posti_bloccati_eventi:
        u_id = p.get("utente_id")
        
        info_u = p.get("utenti") or {}
        if isinstance(info_u, list) and len(info_u) > 0:
            info_u = info_u[0]
        elif not isinstance(info_u, dict):
            info_u = {}

        u_grp = info_u.get("gruppo", "")
        u_name = info_u.get("username", "")
        p_turno = str(p.get("turno", ""))
        u_targa = parse_selected_targa(p_turno, info_u.get("targa") or "")
        
        pass_ids, pass_names = parse_passengers(p_turno)
        
        # Riconoscimento posti bloccati dall'Admin
        is_admin_block = (u_id is None) or (u_name.lower() == "admin") or (p_turno == "BLOCCATO")

        if is_admin_block:
            prenotazioni_visibili[p_id] = {
                "id_prenotazione": p.get("id"),
                "utente_id": None,
                "username": "BLOCCATO (Admin)",
                "targa": "-",
                "gruppo": "RISERVATO",
                "turno": "BLOCCATO",
                "is_mine": False,
                "zona_evento": get_zona_evento(p_id)
            }
        else:
            is_own_booking = (u_id == utente_loggato.get("id"))
            is_user_passenger = (utente_loggato.get("id") in pass_ids)
            is_my_car = is_own_booking or is_user_passenger
            
            is_staff_spot = str(p_id).startswith("Staff") or u_grp == "Staff"
            is_alloggi_spot = str(p_id).startswith("Alloggi") or check_is_alloggi(info_u)

            if is_student:
                if is_my_car:
                    username_disp = u_name
                    targa_disp = u_targa
                    pass_disp = ", ".join(pass_names) if pass_names else "-"
                elif u_grp == gruppo_utente:
                    username_disp = u_name
                    targa_disp = "-"
                    pass_disp = ", ".join(pass_names) if pass_names else "-"
                else:
                    username_disp = "Occupato"
                    targa_disp = "-"
                    pass_disp = "-"
            elif is_staff_spot and not is_staff_or_admin:
                username_disp = "Staff"
                targa_disp = "-"
                pass_disp = "-"
            else:
                username_disp = u_name
                targa_disp = u_targa
                pass_disp = ", ".join(pass_names) if pass_names else "-"

            prenotazioni_visibili[p_id] = {
                "id_prenotazione": p.get("id"),
                "utente_id": u_id,
                "username": username_disp,
                "targa": targa_disp,
                "gruppo": u_grp if (not is_student or u_grp == gruppo_utente or is_my_car) else "Altro Corso",
                "turno": "TUTTO_IL_GIORNO",
                "is_mine": is_my_car,
                "is_alloggi": is_alloggi_spot,
                "passeggeri": pass_disp,
                "zona_evento": get_zona_evento(p_id)
            }

if is_student:
    zone_non_studenti = POSTI_PER_ZONA["Staff"] + POSTI_PER_ZONA["Docenti"] + POSTI_PER_ZONA["Alloggi"]
    for p_id in zone_non_studenti:
        if p_id not in prenotazioni_visibili:
            prenotazioni_visibili[p_id] = {
                "id_prenotazione": None,
                "utente_id": None,
                "username": "Riservato Zona",
                "targa": "-",
                "gruppo": "RISERVATO",
                "turno": "TUTTO_IL_GIORNO",
                "is_mine": False,
                "zona_evento": get_zona_evento(p_id)
            }

# --- 6. MAPPA INTERATTIVA ---
eventi_oggi = get_eventi_giorno(data_str)
if eventi_oggi:
    nomi_ev = ", ".join([e.get("nome_evento", "Evento") for e in eventi_oggi])
    st.error(f"🚨 **ATTENZIONE: EVENTO PROGRAMMATO IN DATA {data_visiva}! ({nomi_ev})**\nI posti riservati all'evento sono evidenziati sulla mappa in base alle rispettive Zone Evento (🟡 Gialla, 🟢 Verde, 🔴 Rossa, 🔵 Blu, ⚪ Grigia).")

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
    html_ready = html_ready.replace("ST_IS_STUDENT_VIEW_PLACEHOLDER", "true" if is_student else "false")
    components.html(html_ready, height=800, scrolling=True)
except Exception as e:
    st.error(f"⚠️ Impossibile caricare la mappa: {e}")

# --- 7. LOGICA PRENOTAZIONI UTENTI ---
st.divider()

quote_dinamiche, corsi_presenti_oggi, numero_iscritti = calcola_quote_posti(data_scelta)

def ottieni_posti_liberi_zona(prefisso_lista):
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
    is_passenger_check, driver_name_check, p_assigned_check = find_user_as_passenger(utente_loggato["id"], prenotazioni_raw)
    
    if mie_prenotazioni:
        st.warning("🏷️ Hai la seguente prenotazione/assegnazione per questo giorno:")
        for mp in mie_prenotazioni:
            is_perm = mp.get("data") == DATA_PERMANENTE
            dt_txt = "Permanente" if is_perm else data_visiva
            cod_num = get_codice_mappa(mp['posto_id']) if is_student else mp['posto_id']
            st.write(f"- **Posto numero {cod_num}** ({dt_txt})")
            
            txt_del_btn = f"Cancella Prenotazione Posto {cod_num} ❌" if is_student else f"Cancella Prenotazione {mp['posto_id']} ❌"
            if st.button(txt_del_btn, key=f"del_{mp['id']}"):
                supabase.table("prenotazioni").delete().eq("id", mp["id"]).execute()
                st.success("Prenotazione annullata!")
                st.rerun()

    elif is_passenger_check:
        cod_num_p = get_codice_mappa(p_assigned_check) if is_student else p_assigned_check
        st.info(f"🚗 **Sei registrato come passeggero** nell'auto di **{driver_name_check}** (Posto numero **{cod_num_p}**) per il giorno **{data_visiva}**.")
        st.caption("Risultando già presente come passeggero, non puoi effettuare un'ulteriore prenotazione come conducente.")

    else:
        st.subheader("📌 Prenota il tuo Posto Auto")

        if not targa_valida:
            st.error("⚠️ **TARGA NON IMPOSTATA O NON VALIDA!**")
            st.info("Per poter prenotare un posto auto devi registrare una targa italiana valida (es. **AA123BB** - 2 lettere, 3 cifre, 2 lettere) nella barra laterale a sinistra.")
            st.stop()

        # Selezione Targa se l'utente ne ha registrate più di una
        if len(targhe_utente_list) > 1:
            targa_selezionata_booking = st.selectbox("🏎️ Seleziona quale auto/targa stai usando per questa prenotazione:", options=targhe_utente_list, key="sb_targa_booking_user")
        else:
            targa_selezionata_booking = targhe_utente_list[0] if targhe_utente_list else "-"

        # --- GESTIONE SPECIFICA ALLOGGIATI (SOLO CONFERMA PER TUTTO IL PERIODO) ---
        if is_alloggi_user:
            giorni_corso = GRUPPI_STUDENTI.get(gruppo_utente, {}).get("giorni_default", [])
            if giorni_corso == [0, 1, 2]:
                nome_grp_alloggi = "Gruppo 1 (Lunedì - Mercoledì)"
            elif giorni_corso == [2, 3, 4]:
                nome_grp_alloggi = "Gruppo 2 (Mercoledì - Venerdì)"
            else:
                nome_grp_alloggi = "Residenza Alloggi"

            alloggiati_stesso_gruppo = []
            try:
                res_u_all = supabase.table("utenti").select("*").execute()
                if res_u_all.data:
                    for u in res_u_all.data:
                        if check_is_alloggi(u):
                            g_u = GRUPPI_STUDENTI.get(u.get("gruppo"), {}).get("giorni_default", [])
                            if g_u == giorni_corso:
                                alloggiati_stesso_gruppo.append(u.get("id"))
            except Exception:
                pass

            totale_gruppo_alloggi = len(alloggiati_stesso_gruppo)
            confermati_oggi = 0
            for pr in prenotazioni_raw:
                if pr.get("data") == data_str and pr.get("utente_id") in alloggiati_stesso_gruppo and pr.get("posto_id") == "ALLOGGI":
                    confermati_oggi += 1

            st.info(f"🏠 **Stato {nome_grp_alloggi} per il {data_visiva}:**\n**{confermati_oggi} su {totale_gruppo_alloggi}** studenti alloggiati del tuo gruppo hanno già confermato la presenza in auto per questa data.")

            studenti_disponibili = get_lista_studenti(utente_loggato["id"])
            selected_passengers = st.multiselect(
                "👥 Seleziona chi viaggia in auto con te (facoltativo):",
                options=studenti_disponibili,
                format_func=lambda u: f"{u['username']} ({u['gruppo']})",
                key="ms_passengers_alloggi"
            )

            p_ids = [u["id"] for u in selected_passengers]
            p_names = [u["username"] for u in selected_passengers]
            txt_turno_alloggi = f"TUTTO_IL_GIORNO | TARGA:{targa_selezionata_booking}"
            if selected_passengers:
                txt_turno_alloggi += f" | PASSENGERS_IDS:{','.join(map(str, p_ids))} | PASSENGERS_NAMES:{','.join(p_names)}"

            if st.button("Conferma Presenza in Auto per TUTTO IL PERIODO 🗓️", use_container_width=True):
                date_periodo = []
                curr_d = oggi
                fine_d = oggi + datetime.timedelta(days=90)
                while curr_d <= fine_d:
                    if curr_d.weekday() in giorni_corso:
                        date_periodo.append(curr_d.strftime("%Y-%m-%d"))
                    curr_d += datetime.timedelta(days=1)

                successi = 0
                già_presenti = 0
                for d_target in date_periodo:
                    try:
                        chk = supabase.table("prenotazioni").select("id").eq("utente_id", utente_loggato["id"]).eq("data", d_target).execute()
                        if chk.data:
                            già_presenti += 1
                            continue
                        
                        supabase.table("prenotazioni").insert({
                            "utente_id": utente_loggato["id"],
                            "data": d_target,
                            "posto_id": "ALLOGGI",
                            "turno": txt_turno_alloggi
                        }).execute()
                        successi += 1
                    except Exception:
                        pass

                st.success(f"🎉 Presenza auto confermata per **{successi}** date del tuo periodo di alloggio! ({già_presenti} date erano già confermate).")
                st.rerun()

        elif gruppo_utente in ["Staff", "Segreteria"]:
            st.info("ℹ️ Come membro dello Staff / Segreteria puoi riservare un posto giornaliero o permanente.")
            candidati_staff = ottieni_posti_liberi_zona(POSTI_PER_ZONA["Staff"])
            tipo_staff = st.radio("Tipo Assegnazione:", ["Giornaliera", "Permanente (Fissa)"])
            
            if candidati_staff:
                if st.button(f"Conferma Assegnazione Posto Staff 🟢", use_container_width=True):
                    d_save = DATA_PERMANENTE if tipo_staff == "Permanente (Fissa)" else data_str
                    txt_turno_staff = f"TUTTO_IL_GIORNO | TARGA:{targa_selezionata_booking}"
                    ok, esito = prenotazione_atomica_sicura(utente_loggato["id"], d_save, candidati_staff, txt_turno_staff)
                    if ok:
                        st.success(f"Posto **{esito}** riservato con successo per l'auto **{targa_selezionata_booking}**!")
                        st.rerun()
                    elif esito == "HAI_GIA_PRENOTATO":
                        st.warning("⚠️ Risulti già in possesso di una prenotazione per questa data.")
                    else:
                        st.error("❌ I posti liberi sono stati appena occupati. Riprova.")
            else:
                st.error("❌ Nessun Posto Staff libero per oggi.")

        elif gruppo_utente == "Docenti":
            candidati_doc = ottieni_posti_liberi_zona(POSTI_PER_ZONA["Docenti"])
            if candidati_doc:
                if st.button(f"Prenota Posto Docenti 🟢", use_container_width=True):
                    txt_turno_doc = f"TUTTO_IL_GIORNO | TARGA:{targa_selezionata_booking}"
                    ok, esito = prenotazione_atomica_sicura(utente_loggato["id"], data_str, candidati_doc, txt_turno_doc)
                    if ok:
                        st.success(f"Posto **{esito}** prenotato con successo per l'auto **{targa_selezionata_booking}**!")
                        st.rerun()
                    elif esito == "HAI_GIA_PRENOTATO":
                        st.warning("⚠️ Risulti già in possesso di una prenotazione per questa data.")
                    else:
                        st.error("❌ Nessun posto libero disponibile. Riprova.")
            else:
                st.error("❌ Nessun Posto Docenti libero per oggi.")

        else:
            if is_student:
                is_open, open_datetime = is_booking_open_for_student(data_scelta)
                if not is_open:
                    st.warning(f"⏳ **Prenotazioni non ancora aperte per il giorno {data_visiva}!**")
                    st.info(f"Le prenotazioni per la settimana del **{data_scelta.strftime('%d/%m/%Y')}** si apriranno **Venerdì {open_datetime.strftime('%d/%m/%Y')} alle ore 9:00**.")
                    st.stop()

            if gruppo_utente not in corsi_presenti_oggi:
                st.error(f"❌ Il gruppo **{gruppo_utente}** non risulta presente/in lezione il giorno **{data_visiva}**.")
                st.stop()
            
            max_quota = quote_dinamiche.get(gruppo_utente, 0)
            
            occupati_gruppo = 0
            for pr in prenotazioni_raw:
                u_inf = pr.get("utenti") or {}
                if isinstance(u_inf, list) and len(u_inf) > 0:
                    u_inf = u_inf[0]
                elif not isinstance(u_inf, dict):
                    u_inf = {}
                u_grp = u_inf.get("gruppo")
                if u_grp == gruppo_utente and not check_is_alloggi(u_inf):
                    occupati_gruppo += 1
            
            st.info(f"📊 **Quota del tuo corso ({gruppo_utente}) per oggi**: **{occupati_gruppo}/{max_quota}** posti auto (regola min 2 persone/auto).")
            
            studenti_disponibili = get_lista_studenti(utente_loggato["id"])
            
            selected_passengers = st.multiselect(
                "👥 Seleziona chi è in auto con te (OBBLIGATORIO - Almeno 1 passeggero):",
                options=studenti_disponibili,
                format_func=lambda u: f"{u['username']} ({u['gruppo']})",
                key="ms_passengers_select"
            )

            if occupati_gruppo >= max_quota:
                st.error(f"❌ Limite raggiunto! Il gruppo **{gruppo_utente}** ha esaurito la quota massima di **{max_quota}** auto per oggi.")
            else:
                if st.button("Prenota Posto Auto Studenti 🚗", use_container_width=True):
                    if not selected_passengers:
                        st.error("❌ **ATTENZIONE**: Devi selezionare **almeno un passeggero** che viaggia con te per poter prenotare (regola carpooling)!")
                    else:
                        candidati_studenti = ottieni_posti_liberi_zona(POSTI_PER_ZONA["Bassa"] + POSTI_PER_ZONA["Piazzale"] + POSTI_PER_ZONA["Alta"])
                        
                        if candidati_studenti:
                            p_ids = [u["id"] for u in selected_passengers]
                            p_names = [u["username"] for u in selected_passengers]
                            
                            txt_turno = f"TUTTO_IL_GIORNO | TARGA:{targa_selezionata_booking} | PASSENGERS_IDS:{','.join(map(str, p_ids))} | PASSENGERS_NAMES:{','.join(p_names)}"
                            
                            ok, esito = prenotazione_atomica_sicura(utente_loggato["id"], data_str, candidati_studenti, txt_turno)
                            
                            if ok:
                                cod_num = get_codice_mappa(esito)
                                st.success(f"🎉 Ti è stato assegnato il **posto numero {cod_num}** (Targa: `{targa_selezionata_booking}`) con {len(selected_passengers)} passeggeri registrati!")
                                st.rerun()
                            elif esito == "HAI_GIA_PRENOTATO":
                                st.warning("⚠️ Risulti già in possesso di una prenotazione per questa data.")
                            else:
                                st.error("❌ I posti liberi sono stati appena occupati da altri utenti. Riprova.")
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
                    st.warning(f"Il posto **{posto_admin}** è bloccato da un Evento ({info_p['username']}) - {info_p['zona_evento']} - Riservato: `{info_p['targa']}`")
                else:
                    pr_esistenti = [pr for pr in prenotazioni_raw if pr["posto_id"] == posto_admin]
                    if not pr_esistenti:
                        st.success(f"Il **Posto {posto_admin}** ({get_zona_evento(posto_admin)}) è LIBERO per il {data_visiva}.")
                        if st.button(f"Blocca Posto {posto_admin} ⛔", use_container_width=True):
                            try:
                                supabase.table("prenotazioni").insert({
                                    "utente_id": None,
                                    "data": data_str,
                                    "posto_id": posto_admin,
                                    "turno": "BLOCCATO"
                                }).execute()
                                st.success(f"Posto {posto_admin} bloccato con successo!")
                                st.rerun()
                            except Exception as e_block:
                                try:
                                    supabase.table("prenotazioni").insert({
                                        "utente_id": utente_loggato["id"],
                                        "data": data_str,
                                        "posto_id": posto_admin,
                                        "turno": "BLOCCATO"
                                    }).execute()
                                    st.success(f"Posto {posto_admin} bloccato!")
                                    st.rerun()
                                except Exception as ex_inner:
                                    st.error(f"❌ Impossibile bloccare il posto: {ex_inner}")
                    else:
                        occ = pr_esistenti[0]
                        u_info = occ.get("utenti") or {}
                        if isinstance(u_info, list) and len(u_info) > 0:
                            u_info = u_info[0]
                        elif not isinstance(u_info, dict):
                            u_info = {}
                        u_id_occ = occ.get("utente_id")
                        n_occ = u_info.get("username", "")
                        t_occ = str(occ.get("turno", ""))
                        targa_occ = parse_selected_targa(t_occ, u_info.get("targa") or "")
                        
                        is_block = (u_id_occ is None) or (n_occ.lower() == "admin") or (t_occ == "BLOCCATO")
                        
                        if is_block:
                            st.warning(f"⛔ Posto **{posto_admin}** **BLOCCATO DA ADMIN** ({get_zona_evento(posto_admin)})")
                            if st.button(f"Sblocca Posto {posto_admin} 🔓", use_container_width=True):
                                supabase.table("prenotazioni").delete().eq("id", occ["id"]).execute()
                                st.success(f"Posto {posto_admin} sbloccato!")
                                st.rerun()
                        else:
                            st.error(f"Occupato da: **{n_occ}** ({get_zona_evento(posto_admin)}) - Targa: `{targa_occ}`")
                            if st.button(f"Rimuovi Prenotazione 🗑️", use_container_width=True):
                                supabase.table("prenotazioni").delete().eq("id", occ["id"]).execute()
                                st.success("Prenotazione rimossa!")
                                st.rerun()
        st.divider()
        st.write("### ↔️ Sposta una Prenotazione Esistente")
        prenotazioni_spostabili = [pr for pr in prenotazioni_raw if pr.get("posto_id")]
        if prenotazioni_spostabili:
            def label_spostamento(x):
                u_inf = x.get("utenti") or {}
                if isinstance(u_inf, list) and len(u_inf) > 0:
                    u_inf = u_inf[0]
                elif not isinstance(u_inf, dict):
                    u_inf = {}
                u_nm = u_inf.get("username", "")
                u_id_val = x.get("utente_id")
                p_tr = str(x.get("turno", ""))
                if u_id_val is None or u_nm.lower() == "admin" or p_tr == "BLOCCATO":
                    return f"Posto {x['posto_id']} - BLOCCATO DA ADMIN"
                return f"Posto {x['posto_id']} - {u_nm}"
            col_mv1, col_mv2, col_mv3 = st.columns(3)
            with col_mv1:
                p_sposta = st.selectbox(
                    "Seleziona Prenotazione da spostare:",
                    options=prenotazioni_spostabili,
                    format_func=label_spostamento,
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
                        st.success(f"Spostato con successo al posto {nuovo_posto_target}!")
                        st.rerun()
                    else:
                        st.error("Nessun posto libero disponibile.")
        else:
            st.info("Nessuna prenotazione attiva da spostare per questa data.")
            
    # TAB 2: ASSEGNAZIONE STAFF & ELENCO ALLOGGIATI
    with tab2:
        st.write(f"### 🏠 Elenco Studenti Alloggiati Confermati ({data_visiva})")
        
        alloggiati_confermati_oggi = []
        for pr in prenotazioni_raw:
            if pr.get("data") == data_str and pr.get("posto_id") == "ALLOGGI":
                u_i = pr.get("utenti") or {}
                if isinstance(u_i, list) and len(u_i) > 0:
                    u_i = u_i[0]
                elif not isinstance(u_i, dict):
                    u_i = {}
                
                p_turno_all = str(pr.get("turno", ""))
                p_ids, p_names = parse_passengers(p_turno_all)
                pass_txt = ", ".join(p_names) if p_names else "-"
                targa_alloggiato = parse_selected_targa(p_turno_all, u_i.get("targa") or "")
                
                alloggiati_confermati_oggi.append({
                    "id_prenotazione": pr.get("id"),
                    "Studente": u_i.get("username", "-"),
                    "Corso": u_i.get("gruppo", "-"),
                    "Targa": targa_alloggiato,
                    "Passeggeri": pass_txt
                })
        if alloggiati_confermati_oggi:
            df_alloggi_admin = pd.DataFrame(alloggiati_confermati_oggi)
            st.dataframe(df_alloggi_admin[["Studente", "Corso", "Targa", "Passeggeri"]], use_container_width=True)
            
            with st.expander("🗑️ Revoca / Rimuovi Conferma Alloggiato"):
                for item_all in alloggiati_confermati_oggi:
                    col_del1, col_del2 = st.columns([4, 1])
                    col_del1.write(f"👤 **{item_all['Studente']}** ({item_all['Corso']}) - Targa: `{item_all['Targa']}`")
                    if col_del2.button("Rimuovi ❌", key=f"del_alloggi_adm_{item_all['id_prenotazione']}"):
                        supabase.table("prenotazioni").delete().eq("id", item_all['id_prenotazione']).execute()
                        st.success("Conferma rimossa!")
                        st.rerun()
        else:
            st.info(f"Nessuno studente alloggiato ha ancora confermato la presenza in auto per il {data_visiva}.")
        
        st.divider()
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
                    format_func=lambda u: f"{u['username']} ({'Alloggi' if check_is_alloggi(u) else u.get('gruppo')}) - Targhe: {u.get('targa') or '-'}",
                    key="sb_staff_member"
                )
                modalita_assegnazione = st.radio("Modalità di Assegnazione:", ["Giorni Ricorrenti", "Singola Data", "Permanente (Fissa)"], key="radio_mod_staff")
                
            with col_s2:
                is_membro_alloggi = check_is_alloggi(membro_scelto)
                posti_suggeriti = POSTI_PER_ZONA["Alloggi"] if is_membro_alloggi else POSTI_PER_ZONA["Staff"]
                altri_posti = [p for p in POSTI.keys() if p not in posti_suggeriti]
                posto_staff_scelto = st.selectbox("Seleziona Posto da Assegnare:", posti_suggeriti + altri_posti, key="sb_staff_spot")
            
            targhe_membro = parse_targhe(membro_scelto.get("targa"))
            if len(targhe_membro) > 1:
                targa_assegnata_staff = st.selectbox("Seleziona Targa per questa assegnazione:", options=targhe_membro, key="sb_targa_admin_staff")
            else:
                targa_assegnata_staff = targhe_membro[0] if targhe_membro else "-"

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
                    txt_t_save = f"TUTTO_IL_GIORNO | TARGA:{targa_assegnata_staff}"
                    payload = [{"utente_id": membro_scelto["id"], "data": d_val, "posto_id": posto_staff_scelto, "turno": txt_t_save} for d_val in date_da_inserire]
                    supabase.table("prenotazioni").insert(payload).execute()
                    st.success(f"🎉 Posto **{posto_staff_scelto}** assegnato a **{membro_scelto['username']}** (Targa: `{targa_assegnata_staff}`)!")
                    st.rerun()

            st.divider()
            st.write("### 🗑️ Gestione e Revoca Assegnazioni Speciali")
            try:
                res_all_s = supabase.table("prenotazioni").select("id, data, posto_id, turno, utente_id, utenti(*)").execute()
                if res_all_s.data:
                    for r in res_all_s.data:
                        u_i = r.get("utenti") or {}
                        if isinstance(u_i, list) and len(u_i) > 0:
                            u_i = u_i[0]
                        elif not isinstance(u_i, dict):
                            u_i = {}
                        dt_r = r.get("data")
                        p_r = r.get("posto_id")
                        t_r = str(r.get("turno", ""))
                        targa_disp_spec = parse_selected_targa(t_r, u_i.get("targa") or "")
                        
                        if str(p_r).startswith("Staff") or str(p_r).startswith("Alloggi") or u_i.get("gruppo") in ["Staff", "Segreteria"]:
                            col_r1, col_r2, col_r3, col_r4 = st.columns([3, 2, 2, 1])
                            col_r1.write(f"👤 **{u_i.get('username')}** ({targa_disp_spec})")
                            col_r2.write(f"🅿️ Posto: **{p_r}**")
                            col_r3.write(f"📅 `{ 'PERMANENTE' if dt_r == DATA_PERMANENTE else dt_r }`")
                            if col_r4.button("❌", key=f"del_spec_{r['id']}"):
                                supabase.table("prenotazioni").delete().eq("id", r["id"]).execute()
                                st.success("Assegnazione rimossa!")
                                st.rerun()
            except Exception as ex:
                st.error(f"Errore caricamento: {ex}")

    # TAB 3: GESTIONE EVENTI E DOWNLOAD REPORT EVENTI
    with tab3:
        st.write("### 🎉 Modalità Eventi e Blocco Parcheggi")
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            data_evento = st.date_input("Data Evento:", value=data_scelta, min_value=oggi, key="dt_event")
            nome_evento = st.text_input("Nome Evento:", placeholder="Es. Convegno Viticoltura / Open Day")
        with col_e2:
            note_evento = st.text_area("Note Generali Evento:", placeholder="Es. Riservato Relatori / Ospiti Esterni")
            opzioni_blocchi = ["TUTTI", "Zona Gialla", "Zona Verde", "Zona Rossa", "Zona Blu", "Zona Grigia", "Bassa", "Alta", "Piazzale", "Staff", "Docenti", "Alloggi"]
            blocchi_selezionati = st.multiselect("Blocchi / Zone Evento da Bloccare:", options=opzioni_blocchi, default=["TUTTI"])
        posti_interessati = []
        if "TUTTI" in blocchi_selezionati:
            posti_interessati = list(POSTI.keys())
        else:
            for p_id in POSTI.keys():
                pref = p_id.split("-")[0]
                z_ev = get_zona_evento(p_id)
                if pref in blocchi_selezionati or z_ev in blocchi_selezionati:
                    posti_interessati.append(p_id)
        dettagli_posti = {}
        if posti_interessati:
            with st.expander("✏️ Personalizza indicazione per singoli posti (in fase di creazione)"):
                cols_ev = st.columns(3)
                for idx, p_id in enumerate(posti_interessati):
                    c_target = cols_ev[idx % 3]
                    txt_p = c_target.text_input(f"Posto {p_id} ({get_zona_evento(p_id)}):", key=f"inp_ev_{p_id}", placeholder="Es. Prof. Rossi")
                    if txt_p.strip():
                        dettagli_posti[p_id] = txt_p.strip()
        if st.button("Crea Evento e Blocca Parcheggi 🚫", use_container_width=True):
            if not nome_evento.strip():
                st.error("Inserisci un nome per l'evento.")
            elif not blocchi_selezionati:
                st.error("Seleziona almeno un blocco o zona di parcheggi.")
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
        st.write("### 📋 Eventi Programmati & Report per Stampa")
        try:
            res_ev_all = supabase.table("eventi").select("*").gte("data", oggi.strftime("%Y-%m-%d")).order("data").execute()
            if res_ev_all.data:
                for ev in res_ev_all.data:
                    ev_id = ev.get("id")
                    ev_dt = ev.get("data")
                    ev_nm = ev.get("nome_evento")
                    
                    col_ev1, col_ev2, col_ev3, col_ev4 = st.columns([2, 3, 2, 1])
                    col_ev1.write(f"📅 **{ev_dt}**")
                    col_ev2.write(f"🎉 **{ev_nm}**")
                    col_ev3.write(f"🚫 Blocchi: `{ev.get('blocchi')}`")
                    
                    if col_ev4.button("🗑️ Eliminare", key=f"del_ev_{ev_id}"):
                        supabase.table("eventi").delete().eq("id", ev_id).execute()
                        st.success("Evento eliminato!")
                        st.rerun()
                    
                    buf_ev = genera_excel_evento(ev, POSTI_PER_ZONA)
                    st.download_button(
                        label=f"📥 Scarica Report Evento '{ev_nm}' (Excel con Zone Evento)",
                        data=buf_ev,
                        file_name=f"evento_{ev_nm.replace(' ', '_')}_{ev_dt}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_ev_{ev_id}",
                        use_container_width=True
                    )
                    
                    with st.expander(f"✏️ Modifica Dettagli e Nomi Posti: {ev_nm}"):
                        with st.form(key=f"form_mod_ev_{ev_id}"):
                            m_nome = st.text_input("Nome Evento:", value=ev_nm)
                            m_note = st.text_area("Note Evento:", value=ev.get("note", ""))
                            
                            curr_b = ev.get("blocchi", "TUTTI")
                            b_def = [b.strip() for b in curr_b.split(",")] if isinstance(curr_b, str) else (curr_b if isinstance(curr_b, list) else ["TUTTI"])
                            m_blocchi = st.multiselect("Blocchi / Zone Parcheggio:", options=opzioni_blocchi, default=b_def)
                            
                            det_p_curr = ev.get("dettagli_posti") or {}
                            if isinstance(det_p_curr, str):
                                try:
                                    det_p_curr = json.loads(det_p_curr)
                                except Exception:
                                    det_p_curr = {}
                            elif not isinstance(det_p_curr, dict):
                                det_p_curr = {}
                            st.caption("Personalizza testo/ospite assegnato a ciascun posto auto:")
                            imp_spots = []
                            if "TUTTI" in m_blocchi:
                                imp_spots = list(POSTI.keys())
                            else:
                                for p_k in POSTI.keys():
                                    pref_k = p_k.split("-")[0]
                                    z_ev_k = get_zona_evento(p_k)
                                    if pref_k in m_blocchi or z_ev_k in m_blocchi:
                                        imp_spots.append(p_k)
                            
                            cols_m = st.columns(2)
                            m_dettagli = {}
                            for idx, p_k in enumerate(imp_spots):
                                c_target = cols_m[idx % 2]
                                val_input = c_target.text_input(f"Posto {p_k} ({get_zona_evento(p_k)}):", value=det_p_curr.get(p_k, ""), key=f"inp_mod_{ev_id}_{p_k}")
                                if val_input.strip():
                                    m_dettagli[p_k] = val_input.strip()
                            if st.form_submit_button("Salva Modifiche Evento 💾", use_container_width=True):
                                str_m_blocchi = "TUTTI" if "TUTTI" in m_blocchi else ",".join(m_blocchi)
                                supabase.table("eventi").update({
                                    "nome_evento": m_nome.strip(),
                                    "note": m_note.strip(),
                                    "blocchi": str_m_blocchi,
                                    "dettagli_posti": json.dumps(m_dettagli)
                                }).eq("id", ev_id).execute()
                                st.success("Dettagli evento aggiornati!")
                                st.rerun()
                    st.divider()
        except Exception as ex_ev_list:
            st.info(f"Nessun evento caricato: {ex_ev_list}")

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
        
        prenotazioni_oggi = [pr for pr in prenotazioni_raw if pr.get("data") == data_str]
        
        table_rows = []
        for grp in GRUPPI_STUDENTI.keys():
            is_present = grp in corsi_presenti_oggi
            q_max = quote_dinamiche.get(grp, 0) if is_present else 0
            
            prenotati_grp = 0
            for pr in prenotazioni_oggi:
                u_inf = pr.get("utenti") or {}
                if isinstance(u_inf, list) and len(u_inf) > 0:
                    u_inf = u_inf[0]
                elif not isinstance(u_inf, dict):
                    u_inf = {}
                
                if u_inf.get("gruppo") == grp and not check_is_alloggi(u_inf):
                    prenotati_grp += 1
                    
            q_residua = max(0, q_max - prenotati_grp) if is_present else 0
            
            table_rows.append({
                "Corso": grp,
                "Stato Oggi": "PRESENTE 🟢" if is_present else "ASSENTE 🔴",
                "Iscritti (No Alloggi)": numero_iscritti.get(grp, 0),
                "Quota Max Auto": q_max,
                "Auto Prenotate": prenotati_grp,
                "Quota Residua (Disponibili)": q_residua
            })
            
        df_quote = pd.DataFrame(table_rows)
        st.dataframe(df_quote, use_container_width=True)
        
        st.divider()
        st.write("### 📋 Download Report Excel Generale")
        tipo_report = st.radio("Ambito report:", ["Report Giornaliero (Data selezionata)", "Report Completo (Tutti i dati)"], horizontal=True)
        
        if st.button("Genera e Scarica Report Excel 📥", use_container_width=True):
            try:
                if "Giornaliero" in tipo_report:
                    risposta_t = supabase.table("prenotazioni").select("data, posto_id, turno, utente_id, utenti(*)").in_("data", [data_str, DATA_PERMANENTE]).execute()
                else:
                    risposta_t = supabase.table("prenotazioni").select("data, posto_id, turno, utente_id, utenti(*)").execute()
                
                if risposta_t.data:
                    lista_excel = []
                    for item in risposta_t.data:
                        u_info = item.get("utenti") or {}
                        if isinstance(u_info, list) and len(u_info) > 0:
                            u_info = u_info[0]
                        elif not isinstance(u_info, dict):
                            u_info = {}
                        p_data_raw = str(item.get("data", ""))
                        p_user = u_info.get("username", "")
                        p_id = item.get("posto_id", "")
                        p_turno = str(item.get("turno", ""))
                        p_targa = parse_selected_targa(p_turno, u_info.get("targa") or "")
                        
                        cod_abbr = get_codice_mappa(p_id)
                        p_ids, p_names = parse_passengers(p_turno)
                        pass_txt = ", ".join(p_names) if p_names else "-"
                        is_adm_blk = (item.get("utente_id") is None) or (p_user.lower() == 'admin') or (p_turno == 'BLOCCATO')
                        prenotato_da_val = "BLOCCATO (Admin)" if is_adm_blk else (p_user if p_user else "-")
                        conducente_val = "BLOCCATO (Admin)" if is_adm_blk else (p_user if p_user else "-")
                        targa_val = "-" if is_adm_blk else p_targa
                        gruppo_val = "-" if is_adm_blk else (u_info.get("gruppo") or "-")
                        lista_excel.append({
                            "Data": "PERMANENTE" if p_data_raw == DATA_PERMANENTE else p_data_raw,
                            "Codice Mappa": cod_abbr,
                            "Posto": p_id,
                            "Zona Evento": get_zona_evento(p_id),
                            "Prenotato da": prenotato_da_val,
                            "Conducente": conducente_val,
                            "Gruppo": gruppo_val,
                            "Targa": targa_val,
                            "Passeggeri in Auto": pass_txt
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
