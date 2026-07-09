import pdfplumber
import json
import os
from pathlib import Path

# --- Config : adapte ces deux chemins ---
INPUT_FOLDERS = {
    "grant_paper": r"C:\Users\colin\OneDrive\Dokumente\SOYA\data_processing\material_AI_training\Applications_submitted",
    "feedback": r"C:\Users\colin\OneDrive\Dokumente\SOYA\data_processing\material_AI_training\Feedbacks",
}
OUTPUT_FOLDER = r"C:\Users\colin\OneDrive\Dokumente\SOYA\data_processing\material_AI_training\extracted_text"
# -----------------------------------------

def extract_text_from_pdf(pdf_path):
    """Extrait tout le texte d'un PDF natif, page par page."""
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
            else:
                print(f"  [!] Page {i+1} vide ou illisible dans {pdf_path.name}")
    return "\n\n".join(text_parts)

def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    for doc_type, folder_path in INPUT_FOLDERS.items():
        folder = Path(folder_path)
        if not folder.exists():
            print(f"[!] Dossier introuvable : {folder_path}")
            continue

        pdf_files = list(folder.glob("*.pdf"))
        print(f"\n--- {doc_type} : {len(pdf_files)} fichiers trouvés ---")

        for pdf_path in pdf_files:
            print(f"Traitement : {pdf_path.name}")
            try:
                text = extract_text_from_pdf(pdf_path)

                if not text.strip():
                    print(f"  [!] Aucun texte extrait — vérifier si {pdf_path.name} est bien natif")
                    continue

                output_data = {
                    "filename": pdf_path.name,
                    "document_type": doc_type,
                    "raw_text": text,
                }

                output_filename = pdf_path.stem + ".json"
                output_path = Path(OUTPUT_FOLDER) / output_filename

                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False, indent=2)

                print(f"  -> Sauvegardé : {output_filename}")

            except Exception as e:
                print(f"  [!] Erreur sur {pdf_path.name} : {e}")

    print("\nExtraction terminée.")

if __name__ == "__main__":
    main()