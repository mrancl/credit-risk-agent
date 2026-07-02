"""Guardrails for the credit-risk multi-agent system.

Three layers, wired as ADK callbacks:

- ``guard_user_input``  (before_model_callback): blocks prompt-injection
  attempts and profanity in the user's message before it reaches the model.
- ``guard_tool_args``   (before_tool_callback): validates and normalizes tool
  arguments (e.g. CUI format) before an MCP call is made.
- ``scrub_model_output`` (after_model_callback): masks profanity that would
  otherwise leak into the final answer.

All text checks run on diacritics-stripped lowercase text, so "Pizdă" and
"pizda" are treated the same.
"""

import re
import unicodedata

from google.adk.models.llm_response import LlmResponse
from google.genai import types

BLOCKED_MESSAGE = (
    "Request blocked by guardrails: it contains inappropriate language or an "
    "attempt to manipulate the agent's instructions. Please rephrase your "
    "request, for example: 'Evaluate the credit risk for the company with "
    "CUI 14399840'."
)

# Matched with word boundaries on normalized (lowercase, no diacritics) text.
_PROFANITY_WORDS = [
    # Romanian
    "pula", "pizda", "muie", "fut", "futu", "futui", "fututi", "futai",
    "cacat", "curva", "coaie", "sugi",
    # English
    "fuck", "fucking", "shit", "bitch", "asshole", "cunt", "dick",
    "bastard", "motherfucker",
]
_PROFANITY_RE = re.compile(r"\b(" + "|".join(_PROFANITY_WORDS) + r")\b")

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|previous\s+|prior\s+|the\s+)*(instructions|rules|prompts?)",
    r"disregard\s+.{0,40}(instructions|rules|prompt)",
    r"forget\s+(everything|all|your\s+instructions)",
    r"(reveal|show|print|dump|leak)\s+.{0,40}(system\s+prompt|instructions)",
    r"system\s+prompt",
    r"developer\s+(mode|message)",
    r"jailbreak",
    r"\bdan\s+mode\b",
    r"you\s+are\s+(now|no\s+longer)\b",
    r"pretend\s+(to\s+be|you\s+are)",
    r"new\s+instructions\s*:",
    # Romanian variants (normalized, no diacritics)
    r"ignora\s+(toate\s+)?(instructiunile|regulile)",
    r"uita\s+(tot|toate|instructiunile)",
    r"(dezvaluie|arata|afiseaza|spune)(-\w+)?\s+.{0,40}(promptul|instructiunile)",
    r"prefa-te\s+ca\s+esti",
    r"de\s+acum\s+esti\b",
]
_INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in _INJECTION_PATTERNS))


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def contains_profanity(text: str) -> bool:
    return bool(_PROFANITY_RE.search(_normalize(text)))


def contains_injection(text: str) -> bool:
    return bool(_INJECTION_RE.search(_normalize(text)))


def _blocked_llm_response(message: str = BLOCKED_MESSAGE) -> LlmResponse:
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=message)])
    )


def _last_user_text(llm_request) -> str:
    for content in reversed(llm_request.contents or []):
        if content.role != "user":
            continue
        texts = [part.text for part in (content.parts or []) if getattr(part, "text", None)]
        # Skip function-response turns (they have no text parts).
        if texts:
            return " ".join(texts)
    return ""


def guard_user_input(callback_context, llm_request):
    """before_model_callback: short-circuits unsafe user input."""
    text = _last_user_text(llm_request)
    if not text:
        return None
    if contains_injection(text) or contains_profanity(text):
        return _blocked_llm_response()
    return None


_CUI_ARG_TOOLS = {
    "get_company",
    "get_company_financials",
    "check_company_contracts",
    "list_company_contracts",
}


def normalize_cui(value: object) -> str | None:
    """'RO 1439-9840' -> '14399840'; None if not a plausible CUI."""
    cui = re.sub(r"[\s.-]", "", str(value)).upper().removeprefix("RO")
    if cui.isdigit() and 2 <= len(cui) <= 10:
        return cui
    return None


def guard_tool_args(tool, args, tool_context):
    """before_tool_callback: validates CUI-style arguments for MCP tools."""
    if tool.name not in _CUI_ARG_TOOLS:
        return None
    raw = args.get("cui")
    if raw is None:
        return None
    cui = normalize_cui(raw)
    if cui is None:
        return {
            "error": (
                f"Invalid CUI '{raw}'. A Romanian CUI is 2-10 digits, optionally "
                "prefixed with 'RO'. Ask the user for a valid CUI or resolve the "
                "company name via search_company first."
            )
        }
    args["cui"] = cui
    return None


def _mask_profanity(text: str) -> str:
    """Mask profane words while keeping the rest of the text intact.

    Normalization (NFKD strip) is per-character, so offsets in the normalized
    text map 1:1 to the original and we can mask spans in place.
    """
    normalized = "".join(
        (unicodedata.normalize("NFKD", ch)[:1] or ch) for ch in text
    ).lower()
    masked = list(text)
    for match in _PROFANITY_RE.finditer(normalized):
        masked[match.start() : match.end()] = "*" * (match.end() - match.start())
    return "".join(masked)


def scrub_model_output(callback_context, llm_response):
    """after_model_callback: masks profanity in the model's text output."""
    content = getattr(llm_response, "content", None)
    if content is None or not content.parts:
        return None
    changed = False
    for part in content.parts:
        if getattr(part, "text", None) and contains_profanity(part.text):
            part.text = _mask_profanity(part.text)
            changed = True
    return llm_response if changed else None
