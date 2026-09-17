from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from motivation_letter.schema import MotivationLetter, MotivationLetterRequest
from utils.logger import get_logger


class MotivationLetterService:
    def __init__(self, logger_name: str = "motivation_letter.service"):
        self.logger = get_logger(name=logger_name, log_file="motivation_letter_api.log", level="INFO")
        
        # Set up clean data directory path supporting GCS FUSE
        data_dir_env = os.getenv("DATA_DIR")
        if data_dir_env:
            self.db_base_dir = Path(data_dir_env)
        else:
            self.db_base_dir = Path(__file__).parent.parent / "db"
            
        self.result_base_dir = self.db_base_dir / "motivation_letter" / "generate"
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

    def generate_letter_content(self, request: MotivationLetterRequest, letter_content: str) -> str:
        """Format the letter content as a complete LaTeX document using 'lettre' class."""
        if request.return_format == "latex":
            # Content is already a LaTeX document, return as is
            return letter_content
            
        # Content is plain text, wrap it dynamically using 'lettre' class
        import pylatex.utils as pl_utils
        
        # Gather sender info
        sender_name = request.cv_info.personal_info.name or "Expéditeur"
        sender_email = str(request.cv_info.personal_info.email) if request.cv_info.personal_info.email else ""
        sender_phone = request.cv_info.personal_info.phone or ""
        sender_address = request.cv_info.personal_info.address or ""
        
        # Gather recipient info
        company_name = request.job_info.company or "Destinataire"
        job_title = request.job_info.job_title or ""
        
        # Escape values for LaTeX safety
        safe_sender_name = pl_utils.escape_latex(sender_name)
        safe_sender_address = pl_utils.escape_latex(sender_address).replace("\n", " \\\\ ")
        safe_company_name = pl_utils.escape_latex(company_name)
        safe_job_title = pl_utils.escape_latex(job_title)
        
        # Build sender block
        sender_info = safe_sender_name
        if sender_address:
            sender_info += f" \\\\ {safe_sender_address}"
            
        # Build body by paragraphs
        paragraphs = [pl_utils.escape_latex(p.strip()) for p in letter_content.split("\n\n") if p.strip()]
        
        # Extract opening and closing if possible, or use standard
        opening = "Madame, Monsieur,"
        closing = "Je vous prie d'agréer, l'expression de mes salutations distinguées."
        
        # If the first paragraph looks like an opening, extract it
        if paragraphs and any(paragraphs[0].startswith(o) for o in ["Madame", "Monsieur", "Chère", "Cher"]):
            opening = paragraphs.pop(0)
            
        # If the last paragraph looks like a closing salutation, extract it
        if paragraphs and len(paragraphs) > 1 and any(paragraphs[-1].startswith(c) for c in ["Je vous prie", "Veuillez", "Cordialement", "Bien cordialement"]):
            closing = paragraphs.pop()
            
        body_text = "\n\n".join(paragraphs)
        
        # Format LaTeX string using the verified lettre layout
        latex_template = f"""\\documentclass[11pt,francais]{{lettre}}
\\usepackage[T1]{{fontenc}}
\\usepackage[utf8]{{inputenc}}
\\usepackage[french]{{babel}}

\\begin{{document}}
\\begin{{letter}}{{{safe_company_name}}}
\\name{{{safe_sender_name}}}
\\address{{{sender_info}}}
\\lieu{{Paris}}
\\date{{\\today}}
\\conc{{Candidature au poste de {safe_job_title}}}

\\opening{{{opening}}}

{body_text}

\\closing{{{closing}}}

\\end{{letter}}
\\end{{document}}
"""
        return latex_template

    def render_letter_pdf(self, latex_content: str, output_directory: Path, filename_prefix: str) -> Optional[Path]:
        """Compile LaTeX code to PDF using latexmk and save in the output directory."""
        self.logger.info("Rendering motivation letter PDF using latexmk")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            tex_file = tmp_path / "motivation_letter.tex"
            tex_file.write_text(latex_content, encoding="utf-8")
            
            try:
                # Compile using latexmk
                result = subprocess.run(
                    ["latexmk", "-pdf", "-interaction=nonstopmode", "-output-directory=" + str(tmp_path), str(tex_file)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    pdf_file = tmp_path / "motivation_letter.pdf"
                    if pdf_file.exists():
                        dest_pdf = output_directory / f"{filename_prefix}.pdf"
                        dest_pdf.write_bytes(pdf_file.read_bytes())
                        self.logger.info("Motivation letter PDF successfully rendered: %s", dest_pdf)
                        return dest_pdf
                    else:
                        self.logger.error("Latexmk completed successfully but PDF file was not generated.")
                else:
                    self.logger.error("Latexmk compilation failed (exit code %s).", result.returncode)
                    self.logger.debug("Compilation output:\n%s", result.stdout)
            except subprocess.TimeoutExpired:
                self.logger.error("Latexmk compilation timed out.")
            except Exception as exc:
                self.logger.error("Failed to compile LaTeX PDF: %s", str(exc), exc_info=True)
                
        return None

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

        # Save letter content in the requested format
        letter_file = result_folder / f"motivation_letter.{request.return_format}"
        with open(letter_file, "w", encoding="utf-8") as file:
            file.write(letter.content)
        self.logger.info("Letter content saved to: %s", letter_file)

        # Generate LaTeX and compile PDF automatically
        try:
            latex_content = self.generate_letter_content(request, letter.content)
            
            # Save raw .tex source
            tex_file = result_folder / "motivation_letter.tex"
            tex_file.write_text(latex_content, encoding="utf-8")
            self.logger.info("LaTeX source saved to: %s", tex_file)
            
            # Render and save PDF
            pdf_path = self.render_letter_pdf(latex_content, result_folder, "motivation_letter")
            if pdf_path:
                self.logger.info("PDF compiled and saved successfully.")
        except Exception as exc:
            self.logger.error("Failed to generate/compile LaTeX source or PDF: %s", str(exc), exc_info=True)

        # Save Metadata
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

        # Save Request
        request_file = result_folder / "request.json"
        request_dict = request.model_dump()
        request_dict["cv_info"]["personal_info"]["email"] = str(
            request_dict["cv_info"]["personal_info"]["email"]
        )
        with open(request_file, "w", encoding="utf-8") as file:
            json.dump(request_dict, file, indent=2, ensure_ascii=False, default=str)
        self.logger.info("Request details saved to: %s", request_file)

        return letter
