"""Step 9 – AI issue interpretation and discovery (Qwen3:4b + LangChain)."""
from __future__ import annotations

from app.core.config import settings
from app.services.common.banking_rules import CANONICAL
from app.services.ai.llm import ask_json

SYSTEM = f"""You are a banking data-quality analyst. You receive JSON with dataset columns, profiling
statistics, issues already detected by rule engines, sample rows and historical knowledge.
Tasks:
1. Interpret each existing issue in one short sentence (meaning + likely cause).
2. Discover additional potential issues NOT already listed (max 8) and propose ONE validation method each,
   chosen from this list so a Python engine can verify it on all rows:
   null_check | placeholder_check | whitespace_check | case_inconsistency | duplicate_values | duplicate_rows |
   non_numeric | unparseable_date | numeric_range{{min,max}} | regex_mismatch{{regex}} | allowed_values{{allowed:[...]}} |
   outlier_iqr{{k}} | future_date | cross_column_compare{{other,op,kind}}  (op one of <= < >= > == !=, kind numeric|date)
Known canonical banking fields: {CANONICAL}.
Use column names EXACTLY as given. Set needs_business_context=true if the issue cannot be checked from the data alone.
Return JSON:
{{"interpretations":[{{"issue_id":"ISS-001","meaning":"...","likely_cause":"..."}}],
  "new_findings":[{{"column":"...","method":"...","params":{{}},"description":"...","needs_business_context":false}}]}}"""


def interpret_and_discover(context: dict, columns: list[str]):
    if not settings.llm_enabled or not settings.enable_ai_discovery:
        return {"interpretations": [], "new_findings": []}, "AI discovery skipped (enable ENABLE_AI_DISCOVERY=true to use Qwen)."
    data, err = ask_json(SYSTEM, context)
    if not data:
        return {"interpretations": [], "new_findings": []}, err
    interp = [i for i in (data.get("interpretations") or []) if isinstance(i, dict)][:40]
    findings = []
    for k, f in enumerate((data.get("new_findings") or [])[:10], 1):
        if not isinstance(f, dict):
            continue
        params = f.get("params") if isinstance(f.get("params"), dict) else {}
        findings.append({
            "id": f"AI-{k:03d}", "column": f.get("column"), "method": str(f.get("method", "")).strip(),
            "params": params, "description": str(f.get("description", ""))[:300],
            "needs_business_context": bool(f.get("needs_business_context", False)), "source": "qwen3",
        })
    return {"interpretations": interp, "new_findings": findings}, None
