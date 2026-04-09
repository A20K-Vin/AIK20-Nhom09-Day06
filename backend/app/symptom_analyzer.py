"""
Symptom analyzer using DiseaseAndSymptoms.csv.

Pipeline:
  1. Normalize Vietnamese input (remove diacritics, lowercase).
  2. Match against VI→EN symptom translation map → get English symptom tokens.
  3. Score each disease in the CSV by how many of its symptoms appear in input.
  4. Map winning disease → Vietnamese medical specialty.
  5. Fall back to keyword-only matching when CSV gives no signal.
"""

import csv
import re
import unicodedata
from pathlib import Path
from collections import defaultdict

# ── Paths ─────────────────────────────────────────────────────────────────────

_CSV_PATH = Path(__file__).parent.parent / "data" / "DiseaseAndSymptoms.csv"

# ── Disease → specialty mapping ───────────────────────────────────────────────

DISEASE_SPECIALTY: dict[str, str] = {
    # Tim mach
    "Heart attack":             "Tim mạch",
    "Hypertension":             "Tim mạch",
    "Varicose veins":           "Tim mạch",

    # Ho hap
    "Bronchial Asthma":         "Hô hấp",
    "Pneumonia":                "Hô hấp",
    "Tuberculosis":             "Hô hấp",
    "Common Cold":              "Hô hấp",
    "Allergy":                  "Hô hấp",

    # Than kinh
    "Migraine":                                "Thần kinh",
    "(vertigo) Paroymsal  Positional Vertigo": "Thần kinh",
    "Paralysis (brain hemorrhage)":            "Thần kinh",
    "Cervical spondylosis":                    "Thần kinh",

    # Da lieu
    "Fungal infection":         "Da liễu",
    "Acne":                     "Da liễu",
    "Psoriasis":                "Da liễu",
    "Impetigo":                 "Da liễu",
    "Chicken pox":              "Da liễu",
    "Drug Reaction":            "Da liễu",

    # Tieu hoa
    "GERD":                         "Tiêu hóa",
    "Peptic ulcer diseae":          "Tiêu hóa",
    "Gastroenteritis":              "Tiêu hóa",
    "Alcoholic hepatitis":          "Tiêu hóa",
    "Chronic cholestasis":          "Tiêu hóa",
    "Hepatitis A":                  "Tiêu hóa",
    "hepatitis A":                  "Tiêu hóa",
    "Hepatitis B":                  "Tiêu hóa",
    "Hepatitis C":                  "Tiêu hóa",
    "Hepatitis D":                  "Tiêu hóa",
    "Hepatitis E":                  "Tiêu hóa",
    "Jaundice":                     "Tiêu hóa",
    "Dimorphic hemmorhoids(piles)": "Tiêu hóa",

    # Co xuong khop
    "Arthritis":        "Cơ xương khớp",
    "Osteoarthristis":  "Cơ xương khớp",

    # Noi tiet
    "Diabetes":         "Nội tiết",
    "Hyperthyroidism":  "Nội tiết",
    "Hypothyroidism":   "Nội tiết",
    "Hypoglycemia":     "Nội tiết",

    # Noi tong quat
    "Typhoid":                  "Nội tổng quát",
    "Dengue":                   "Nội tổng quát",
    "Malaria":                  "Nội tổng quát",
    "AIDS":                     "Nội tổng quát",
    "Urinary tract infection":  "Nội tổng quát",
}

# ── Vietnamese → English symptom translation map ──────────────────────────────
# Key: normalized Vietnamese phrase (no diacritics, lowercase)
# Value: English symptom string as it appears in CSV (after strip/lower)

VI_TO_EN: dict[str, str] = {
    # General
    "sot":                      "high_fever",
    "sot cao":                  "high_fever",
    "sot nhe":                  "mild_fever",
    "ot ret":                   "chills",
    "run":                      "shivering",
    "met moi":                  "fatigue",
    "met":                      "fatigue",
    "yeu":                      "weakness_in_limbs",
    "sut can":                  "weight_loss",
    "giam can":                 "weight_loss",
    "tang can":                 "obesity",
    "beo phi":                  "obesity",
    "an khong ngon":            "loss_of_appetite",
    "chan an":                  "loss_of_appetite",
    "khat nuoc":                "excessive_hunger",
    "uong nhieu nuoc":          "excessive_hunger",

    # Da lieu
    "ngua":                     "itching",
    "man ngua":                 "itching",
    "phat ban":                 "skin_rash",
    "ban do":                   "skin_rash",
    "noi man":                  "skin_rash",
    "mun":                      "pus_filled_pimples",
    "mun trung ca":             "blackheads",
    "lo lo":                    "scurring",
    "vay nen":                  "silver_like_dusting",
    "da kho":                   "skin_peeling",
    "bong da":                  "skin_peeling",
    "vang da":                  "yellowish_skin",

    # Ho hap
    "ho":                       "cough",
    "ho khan":                  "cough",
    "ho co dom":                "mucoid_sputum",
    "dom":                      "mucoid_sputum",
    "kho tho":                  "breathlessness",
    "kho tho":                  "breathlessness",
    "nghet mui":                "congestion",
    "chay mui":                 "runny_nose",
    "viem hong":                "throat_irritation",
    "dau hong":                 "throat_irritation",
    "nuot kho":                 "throat_irritation",
    "hen":                      "breathlessness",

    # Tim mach
    "dau nguc":                 "chest_pain",
    "danh trong nguc":          "palpitations",
    "hoi hop":                  "palpitations",
    "tim dap nhanh":            "fast_heart_rate",
    "nhip tim nhanh":           "fast_heart_rate",
    "cao huyet ap":             "headache",
    "huyet ap cao":             "headache",

    # Than kinh
    "dau dau":                  "headache",
    "dau nua dau":              "headache",
    "chong mat":                "dizziness",
    "choang":                   "dizziness",
    "choang vang":              "dizziness",
    "hoa mat":                  "visual_disturbances",
    "te tay":                   "weakness_in_limbs",
    "te chan":                  "weakness_in_limbs",
    "te biet":                  "altered_sensorium",
    "kho ngu":                  "restlessness",
    "mat ngu":                  "restlessness",
    "ngu nhieu":                "lethargy",
    "hay quen":                 "loss_of_balance",

    # Tieu hoa
    "dau bung":                 "stomach_pain",
    "dau thuong vi":            "stomach_pain",
    "dau da day":               "stomach_pain",
    "buon non":                 "nausea",
    "non":                      "vomiting",
    "non mua":                  "vomiting",
    "tieu chay":                "diarrhoea",
    "tao bon":                  "constipation",
    "kho tieu":                 "constipation",
    "day bung":                 "abdominal_pain",
    "chan an":                  "loss_of_appetite",
    "phan co mau":              "bloody_stool",
    "vang da":                  "yellowing_of_eyes",
    "mat vang":                 "yellowing_of_eyes",
    "truong bung":              "distension_of_abdomen",

    # Co xuong khop
    "dau khop":                 "joint_pain",
    "dau lung":                 "back_pain",
    "dau co":                   "muscle_pain",
    "sung khop":                "swelling_joints",
    "cung khop":                "stiff_neck",
    "dau vai":                  "neck_pain",
    "dau goi":                  "knee_pain",
    "dau that lung":            "back_pain",

    # Noi tiet
    "tieu nhieu":               "polyuria",
    "di tieu nhieu":            "polyuria",
    "tieu dem":                 "polyuria",
    "tuyen giap":               "enlarged_thyroid",
    "buou co":                  "enlarged_thyroid",
    "run tay":                  "muscle_weakness",
    "do mo hoi":                "excessive_sweating",

    # Truyen nhiem
    "vang mong mat":            "yellowing_of_eyes",
    "phat ban do":              "red_spots_over_body",
    "dom dau do":               "red_spots_over_body",
}

# ── Load CSV ──────────────────────────────────────────────────────────────────

# disease_symptoms: { disease_name: set of normalized symptom strings }
_disease_symptoms: dict[str, set[str]] = defaultdict(set)


def _load_csv() -> None:
    if not _CSV_PATH.exists():
        return
    with open(_CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            disease = row["Disease"].strip()
            for i in range(1, 18):
                sym = row.get(f"Symptom_{i}", "").strip().lower().replace(" ", "_")
                if sym:
                    _disease_symptoms[disease].add(sym)


_load_csv()

# ── Normalization ─────────────────────────────────────────────────────────────

def _remove_diacritics(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    text = text.lower()
    text = _remove_diacritics(text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ── Core logic ────────────────────────────────────────────────────────────────

def _extract_en_symptoms(normalized_vi: str) -> set[str]:
    """Map normalized Vietnamese text → matched English symptom tokens."""
    matched: set[str] = set()
    for vi_phrase, en_sym in VI_TO_EN.items():
        if _normalize(vi_phrase) in normalized_vi:
            matched.add(en_sym.lower().replace(" ", "_"))
    return matched


def _score_diseases(en_symptoms: set[str]) -> dict[str, int]:
    """Score each disease by number of its symptoms present in input."""
    scores: dict[str, int] = {}
    for disease, disease_syms in _disease_symptoms.items():
        overlap = en_symptoms & disease_syms
        if overlap:
            scores[disease] = len(overlap)
    return scores


def detect_specialty(symptom_text: str) -> str:
    """
    Return the best-matching Vietnamese medical specialty for the given text.

    Steps:
      1. Translate Vietnamese → English symptoms via VI_TO_EN map.
      2. Score all CSV diseases by symptom overlap.
      3. Map winning disease → specialty via DISEASE_SPECIALTY.
      4. Fall back to direct keyword matching if CSV gives no result.
    """
    normalized = _normalize(symptom_text)

    # Step 1-2: CSV-based scoring
    en_symptoms = _extract_en_symptoms(normalized)
    if en_symptoms:
        scores = _score_diseases(en_symptoms)
        if scores:
            best_disease = max(scores, key=lambda d: scores[d])
            specialty = DISEASE_SPECIALTY.get(best_disease)
            if specialty:
                return specialty

    # Step 3: Fallback — direct Vietnamese keyword matching
    fallback_map: list[tuple[str, list[str]]] = [
        ("Tim mạch",      ["tim", "dau nguc", "danh trong nguc", "hoi hop", "huyet ap"]),
        ("Hô hấp",        ["ho", "dom", "viem hong", "kho tho", "sot", "hen suyen"]),
        ("Thần kinh",     ["dau dau", "chong mat", "choang", "te", "mat ngu", "kho ngu", "met moi"]),
        ("Da liễu",       ["ngua", "man ngua", "noi man", "phat ban", "mun", "vay nen"]),
        ("Tiêu hóa",      ["dau bung", "buon non", "non", "tieu chay", "tao bon", "day bung"]),
        ("Cơ xương khớp", ["dau khop", "dau lung", "sung khop", "cung khop", "dau co"]),
        ("Nội tiết",      ["tieu nhieu", "tieu duong", "dai thao duong", "tuyen giap", "buou co"]),
    ]

    best_specialty = "Nội tổng quát"
    best_score = 0
    for specialty, keywords in fallback_map:
        score = sum(1 for kw in keywords if _normalize(kw) in normalized)
        if score > best_score:
            best_score = score
            best_specialty = specialty

    return best_specialty
