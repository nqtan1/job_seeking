"""A canned fit analysis: a letter argues from one, so letter tests queue it too."""

from recruitai.ai.prompts.fit import PROMPT_VERSION as FIT_VERSION
from recruitai.modules.matching.schemas import FitCheck

FIT = FitCheck.model_validate(
    {
        "strengths": ["Python backend depuis 5 ans", "CI/CD et tests automatisés"],
        "gaps": ["Pas d'expérience Kubernetes"],
        "key_missing_requirements": [],
        "reasons": ["Profil technique très proche du poste"],
        "fit_score": 82,
        "recommendation": "go",
        "is_fit": True,
        "confidence": 0.8,
        "summary": "Bon profil.",
        "constructive_feedback": "Monter en compétence sur Kubernetes.",
    }
)

__all__ = ["FIT", "FIT_VERSION"]
