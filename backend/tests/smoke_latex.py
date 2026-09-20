import os
import sys
from pathlib import Path
import tempfile
import subprocess

def test_latex_compile():
    print("Starting LaTeX French Letter compilation smoke test...")
    
    # 1. Check if we can import pylatex
    try:
        import pylatex
        print("Successfully imported pylatex!")
    except ImportError as e:
        print(f"Error: Failed to import pylatex: {e}")
        return False
        
    # 2. Define our dummy French Letter LaTeX content using 'lettre' class and 'letter' environment
    latex_content = r"""\documentclass[11pt,francais]{lettre}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[french]{babel}

\begin{document}
\begin{letter}{Destinataire \\ Adresse \\ Ville}
\name{Expéditeur}
\address{Expéditeur \\ Adresse \\ Ville}
\lieu{Paris}
\date{17 septembre 2026}
\conc{Candidature au poste de Senior Backend Engineer}

\opening{Madame, Monsieur,}

Ceci est le corps de la lettre de motivation de test, rédigé en français et utilisant la classe lettre standard.

\closing{Je vous prie d'agréer, l'expression de mes salutations distinguées.}

\end{letter}
\end{document}
"""

    # 3. Write to temporary .tex file and compile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        tex_file = tmp_path / "smoke_letter.tex"
        tex_file.write_text(latex_content, encoding="utf-8")
        
        print(f"Created temporary .tex file: {tex_file}")
        
        # Compile via latexmk (which we verified is available)
        print("Compiling via latexmk...")
        try:
            result = subprocess.run(
                ["latexmk", "-pdf", "-interaction=nonstopmode", "-output-directory=" + str(tmp_path), str(tex_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout_str = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
            stderr_str = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            
            if result.returncode == 0:
                print("Compilation successful!")
                pdf_file = tmp_path / "smoke_letter.pdf"
                if pdf_file.exists():
                    print(f"Verified: PDF successfully generated at {pdf_file} ({pdf_file.stat().st_size} bytes)")
                    
                    # Save a copy of the smoke test PDF to backend/tests/ for verification
                    dest_dir = Path(__file__).resolve().parent
                    dest_pdf = dest_dir / "smoke_letter.pdf"
                    dest_pdf.write_bytes(pdf_file.read_bytes())
                    print(f"Smoke test PDF saved to: {dest_pdf}")
                    return True
                else:
                    print("Error: Compilation finished but PDF was not found!")
                    return False
            else:
                print(f"Error: Compilation failed with exit code {result.returncode}")
                print(f"STDOUT:\n{stdout_str}")
                print(f"STDERR:\n{stderr_str}")
                return False
                
        except Exception as e:
            print(f"Exception during compilation execution: {e}")
            return False

if __name__ == "__main__":
    success = test_latex_compile()
    if success:
        print("LaTeX environment verification smoke test PASSED!")
        sys.exit(0)
    else:
        print("LaTeX environment verification smoke test FAILED!")
        sys.exit(1)
