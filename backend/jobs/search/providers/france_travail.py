import os
import time
import tempfile
import requests
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

from jobs.search.providers.base import BaseJobProvider
from jobs.search.schema import UnifiedJobSearchResult, UnifiedJobSearchResponse
from utils.logger import get_logger

load_dotenv()

DEFAULT_BASE_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2"
TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"


# Comprehensive French metropolitan departments mapping
DEPARTMENTS_MAP = {
    "ain": "01", "aisne": "02", "allier": "03", "alpes-de-haute-provence": "04", "hautes-alpes": "05",
    "alpes-maritimes": "06", "ardeche": "07", "ardennes": "08", "ariege": "09", "aube": "10",
    "aude": "11", "aveyron": "12", "bouches-du-rhone": "13", "calvados": "14", "cantal": "15",
    "charente": "16", "charente-maritime": "17", "cher": "18", "correze": "19", "corse-du-sud": "2A",
    "haute-corse": "2B", "cote-d'or": "21", "cotes-d'armor": "22", "creuse": "23", "dordogne": "24",
    "doubs": "25", "drome": "26", "eure": "27", "eure-et-loir": "28", "finistere": "29",
    "gard": "30", "haute-garonne": "31", "gers": "32", "gironde": "33", "herault": "34",
    "ille-et-vilaine": "35", "indre": "36", "indre-et-loire": "37", "isere": "38", "jura": "39",
    "landes": "40", "loir-et-cher": "41", "loire": "42", "haute-loire": "43", "loire-atlantique": "44",
    "loiret": "45", "lot": "46", "lot-et-garonne": "47", "lozere": "48", "maine-et-loire": "49",
    "manche": "50", "marne": "51", "haute-marne": "52", "mayenne": "53", "meurthe-et-moselle": "54",
    "meuse": "55", "morbihan": "56", "moselle": "57", "nievre": "58", "nord": "59",
    "oise": "60", "orne": "61", "pas-de-calais": "62", "puy-de-dome": "63", "pyrenees-atlantiques": "64",
    "hautes-pyrenees": "65", "pyrenees-orientales": "66", "bas-rhin": "67", "haut-rhin": "68", "rhone": "69",
    "haute-saone": "70", "saone-et-loire": "71", "sarthe": "72", "savoie": "73", "haute-savoie": "74",
    "paris": "75", "seine-maritime": "76", "seine-et-marne": "77", "yvelines": "78", "deux-sevres": "79",
    "somme": "80", "tarn": "81", "tarn-et-garonne": "82", "var": "83", "vaucluse": "84",
    "vendee": "85", "vienne": "86", "haute-vienne": "87", "vosges": "88", "yonne": "89",
    "territoire de belfort": "90", "essonne": "91", "hauts-de-seine": "92", "seine-saint-denis": "93",
    "val-de-marne": "94", "val-d'oise": "95"
}

# Major French cities mapping
CITIES_MAP = {
    "paris": "75", "lyon": "69", "marseille": "13", "toulouse": "31", "nice": "06",
    "nantes": "44", "bordeaux": "33", "strasbourg": "67", "montpellier": "34", "lille": "59",
    "rennes": "35", "reims": "51", "saint-etienne": "42", "le havre": "76", "toulon": "83",
    "grenoble": "38", "dijon": "21", "angers": "49", "nimes": "30", "villeurbanne": "69"
}


class FranceTravailProvider(BaseJobProvider):
    def __init__(self, logger_name: str = "jobs.providers.france_travail"):
        self.logger = get_logger(name=logger_name, log_file="jobs_api.log", level="INFO")
        self.base_url = os.getenv("FRANCE_TRAVAIL_API_URL", "").strip().rstrip("/") or DEFAULT_BASE_URL

    def get_provider_name(self) -> str:
        return "france_travail"

    def _get_credentials(self) -> tuple[str, str]:
        client_id = os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
        client_secret = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")
        if not client_id or not client_secret:
            self.logger.error("Missing France Travail client credentials in environment variables")
            raise ValueError(
                "Missing FRANCE_TRAVAIL_CLIENT_ID or FRANCE_TRAVAIL_CLIENT_SECRET in environment variables"
            )
        return client_id, client_secret

    def _get_token(self) -> str:
        cache_dir = Path(tempfile.gettempdir())
        cache_file = cache_dir / ".francetravail_token_cache.json"

        # Try reading from cache
        if cache_file.exists():
            try:
                import json
                cache_data = json.loads(cache_file.read_text(encoding="utf-8"))
                if cache_data.get("expires_at", 0) > time.time() + 60:
                    return cache_data["access_token"]
            except Exception as e:
                self.logger.warning(
                    "Failed to read token cache from temporary directory",
                    exc_info=True
                )

        # Fetch new token
        client_id, client_secret = self._get_credentials()
        # High value network-blocking event boundary - INFO level
        self.logger.info("OAuth2 token cache miss. Requesting new token from France Travail.")
        try:
            response = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "api_offresdemploiv2 o2dsoffre",
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            # Critical authentication boundary failure - ERROR level
            self.logger.error(
                "Authentication with France Travail failed",
                exc_info=True
            )
            raise RuntimeError(f"Authentication failed: {str(e)}")

        access_token = data["access_token"]
        expires_in = data.get("expires_in", 1499)
        expires_at = time.time() + expires_in

        # Cache the token
        try:
            import json
            cache_file.write_text(
                json.dumps({"access_token": access_token, "expires_at": expires_at}),
                encoding="utf-8",
            )
        except Exception as e:
            self.logger.warning(
                "Failed to write token cache to temporary directory",
                exc_info=True
            )

        return access_token

    def _api_get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> tuple[requests.Response, Any]:
        token = self._get_token()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        max_retries = 3
        delay = 0.5

        for attempt in range(max_retries + 1):
            try:
                res = requests.get(url, headers=headers, params=params, timeout=15)
            except Exception as e:
                if attempt == max_retries:
                    # Critical network boundary failure - ERROR level
                    self.logger.error(
                        "Network error during France Travail API GET",
                        exc_info=True,
                        extra={"endpoint": endpoint, "params": params}
                    )
                    raise ConnectionError(f"Connection failed: {str(e)}")
                time.sleep(delay)
                delay *= 2
                continue

            if res.status_code == 429 or res.status_code >= 500:
                if attempt == max_retries:
                    # Remote API server error - ERROR level
                    self.logger.error(
                        "France Travail API server failed",
                        extra={
                            "endpoint": endpoint,
                            "status_code": res.status_code,
                            "response_excerpt": res.text[:200]
                        }
                    )
                    raise RuntimeError(f"API request failed with status {res.status_code}")
                time.sleep(delay)
                delay *= 2
                continue

            if res.status_code == 404:
                return res, {}

            res.raise_for_status()
            try:
                return res, res.json() if res.content else {}
            except Exception as e:
                # Malformed JSON payload - ERROR level
                self.logger.error(
                    "Failed to parse JSON response from France Travail API",
                    exc_info=True,
                    extra={"endpoint": endpoint, "status_code": res.status_code}
                )
                raise ValueError(f"Invalid JSON response: {str(e)}")

        raise RuntimeError("API request failed after retries")

    def _normalize_single_department(self, val: str) -> Optional[str]:
        """
        Normalizes a single city or department name to its numeric code.
        """
        raw_val = val.strip()
        if not raw_val:
            return None
            
        # Check if already a valid numeric code
        if re.match(r"^\d{2,3}$", raw_val) or raw_val.upper() in {"2A", "2B"}:
            return raw_val.upper()

        import unicodedata
        
        # Strip accents and normalize characters to lowercase
        def clean_string(s: str) -> str:
            s_normalized = unicodedata.normalize("NFKD", s)
            s_clean = "".join([c for c in s_normalized if not unicodedata.combining(c)])
            return s_clean.lower().strip()
            
        cleaned_val = clean_string(raw_val)
        
        # Direct lookup in module constants
        if cleaned_val in DEPARTMENTS_MAP:
            return DEPARTMENTS_MAP[cleaned_val]
        if cleaned_val in CITIES_MAP:
            return CITIES_MAP[cleaned_val]
            
        # Substring containments checks (e.g. "Paris 13eme" or "Lyon (69)")
        for city, code in CITIES_MAP.items():
            if city in cleaned_val:
                return code
        for dept_name, code in DEPARTMENTS_MAP.items():
            if dept_name in cleaned_val:
                return code
                
        return None

    def _normalize_department(self, dept: Optional[str]) -> Optional[str]:
        """
        Robustly normalizes city/department list/strings to standard French department codes (e.g. 'Paris, Lyon' -> '75,69').
        Raises ValueError if any part of the input cannot be recognized as a valid French department or city.
        """
        if not dept:
            return None
        
        # Split by comma to handle lists like "Paris, Lyon" or "75, 69"
        parts = [p.strip() for p in dept.split(",") if p.strip()]
        valid_codes = []
        
        for part in parts:
            norm_code = self._normalize_single_department(part)
            if norm_code:
                valid_codes.append(norm_code)
            else:
                self.logger.error(
                    "Unrecognized French department or city name",
                    extra={"raw_part": part, "full_input": dept}
                )
                raise ValueError(
                    f"Unrecognized French department or city name: '{part}'. "
                    f"Please provide a valid French city name (e.g. 'Paris', 'Lyon') or standard numeric department code (e.g. '75', '69')."
                )

        if not valid_codes:
            return None
            
        return ",".join(valid_codes)

    def search_jobs(
        self,
        query: Optional[str] = None,
        department: Optional[str] = None,
        contract_type: Optional[str] = None,
        page: int = 1,
        limit: int = 25,
    ) -> UnifiedJobSearchResponse:
        """
        Searches job listings and returns a standardized result list.
        """
        normalized_dept = self._normalize_department(department)
        
        # Standard Transaction Entry - INFO level
        self.logger.info(
            "Initiating external job search",
            extra={
                "provider": "france_travail",
                "query": query,
                "department": department,
                "normalized_department": normalized_dept,
                "contract_type": contract_type,
                "page": page,
                "limit": limit
            }
        )
        
        start = (page - 1) * limit
        end = start + limit - 1

        params = {
            "range": f"{start}-{end}",
            "sort": "2",  # Publication date, newest first
        }

        if query:
            params["motsCles"] = query
        if normalized_dept:
            params["departement"] = normalized_dept
        if contract_type:
            # Strip all spaces to ensure we send e.g. "CDD,CDI" instead of "CDD, CDI"
            cleaned_contract = "".join(contract_type.split())
            params["typeContrat"] = cleaned_contract

        try:
            res, data = self._api_get("offres/search", params)
        except Exception as e:
            # Core integration call failure - ERROR level
            self.logger.error(
                "France Travail job search integration call failed",
                exc_info=True,
                extra={"query": query, "department": department, "contract_type": contract_type}
            )
            raise

        if res.status_code == 204:
            return UnifiedJobSearchResponse(
                meta={
                    "count": 0,
                    "page": page,
                    "total": 0,
                },
                results=[],
            )

        results = data.get("resultats", [])
        standardized_results = [
            UnifiedJobSearchResult(**self._standardize_search_result(j))
            for j in results
        ]

        # Parse total count from Content-Range header (e.g. "offres 0-24/2345")
        content_range = res.headers.get("Content-Range", "")
        total = 0
        if "/" in content_range:
            try:
                total = int(content_range.split("/")[-1])
            except ValueError:
                total = len(standardized_results)
        else:
            total = len(standardized_results)

        return UnifiedJobSearchResponse(
            meta={
                "count": len(standardized_results),
                "page": page,
                "total": total,
            },
            results=standardized_results,
        )

    def get_job_detail(self, job_id: str) -> Dict[str, Any]:
        """
        Fetches full details of a single job offer.
        Supports input of raw job ID or a full France Travail job URL.
        """
        # Standard Transaction Entry - INFO level
        self.logger.info(
            "Initiating external job detail fetch",
            extra={"provider": "france_travail", "id_or_url": job_id}
        )
        
        # Clean id_or_url
        clean_id = job_id.strip()
        match = re.search(r"detail/([A-Za-z0-9]+)", clean_id)
        if match:
            clean_id = match.group(1)
        elif "/" in clean_id:
            clean_id = [x for x in clean_id.split("/") if x][-1]

        try:
            res, data = self._api_get(f"offres/{clean_id}")
        except Exception as e:
            # Core integration call failure - ERROR level
            self.logger.error(
                "France Travail job detail fetch integration call failed",
                exc_info=True,
                extra={"job_id": clean_id}
            )
            raise

        if res.status_code == 404:
            raise KeyError(f"Job offer {clean_id} not found")

        if not data:
            raise ValueError("Received empty response from France Travail detail API")

        # Standardize and enrich
        standard_info = self._standardize_search_result(data)
        
        # Convert detail to Pydantic-compatible JobPosition dictionary
        mapped_job_position = self._map_to_job_position(data)

        return {
            "provider": "france_travail",
            "raw_data": data,
            "standard_info": standard_info,
            "job_position_data": mapped_job_position,
        }

    def _standardize_search_result(self, j: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standardizes raw France Travail job record keys to a unified schema.
        """
        job_id = j.get("id", "")
        return {
            "id": job_id,
            "title": j.get("intitule"),
            "company": j.get("entreprise", {}).get("nom"),
            "location": j.get("lieuTravail", {}).get("libelle"),
            "date": j.get("dateCreation")[:10] if j.get("dateCreation") else None,
            "url": (j.get("origineOffre") or {}).get("urlOrigine")
            or f"https://candidat.francetravail.fr/offres/recherche/detail/{job_id}",
            "work_mode": None,
            "regions": ["fr"],
            "countries": ["FR"],
            "skills": [
                c.get("libelle")
                for c in j.get("competences", [])
                if c.get("libelle")
            ],
            "description": j.get("description"),
            "contract_type": j.get("typeContrat"),
            "contract_type_label": j.get("typeContratLibelle"),
            "experience_label": j.get("experienceLibelle"),
            "salary_label": j.get("salaire", {}).get("libelle"),
            "metadata": {
                "origine_offre": j.get("origineOffre") or {},
                "alternance": j.get("alternance") or False,
                "contact": j.get("contact") or {}
            }
        }

    def _map_to_job_position(self, j: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps a France Travail job detail dictionary to properties matching the JobPosition Pydantic model.
        """
        title = j.get("intitule") or "Offre d'emploi"
        company = j.get("entreprise", {}).get("nom") or "Entreprise non divulguée"
        location = j.get("lieuTravail", {}).get("libelle") or "France"
        
        # Determine contract type Literal: "CDI" | "CDD" | "Stage" | "Alternance" | "Freelance" | "PhD"
        raw_contract = (j.get("typeContrat") or "").upper()
        raw_contract_libelle = (j.get("typeContratLibelle") or "").lower()
        
        contract_type = "CDI"  # Default fallback
        if "CDI" in raw_contract:
            contract_type = "CDI"
        elif "CDD" in raw_contract:
            contract_type = "CDD"
        elif "MIS" in raw_contract:  # Interim / Mission
            contract_type = "CDD"
        elif "FRA" in raw_contract or "freelance" in raw_contract_libelle:
            contract_type = "Freelance"
        elif "stage" in raw_contract_libelle or "internship" in raw_contract_libelle:
            contract_type = "Stage"
        elif "alternance" in raw_contract_libelle or "apprentissage" in raw_contract_libelle or "professionnalisation" in raw_contract_libelle:
            contract_type = "Alternance"
            
        # Parse salary if available
        salaire_data = j.get("salaire", {})
        min_salary = None
        max_salary = None
        salary_text = salaire_data.get("libelle") or salaire_data.get("commentaire") or ""
        
        # Robust parsing: split on hyphen if there's a range, e.g., "45 000,00 - 55 000,00 EUR par an"
        if salary_text:
            parts = salary_text.split("-")
            if len(parts) >= 2:
                try:
                    # Clean and parse min salary
                    min_clean = re.split(r"[,.]", parts[0])[0]
                    min_digits = "".join(re.findall(r"\d", min_clean))
                    if min_digits:
                        min_salary = float(min_digits)
                    
                    # Clean and parse max salary
                    max_clean = re.split(r"[,.]", parts[1])[0]
                    max_digits = "".join(re.findall(r"\d", max_clean))
                    if max_digits:
                        max_salary = float(max_digits)
                except Exception:
                    pass
            elif len(parts) == 1:
                try:
                    single_clean = re.split(r"[,.]", parts[0])[0]
                    single_digits = "".join(re.findall(r"\d", single_clean))
                    if single_digits:
                        min_salary = float(single_digits)
                except Exception:
                    pass

        # Build CompensationInfo structure
        compensation = {
            "min_salary": min_salary,
            "max_salary": max_salary,
            "salary_currency": "EUR",
            "salary_frequency": "Annuel" if "an" in salary_text.lower() or min_salary and min_salary > 15000 else "Mensuel",
            "benefits": [salaire_data.get("commentaire")] if salaire_data.get("commentaire") else None,
            "meal_vouchers": True if "ticket" in salary_text.lower() or "restaurant" in salary_text.lower() else None
        }

        # Build JobRequirements structure
        skills = [c.get("libelle") for c in j.get("competences", []) if c.get("libelle")]
        requirements = {
            "required_skills": skills,
            "experience_level": j.get("experienceLibelle") or j.get("experienceExige"),
            "years_of_experience": None,  # Can be left empty or parsed
        }
        
        # Try parsing years of experience from experienceExige
        exp_exige = j.get("experienceExige") or ""
        years_match = re.search(r"(\d+)\s*an", exp_exige.lower())
        if years_match:
            try:
                requirements["years_of_experience"] = int(years_match.group(1))
            except ValueError:
                pass

        # Build JobPosition output dict
        return {
            "job_title": title,
            "company": company,
            "location": location,
            "contract_type": contract_type,
            "compensation": compensation,
            "requirements": requirements,
            "job_description_text": j.get("description") or "",
            "company_description": j.get("entreprise", {}).get("description") or "",
        }
