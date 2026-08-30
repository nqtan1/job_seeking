from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from motivation_letter.schema import MotivationLetter, MotivationLetterRequest
from utils.logger import get_logger


class MotivationLetterService:
    def __init__(self, logger_name: str = "motivation_letter.service"):
        self.logger = get_logger(name=logger_name, log_file="motivation_letter_api.log", level="INFO")
        self.result_base_dir = Path(__file__).resolve().parent.parent / "db/motivation_letter/generate"
        self.result_base_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, text: str) -> str:
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ASCII", "ignore").decode("ASCII")
        text = text.replace(" ", "_")
        return re.sub(r"[^a-zA-Z0-9_-]", "", text)

    def _get_result_folder(self, company: str, job_title: str) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safe_company = self._sanitize_filename(company)[:50]
        safe_job_title = self._sanitize_filename(job_title)[:50]
        folder_name = f"{timestamp}_{safe_company}_{safe_job_title}"
        result_dir = self.result_base_dir / folder_name
        result_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info("Result folder created: %s", result_dir)
        return result_dir

    def persist(self, request: MotivationLetterRequest, letter: MotivationLetter) -> MotivationLetter:
        self.logger.info(
            "Persisting motivation letter candidate=%s company=%s job_type=%s language=%s format=%s",
            request.cv_info.personal_info.name,
            request.job_info.company,
            request.job_type,
            request.language,
            request.return_format,
        )
        result_folder = self._get_result_folder(
            company=request.job_info.company,
            job_title=request.job_info.job_title,
        )

        letter_file = result_folder / f"motivation_letter.{request.return_format}"
        with open(letter_file, "w", encoding="utf-8") as file:
            file.write(letter.content)
        self.logger.info("Letter content saved to: %s", letter_file)

        metadata_file = result_folder / "metadata.json"
        metadata_dict = letter.metadata.model_dump()
        metadata_dict["generated_at"] = metadata_dict["generated_at"].isoformat()
        metadata_dict["candidate_name"] = request.cv_info.personal_info.name
        metadata_dict["candidate_email"] = str(request.cv_info.personal_info.email)
        metadata_dict["company"] = request.job_info.company
        metadata_dict["job_title"] = request.job_info.job_title

        with open(metadata_file, "w", encoding="utf-8") as file:
            json.dump(metadata_dict, file, indent=2, ensure_ascii=False)
        self.logger.info("Metadata saved to: %s", metadata_file)

        request_file = result_folder / "request.json"
        request_dict = request.model_dump()
        request_dict["cv_info"]["personal_info"]["email"] = str(
            request_dict["cv_info"]["personal_info"]["email"]
        )
        with open(request_file, "w", encoding="utf-8") as file:
            json.dump(request_dict, file, indent=2, ensure_ascii=False, default=str)
        self.logger.info("Request details saved to: %s", request_file)

        return letter