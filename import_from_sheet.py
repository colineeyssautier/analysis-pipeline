"""
01b_import_from_sheets.py
==========================
Importe les projets depuis les 2 Google Sheets vers Supabase,
sans generer d'embedding (cette etape est faite ensuite par
02_embed_and_store.py).
"""

import os
import re
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

CREDENTIALS_PATH = r"C:\Users\colin\OneDrive\Dokumente\SOYA\data_processing\credentials.json"

SHEET_IDS = {
    "grant_paper": "11XN7MfUL5GCQFdUrb7ht5x4luRkhSTgTgKqQp-Q5rmM",
    "feedback": "1x1bDb_Q_NEb0MSEKKOZS5oyzHZy906TX2IWZDJLl3O0",
}

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def connect_to_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
    return gspread.authorize(creds)


def parse_number(value):
    if not value:
        return None
    match = re.search(r"[\d.]+", str(value).replace(",", "."))
    return float(match.group()) if match else None


def parse_int(value):
    n = parse_number(value)
    return int(n) if n is not None else None


def parse_age_range(tranche_age):
    if not tranche_age:
        return None, None
    match = re.search(r"(\d+)\s*-\s*(\d+)", str(tranche_age))
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def parse_list(value):
    if not value:
        return []
    return [v.strip() for v in str(value).split(",") if v.strip()]


def parse_date(value):
    if not value:
        return None
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(value))
    return match.group(0) if match else None


def already_imported():
    """Recupere les fichiers source deja presents dans Supabase, pour eviter les doublons."""
    response = supabase.table("projects").select("notes").execute()
    sources = set()
    for row in response.data:
        notes = row.get("notes") or ""
        match = re.search(r"Source:\s*(.+)", notes)
        if match:
            sources.add(match.group(1).strip())
    return sources


def main():
    gc = connect_to_sheets()
    existing_sources = already_imported()

    all_rows = []
    for doc_type, sheet_id in SHEET_IDS.items():
        sh = gc.open_by_key(sheet_id)
        ws = sh.sheet1
        records = ws.get_all_records()
        for r in records:
            r["_document_type"] = doc_type
            all_rows.append(r)

    to_import = [r for r in all_rows if r.get("Fichier source", "") not in existing_sources]
    print(f"{len(all_rows)} lignes au total, {len(to_import)} restant a importer\n")

    for i, row in enumerate(to_import, 1):
        fichier = row.get("Fichier source", "inconnu")
        print(f"[{i}/{len(to_import)}] {fichier}")

        try:
            age_min, age_max = parse_age_range(row.get("Tranche age", ""))
            partner_countries = parse_list(row.get("Pays partenaires", ""))
            theme_tags = parse_list(row.get("Mots-cles", ""))

            record = {
                "name": row.get("Nom", ""),
                "project_type": row["_document_type"],
                "start_date": parse_date(row.get("Dates", "")),
                "end_date": None,

                "host_country": row.get("Pays hote", ""),
                "partner_countries": partner_countries,
                "nb_countries": parse_int(row.get("Nb pays", "")),

                "nb_participants": parse_int(row.get("Nombre participants", "")),
                "age_range_min": age_min,
                "age_range_max": age_max,

                "theme": row.get("Theme principal", ""),
                "theme_tags": theme_tags,
                "objectives": "",

                "satisfaction_score": parse_number(row.get("Score satisfaction", "")),
                "completion_rate": parse_number(row.get("Taux completion", "")),
                "youthpass_delivered": parse_int(row.get("Youthpass", "")),
                "budget_planned": parse_number(row.get("Budget prevu", "")),
                "budget_actual": parse_number(row.get("Budget reel", "")),

                "strengths": row.get("Points forts", ""),
                "weaknesses": row.get("Faiblesses", ""),
                "lessons": row.get("Lecons", ""),
                "notes": f"Source: {fichier}",
                # embedding volontairement absent -> reste null
            }

            supabase.table("projects").insert(record).execute()
            print("  -> Insere (embedding a generer ensuite)")

        except Exception as e:
            print(f"  [!] Erreur : {e}")

    print("\nTermine.")


if __name__ == "__main__":
    main()