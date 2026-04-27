import re
from pathlib import Path
from typing import Dict, List

import pdfplumber

# Approach 1: use python library
def parse_cv_pdf(file_path: str) -> Dict:
    try: 
        with pdfplumber.open(file_path) as pdf: 
            text = ""
            for page in pdf.pages:
                text += page.extract_text(x_tolerance=1.5, y_tolerance=1.5) + "\n"
    except Exception as e: 
        return {"error": str(e)}

    # Normalisation du texte
    text = re.sub(r'\s*-\s*', '-', text)
    text = re.sub(r'\(cid:\d+\)', ' ', text)
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    # Patterns de détection
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    phone_pattern = r'(?:(?:\+|00)33|0)\s*[1-9](?:[\s.-]*\d{2}){4}'
    ref_indicators = r'Directeur|Ma[iî]tre|R[eé]f[eé]rence|Reference|Professor|Conf[eé]rences'

    sections_map = {
        "formation": r'^(Formation|Education|Academic|Dipl[oô]mes?|Cursus)$',
        "experiences": r'^(Exp[eé]riences?|Work|Experience|Professional|Stages?|Employment)$',
        "skills": r'^(Comp[eé]tences|Skills|Technical|Expertise|Outils|Hard Skills)$',
        "references": r'^(R[eé]f[eé]rences?|References)$'
    }

    data = {
        "personal_info": {"name": lines[0] if lines else "", "emails": [], "phones": []},
        "formation": [],
        "experiences": [],
        "skills": [],
        "references": []
    }

    # Extraction sécurisée des emails personnels
    all_emails = re.findall(email_pattern, text)
    for email in all_emails:
        # Trouver la ligne contenant cet email pour vérifier le contexte
        is_reference_email = False
        for line in lines:
            if email in line and re.search(ref_indicators, line, re.IGNORECASE):
                is_reference_email = True
                break
        
        # Un email personnel est généralement en haut du CV ou non associé à un titre de référence
        if not is_reference_email and email not in data["personal_info"]["emails"]:
            data["personal_info"]["emails"].append(email)

    data["personal_info"]["phones"] = list(set(re.findall(phone_pattern, text)))

    # Machine à état pour les sections
    current_section = None
    for line in lines:
        header_found = False
        for key, pattern in sections_map.items():
            if re.match(pattern, line, re.IGNORECASE):
                current_section = key
                header_found = True
                break
        
        if header_found:
            continue

        if current_section:
            # Si on trouve un email de référence dans une section
            if re.search(email_pattern, line) and (current_section == "references" or re.search(ref_indicators, line)):
                data["references"].append(line)
            else:
                data[current_section].append(line)
            
    return data

# Approach 2: use Gemini directly 
