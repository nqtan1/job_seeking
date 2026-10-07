"""France Travail (Offres d'emploi v2) provider, ported from the legacy
``infrastructure/jobs/search/providers/france_travail.py``.

Changes from the legacy copy: async ``httpx`` instead of ``requests``; the OAuth token is kept
in memory (the legacy wrote it to the temp dir); every failure is an ``AppError`` with a fixed
message (no exception text, no logged query parameters); job URLs are not accepted (D5, URL
fetching is v2); the old ``_map_to_job_position`` is not ported, ``service.to_job_position``
builds the current ``JobPosition`` from the standardized result instead.
"""

import asyncio
import re
import time
import unicodedata
from typing import Any

import httpx

from recruitai.core.errors import NotFound, UpstreamUnavailable, ValidationFailed
from recruitai.modules.jobs.schemas import (
    UnifiedJobSearchResponse,
    UnifiedJobSearchResult,
)

DEFAULT_BASE_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2"
TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
_TIMEOUT_S = 15
_MAX_RETRIES = 3
_MAX_RANGE_END = 3149  # the API rejects ranges past this offset

# French metropolitan departments, by accent-stripped lowercase name
DEPARTMENTS_MAP = {
    "ain": "01",
    "aisne": "02",
    "allier": "03",
    "alpes-de-haute-provence": "04",
    "hautes-alpes": "05",
    "alpes-maritimes": "06",
    "ardeche": "07",
    "ardennes": "08",
    "ariege": "09",
    "aube": "10",
    "aude": "11",
    "aveyron": "12",
    "bouches-du-rhone": "13",
    "calvados": "14",
    "cantal": "15",
    "charente": "16",
    "charente-maritime": "17",
    "cher": "18",
    "correze": "19",
    "corse-du-sud": "2A",
    "haute-corse": "2B",
    "cote-d'or": "21",
    "cotes-d'armor": "22",
    "creuse": "23",
    "dordogne": "24",
    "doubs": "25",
    "drome": "26",
    "eure": "27",
    "eure-et-loir": "28",
    "finistere": "29",
    "gard": "30",
    "haute-garonne": "31",
    "gers": "32",
    "gironde": "33",
    "herault": "34",
    "ille-et-vilaine": "35",
    "indre": "36",
    "indre-et-loire": "37",
    "isere": "38",
    "jura": "39",
    "landes": "40",
    "loir-et-cher": "41",
    "loire": "42",
    "haute-loire": "43",
    "loire-atlantique": "44",
    "loiret": "45",
    "lot": "46",
    "lot-et-garonne": "47",
    "lozere": "48",
    "maine-et-loire": "49",
    "manche": "50",
    "marne": "51",
    "haute-marne": "52",
    "mayenne": "53",
    "meurthe-et-moselle": "54",
    "meuse": "55",
    "morbihan": "56",
    "moselle": "57",
    "nievre": "58",
    "nord": "59",
    "oise": "60",
    "orne": "61",
    "pas-de-calais": "62",
    "puy-de-dome": "63",
    "pyrenees-atlantiques": "64",
    "hautes-pyrenees": "65",
    "pyrenees-orientales": "66",
    "bas-rhin": "67",
    "haut-rhin": "68",
    "rhone": "69",
    "haute-saone": "70",
    "saone-et-loire": "71",
    "sarthe": "72",
    "savoie": "73",
    "haute-savoie": "74",
    "paris": "75",
    "seine-maritime": "76",
    "seine-et-marne": "77",
    "yvelines": "78",
    "deux-sevres": "79",
    "somme": "80",
    "tarn": "81",
    "tarn-et-garonne": "82",
    "var": "83",
    "vaucluse": "84",
    "vendee": "85",
    "vienne": "86",
    "haute-vienne": "87",
    "vosges": "88",
    "yonne": "89",
    "territoire de belfort": "90",
    "essonne": "91",
    "hauts-de-seine": "92",
    "seine-saint-denis": "93",
    "val-de-marne": "94",
    "val-d'oise": "95",
}

CITIES_MAP = {
    "paris": "75",
    "lyon": "69",
    "marseille": "13",
    "toulouse": "31",
    "nice": "06",
    "nantes": "44",
    "bordeaux": "33",
    "strasbourg": "67",
    "montpellier": "34",
    "lille": "59",
    "rennes": "35",
    "reims": "51",
    "saint-etienne": "42",
    "le havre": "76",
    "toulon": "83",
    "grenoble": "38",
    "dijon": "21",
    "angers": "49",
    "nimes": "30",
    "villeurbanne": "69",
}


def _unavailable(code: str = "job_provider_unavailable") -> UpstreamUnavailable:
    return UpstreamUnavailable("The job search service is unavailable.", code=code)


def _clean(s: str) -> str:
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
    return stripped.lower().strip()


def _normalize_single_department(val: str) -> str | None:
    """A city or department name (or numeric code) to its department code, else None."""
    raw = val.strip()
    if re.fullmatch(r"\d{2,3}", raw) or raw.upper() in {"2A", "2B"}:
        return raw.upper()
    cleaned = _clean(raw)
    if cleaned in DEPARTMENTS_MAP:
        return DEPARTMENTS_MAP[cleaned]
    if cleaned in CITIES_MAP:
        return CITIES_MAP[cleaned]
    # "Paris 13eme", "Lyon (69)": whole words only, hyphens included, so 'ain' never matches
    # inside 'saint-denis' and 'marne' never inside 'marne-la-vallee' (unknown beats wrong).
    for name, code in {**CITIES_MAP, **DEPARTMENTS_MAP}.items():
        if re.search(rf"(?<![a-z-]){re.escape(name)}(?![a-z-])", cleaned):
            return code
    return None


def normalize_departments(dept: str | None) -> str | None:
    """'Paris, Lyon' -> '75,69'. An unrecognized part is a validation error, not a guess."""
    if not dept:
        return None
    codes = []
    for part in (p.strip() for p in dept.split(",")):
        if not part:
            continue
        code = _normalize_single_department(part)
        if code is None:
            raise ValidationFailed(
                f"Unrecognized French city or department: '{part}'. Use a city name "
                "(e.g. 'Paris') or a department code (e.g. '75')."
            )
        codes.append(code)
    return ",".join(codes) or None


def _standardize(j: dict[str, Any]) -> UnifiedJobSearchResult:
    job_id = j.get("id") or ""
    created = j.get("dateCreation")
    return UnifiedJobSearchResult(
        id=job_id,
        title=j.get("intitule") or "",
        company=(j.get("entreprise") or {}).get("nom"),
        location=(j.get("lieuTravail") or {}).get("libelle"),
        date=created[:10] if created else None,
        url=(j.get("origineOffre") or {}).get("urlOrigine")
        or f"https://candidat.francetravail.fr/offres/recherche/detail/{job_id}",
        work_mode=None,
        regions=["fr"],
        countries=["FR"],
        skills=[c["libelle"] for c in j.get("competences") or [] if c.get("libelle")],
        description=j.get("description"),
        contract_type=j.get("typeContrat"),
        contract_type_label=j.get("typeContratLibelle"),
        experience_label=j.get("experienceLibelle"),
        salary_label=(j.get("salaire") or {}).get("libelle"),
        metadata={
            "origine_offre": j.get("origineOffre") or {},
            "alternance": j.get("alternance") or False,
        },
    )


class FranceTravailProvider:
    name = "france_travail"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        client_id: str | None,
        client_secret: str | None,
        base_url: str | None = None,
        sleep: Any = asyncio.sleep,
    ) -> None:
        self._client = client
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._sleep = sleep
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def _get_token(self) -> str:
        if self._token and self._token_expires_at > time.monotonic() + 60:
            return self._token
        if not self._client_id or not self._client_secret:
            raise _unavailable("job_provider_not_configured")
        try:
            res = await self._client.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "api_offresdemploiv2 o2dsoffre",
                },
                timeout=_TIMEOUT_S,
            )
            res.raise_for_status()
            data = res.json()
            self._token = data["access_token"]
            self._token_expires_at = time.monotonic() + int(
                data.get("expires_in", 1499)
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise _unavailable() from exc
        return self._token or ""

    async def _get(
        self, endpoint: str, params: dict[str, str] | None = None
    ) -> httpx.Response:
        """GET with exponential backoff on network errors, 429 and 5xx."""
        url = f"{self._base_url}/{endpoint}"
        delay = 0.5
        refreshed = False
        for attempt in range(_MAX_RETRIES + 1):
            last = attempt == _MAX_RETRIES
            headers = {"Authorization": f"Bearer {await self._get_token()}"}
            try:
                res = await self._client.get(
                    url, headers=headers, params=params, timeout=_TIMEOUT_S
                )
            except httpx.HTTPError as exc:
                if last:
                    raise _unavailable() from exc
            else:
                if res.status_code == 401 and not refreshed:
                    # Token revoked/rotated before its expiry: fetch a new one, once.
                    self._token, refreshed = None, True
                    continue
                if res.status_code not in (429,) and res.status_code < 500:
                    return res
                if last:
                    raise _unavailable()
            await self._sleep(delay)
            delay *= 2
        raise _unavailable()  # unreachable; keeps mypy happy

    async def search(
        self,
        *,
        query: str | None = None,
        department: str | None = None,
        contract_type: str | None = None,
        page: int = 1,
        limit: int = 25,
    ) -> UnifiedJobSearchResponse:
        dept = normalize_departments(department)
        start = (page - 1) * limit
        if start + limit - 1 > _MAX_RANGE_END:
            raise ValidationFailed("This page is too deep. Narrow the search instead.")
        params = {"range": f"{start}-{start + limit - 1}", "sort": "2"}  # newest first
        if query:
            params["motsCles"] = query
        if dept:
            params["departement"] = dept
        if contract_type:
            params["typeContrat"] = "".join(
                contract_type.split()
            )  # "CDD, CDI" -> "CDD,CDI"

        res = await self._get("offres/search", params)
        if res.status_code == 204:
            return UnifiedJobSearchResponse(
                meta={"count": 0, "page": page, "total": 0}, results=[]
            )
        # 206 = partial page: the normal answer when the result set spans several pages.
        if res.status_code not in (200, 206):
            raise _unavailable()
        try:
            results = [_standardize(j) for j in res.json().get("resultats", [])]
        except ValueError as exc:  # bad JSON, or a record pydantic rejects
            raise _unavailable() from exc
        total = len(results)
        # "offres 0-24/2345"
        content_range = res.headers.get("Content-Range", "")
        if "/" in content_range:
            try:
                total = int(content_range.rsplit("/", 1)[1])
            except ValueError:
                pass
        return UnifiedJobSearchResponse(
            meta={"count": len(results), "page": page, "total": total}, results=results
        )

    async def detail(self, job_id: str) -> UnifiedJobSearchResult:
        clean_id = job_id.strip()
        if not re.fullmatch(r"[A-Za-z0-9]{1,20}", clean_id):  # also blocks path tricks
            raise ValidationFailed("Invalid job id.")
        res = await self._get(f"offres/{clean_id}")
        if res.status_code == 404:
            raise NotFound("Job offer not found.")
        if res.status_code != 200:
            raise _unavailable()
        try:
            return _standardize(res.json())
        except ValueError as exc:
            raise _unavailable() from exc
