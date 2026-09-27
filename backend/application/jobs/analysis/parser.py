import re
import hashlib
from typing import List, Optional, Literal, Dict, Any

from domain.jobs.analysis.schema import (
    JobPosition, CompensationInfo, Profile, Modalities, SourceMeta,
    CompanyInfo, Badges, AboutCompany
)

def clean_text(text: str) -> Optional[str]:
    if text is None:
        return None
    cleaned = text.strip()
    # Remove common leading bullet points or section markers if they weren't stripped by regex
    cleaned = re.sub(r'^[\s]*[-•*]\s*', '', cleaned)
    cleaned = cleaned.strip(' .-; ') # More aggressive stripping for list items
    return cleaned if cleaned else None

def split_and_clean_list(content: str, delimiter: str = r'[-•*;]') -> List[str]:
    if not content:
        return []
    items = re.split(delimiter, content)
    cleaned_items = []
    for item in items:
        cleaned_item = clean_text(item)
        if cleaned_item:
            cleaned_items.append(cleaned_item)
    return list(dict.fromkeys(cleaned_items)) # Deduplicate while preserving order


def post_process_job_position(
    job_position: JobPosition,
    full_description_content: str
) -> JobPosition:
    """
    Applies programmatic post-processing and refinement to an LLM-extracted JobPosition.
    This function handles rule-based extraction, deduplication, and normalization
    that might be complex or inconsistent for an LLM to manage perfectly.
    """
    
    # Ensure job_description_text is always set
    job_position.job_description_text = full_description_content

    # Initialize sub-models if they are None (Pydantic will do this automatically if default_factory is used,
    # but defensive programming here ensures consistency if LLM returned partial/None sub-objects)
    if not job_position.company:
        job_position.company = CompanyInfo(name="")
    if not job_position.badges:
        job_position.badges = Badges()
    if not job_position.about_company:
        job_position.about_company = AboutCompany()
    if not job_position.profile:
        job_position.profile = Profile()
    if not job_position.modalities:
        job_position.modalities = Modalities()
    if not job_position.compensation:
        job_position.compensation = CompensationInfo()
    if not job_position.source_meta:
        job_position.source_meta = SourceMeta(raw_description_hash=hashlib.sha256(full_description_content.encode('utf-8')).hexdigest())

    # --- Rule-based Extraction/Refinement ---

    # 1. Title and Company Name (basic cleaning)
    if job_position.title:
        job_position.title = clean_text(job_position.title)
    if job_position.company.name:
        job_position.company.name = clean_text(job_position.company.name)

    # 2. Location (French specific patterns, often LLMs struggle with precise extraction)
    if not job_position.badges.location:
        # Try to extract city name before a hyphen, or just the full string
        location_match = re.search(r'(Paris|Lyon|Marseille|Toulouse|Nice|Nantes|Strasbourg|Montpellier|Bordeaux|Lille|Rennes|Reims|Le Havre|Saint-Étienne|Toulon|Grenoble|Dijon|Angers|Villeurbanne)[\s-]*(\d{2,5})?', full_description_content, re.IGNORECASE)
        if location_match:
            job_position.badges.location = clean_text(location_match.group(1))
            if location_match.group(2):
                job_position.badges.location_full = f"{job_position.badges.location} {location_match.group(2)}"
        else:
            # Fallback to general location extraction if available in LLM output
            if job_position.badges.location_full:
                job_position.badges.location = clean_text(job_position.badges.location_full.split(',')[0].strip())
            
    # 3. Contract Type (if not extracted by LLM)
    if not job_position.badges.contract_type:
        contract_match = re.search(r'(CDI|CDD|Freelance|Alternance|Stage|Apprentissage)', full_description_content, re.IGNORECASE)
        if contract_match:
            job_position.badges.contract_type = clean_text(contract_match.group(0))

    # 4. Compensation (French specific TJM/Salary patterns)
    if not job_position.badges.salary:
        # Search for TJM (Taux Journalier Moyen) or daily rate
        tjm_match = re.search(r'TJM[\s:=]?\s*(\d{2,4}\s*€)\s*(?:/jour|par jour)?', full_description_content, re.IGNORECASE)
        if tjm_match:
            job_position.badges.salary = clean_text(tjm_match.group(1).replace(' ', '')) + "/day"
            job_position.compensation.salary_frequency = "Journalier"
            # Try to extract min/max if they are specified around TJM
            min_tjm = re.search(r'entre\s*(\d{2,4})\s*€\s*et\s*(\d{2,4})\s*€/jour', full_description_content, re.IGNORECASE)
            if min_tjm:
                job_position.compensation.min_salary = int(min_tjm.group(1))
                job_position.compensation.max_salary = int(min_tjm.group(2))
        else:
            # Search for annual salary (e.g., K€/an, €/an)
            salary_match = re.search(r'(\d{2,3}(?:\\.\d{3})?)\s*K€[\s]*(?:/an|an|par an)?', full_description_content, re.IGNORECASE)
            if salary_match:
                # Convert K€ to €
                salary_value = float(salary_match.group(1).replace('.', '').replace(',', '.')) * 1000
                job_position.badges.salary = f"{int(salary_value)}€/year"
                job_position.compensation.salary_frequency = "Annuel"
            else:
                salary_match_eur = re.search(r'(\d{5,6})\s*€[\s]*(?:/an|an|par an)?', full_description_content, re.IGNORECASE)
                if salary_match_eur:
                    job_position.badges.salary = f"{salary_match_eur.group(1)}€/year"
                    job_position.compensation.salary_frequency = "Annuel"
    
    if not job_position.compensation.salary_currency:
        job_position.compensation.salary_currency = "EUR" # Default for French context


    # 5. Experience Level (French specific terms)
    if not job_position.badges.experience_level and job_position.profile.experience:
        exp_level_match = re.search(r'(junior|confirmé|sénior|senior|lead|manager|expert)', job_position.profile.experience, re.IGNORECASE)
        if exp_level_match:
            job_position.badges.experience_level = clean_text(exp_level_match.group(0))
        elif re.search(r'\d+\s*ans d\'expérience', job_position.profile.experience, re.IGNORECASE):
             job_position.badges.experience_level = "Expérimenté"


    # 6. Missions and Tech Stack (ensure list parsing)
    if isinstance(job_position.missions, str):
        job_position.missions = split_and_clean_list(job_position.missions, delimiter=r'[-•*;.]')
    job_position.missions = list(dict.fromkeys(job_position.missions)) # Deduplicate

    if isinstance(job_position.tech_stack, str):
        job_position.tech_stack = split_and_clean_list(job_position.tech_stack, delimiter=r'[,;•*-]')
    job_position.tech_stack = list(dict.fromkeys(job_position.tech_stack)) # Deduplicate

    if isinstance(job_position.working_methods, str):
        job_position.working_methods = split_and_clean_list(job_position.working_methods, delimiter=r'[,;•*-]')
    job_position.working_methods = list(dict.fromkeys(job_position.working_methods)) # Deduplicate

    if job_position.profile.technical_skills and isinstance(job_position.profile.technical_skills, str):
        job_position.profile.technical_skills = split_and_clean_list(job_position.profile.technical_skills, delimiter=r'[,;•*-]')
    job_position.profile.technical_skills = list(dict.fromkeys(job_position.profile.technical_skills)) # Deduplicate

    if job_position.profile.soft_skills and isinstance(job_position.profile.soft_skills, str):
        job_position.profile.soft_skills = split_and_clean_list(job_position.profile.soft_skills, delimiter=r'[,;•*-]')
    job_position.profile.soft_skills = list(dict.fromkeys(job_position.profile.soft_skills)) # Deduplicate

    if job_position.profile.nice_to_have and isinstance(job_position.profile.nice_to_have, str):
        job_position.profile.nice_to_have = split_and_clean_list(job_position.profile.nice_to_have, delimiter=r'[,;•*-]')
    job_position.profile.nice_to_have = list(dict.fromkeys(job_position.profile.nice_to_have)) # Deduplicate


    # 7. Deduplicate all list fields
    job_position.missions = list(dict.fromkeys(job_position.missions))
    job_position.tech_stack = list(dict.fromkeys(job_position.tech_stack))
    job_position.working_methods = list(dict.fromkeys(job_position.working_methods))
    job_position.compensation.benefits = list(dict.fromkeys(job_position.compensation.benefits))
    job_position.profile.technical_skills = list(dict.fromkeys(job_position.profile.technical_skills))
    job_position.profile.soft_skills = list(dict.fromkeys(job_position.profile.soft_skills))
    job_position.profile.nice_to_have = list(dict.fromkeys(job_position.profile.nice_to_have))


    # Final check for empty strings that should be None
    for field in ['title', 'job_description_text']:
        if getattr(job_position, field) == "":
            setattr(job_position, field, None)

    if job_position.company.name == "":
        job_position.company.name = None

    return job_position
