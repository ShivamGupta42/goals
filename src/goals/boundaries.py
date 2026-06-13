from __future__ import annotations

from typing import Literal

from goals.models import GoalSnapshot, ProfessionalBoundaryReport

BoundaryDomain = Literal["auto", "general", "medical", "legal", "financial", "safety"]
BoundaryLevel = Literal["basic", "detailed", "technical"]

DOMAIN_PRIORITY = ["medical", "legal", "financial", "safety"]

DOMAIN_TERMS = {
    "medical": {
        "doctor",
        "diagnosis",
        "health",
        "injury",
        "medical",
        "medication",
        "mental health",
        "symptom",
        "treatment",
    },
    "legal": {
        "attorney",
        "compliance",
        "contract",
        "law",
        "lawsuit",
        "legal",
        "liability",
        "regulation",
        "terms",
    },
    "financial": {
        "debt",
        "financial",
        "insurance",
        "investment",
        "loan",
        "money",
        "portfolio",
        "retirement",
        "tax",
    },
    "safety": {
        "abuse",
        "danger",
        "emergency",
        "hazard",
        "physical safety",
        "risk of harm",
        "safety",
        "violence",
    },
}


def build_professional_boundary_report(
    snapshot: GoalSnapshot | None = None,
    *,
    domain: BoundaryDomain = "auto",
) -> ProfessionalBoundaryReport:
    detected = detect_professional_domains(_snapshot_text(snapshot))
    selected = _select_domain(domain, detected)
    template = _template(selected)
    goal_id = snapshot.goal_id if snapshot is not None else ""
    confidence = 0.85 if selected in detected else 0.55 if selected != "general" else 0.4
    return ProfessionalBoundaryReport(
        goal_id=goal_id,
        domain=selected,
        detected_domains=detected,
        title=template["title"],
        plain_boundary=template["plain_boundary"],
        what_agent_can_do=list(template["what_agent_can_do"]),
        needs_user_or_professional=list(template["needs_user_or_professional"]),
        evidence_expectations=list(template["evidence_expectations"]),
        safe_next_steps=list(template["safe_next_steps"]),
        suggested_user_message=template["suggested_user_message"],
        confidence=confidence,
        summary=(
            f"Use the {selected} boundary template before giving high-stakes guidance."
            if selected != "general"
            else "Use the general boundary template when the risk domain is unclear."
        ),
    )


def detect_professional_domains(text: str) -> list[str]:
    lowered = text.lower()
    detected = [
        domain
        for domain in DOMAIN_PRIORITY
        if any(term in lowered for term in DOMAIN_TERMS[domain])
    ]
    return detected


def render_professional_boundary_report(
    report: ProfessionalBoundaryReport,
    *,
    level: BoundaryLevel = "basic",
) -> str:
    if level == "basic":
        lines = [
            "# Professional Boundary",
            "",
            f"Domain: {report.domain}",
            "",
            report.plain_boundary,
            "",
            "## What I Can Do",
            _bullets(report.what_agent_can_do),
            "",
            "## What Needs You Or A Professional",
            _bullets(report.needs_user_or_professional),
            "",
            "## Suggested Wording",
            report.suggested_user_message,
        ]
    elif level == "detailed":
        lines = [
            "# Professional Boundary",
            "",
            f"Domain: {report.domain}",
            f"Summary: {report.summary}",
            "",
            "## Plain Boundary",
            report.plain_boundary,
            "",
            "## What The Agent Can Do",
            _bullets(report.what_agent_can_do),
            "",
            "## What Needs The User Or A Professional",
            _bullets(report.needs_user_or_professional),
            "",
            "## Evidence Expected",
            _bullets(report.evidence_expectations),
            "",
            "## Safe Next Steps",
            _bullets(report.safe_next_steps),
            "",
            "## Suggested Wording",
            report.suggested_user_message,
        ]
    else:
        lines = [
            "# Professional Boundary",
            "",
            f"Goal: {report.goal_id or 'not tied to an active goal'}",
            f"Domain: {report.domain}",
            f"Detected domains: {', '.join(report.detected_domains) or 'none'}",
            f"Confidence: {report.confidence:.0%}",
            "",
            "## Template",
            report.title,
            "",
            "## Boundary",
            report.plain_boundary,
            "",
            "## Agent Scope",
            _bullets(report.what_agent_can_do),
            "",
            "## Escalation Scope",
            _bullets(report.needs_user_or_professional),
            "",
            "## Evidence Contract",
            _bullets(report.evidence_expectations),
            "",
            "## Safe Next Steps",
            _bullets(report.safe_next_steps),
            "",
            "## Suggested Wording",
            report.suggested_user_message,
        ]
    return "\n".join(lines).rstrip() + "\n"


def _select_domain(
    domain: BoundaryDomain, detected: list[str]
) -> Literal["general", "medical", "legal", "financial", "safety"]:
    if domain != "auto":
        return domain
    for candidate in DOMAIN_PRIORITY:
        if candidate in detected:
            return candidate
    return "general"


def _snapshot_text(snapshot: GoalSnapshot | None) -> str:
    if snapshot is None:
        return ""
    parts = [
        snapshot.objective,
        snapshot.why,
        *snapshot.definition_of_done,
        *snapshot.risks,
        *snapshot.blockers,
        *snapshot.learnings,
    ]
    parts.extend(decision.plain_summary for decision in snapshot.decisions)
    parts.extend(source.summary for source in snapshot.sources)
    parts.extend(claim.claim for claim in snapshot.source_claims)
    return " ".join(part for part in parts if part)


def _template(domain: str) -> dict[str, object]:
    templates: dict[str, dict[str, object]] = {
        "medical": {
            "title": "Medical Boundary Template",
            "plain_boundary": (
                "I can help organize information, questions, and next steps, but I cannot "
                "diagnose, prescribe, or replace a licensed medical professional."
            ),
            "what_agent_can_do": [
                "Summarize user-provided information without adding a diagnosis.",
                "Prepare questions to ask a qualified clinician.",
                "Track sources, uncertainty, and follow-up tasks.",
            ],
            "needs_user_or_professional": [
                "Diagnosis, treatment choice, medication change, or urgent symptoms.",
                "Any decision where delay or a wrong choice could affect health or safety.",
            ],
            "evidence_expectations": [
                "Record source evidence for factual health claims.",
                "Separate user-provided facts from agent interpretation.",
                "State uncertainty plainly.",
            ],
            "safe_next_steps": [
                "Ask whether the user wants a question list for a clinician.",
                "Suggest seeking urgent care for emergency or severe symptoms.",
            ],
            "suggested_user_message": (
                "This touches medical judgment, so I should not make the decision for you. "
                "I can organize the facts and draft questions for a qualified clinician."
            ),
        },
        "legal": {
            "title": "Legal Boundary Template",
            "plain_boundary": (
                "I can help organize facts, documents, and questions, but I cannot provide "
                "legal advice or replace a qualified lawyer."
            ),
            "what_agent_can_do": [
                "Summarize documents or user-provided facts.",
                "List issues, deadlines, and questions for counsel.",
                "Track jurisdiction, source, and uncertainty gaps.",
            ],
            "needs_user_or_professional": [
                "Legal strategy, rights, obligations, liability, or filing decisions.",
                "Any jurisdiction-specific interpretation that affects real-world action.",
            ],
            "evidence_expectations": [
                "Record source evidence for legal or regulatory claims.",
                "Identify jurisdiction assumptions.",
                "Avoid presenting uncertain interpretations as conclusions.",
            ],
            "safe_next_steps": [
                "Ask whether the user wants a lawyer-facing question list.",
                "Flag deadlines or missing documents without deciding the legal path.",
            ],
            "suggested_user_message": (
                "This involves legal judgment, so I should not decide it for you. I can "
                "organize the facts and prepare questions to review with a qualified lawyer."
            ),
        },
        "financial": {
            "title": "Financial Boundary Template",
            "plain_boundary": (
                "I can help compare options and organize information, but I cannot provide "
                "personal financial advice or guarantee outcomes."
            ),
            "what_agent_can_do": [
                "Summarize tradeoffs, assumptions, and calculations.",
                "Compare reversible options with clear uncertainty.",
                "Prepare questions for a qualified financial professional.",
            ],
            "needs_user_or_professional": [
                "Investment, tax, insurance, borrowing, or retirement decisions.",
                "Any action that risks money, credit, taxes, or long-term obligations.",
            ],
            "evidence_expectations": [
                "Record sources for factual market, tax, or policy claims.",
                "Show assumptions and ranges instead of one-point certainty.",
                "Separate generic education from user-specific recommendations.",
            ],
            "safe_next_steps": [
                "Ask the user for risk tolerance before comparing options.",
                "Recommend professional review before irreversible or high-value action.",
            ],
            "suggested_user_message": (
                "This could affect money or long-term obligations. I can explain options "
                "and assumptions, but you should make the decision or review it with a qualified professional."
            ),
        },
        "safety": {
            "title": "Safety Boundary Template",
            "plain_boundary": (
                "I can help organize safe, low-risk next steps, but I should not give "
                "instructions that increase danger or replace emergency support."
            ),
            "what_agent_can_do": [
                "Summarize the situation in neutral language.",
                "Suggest contacting appropriate emergency, workplace, or local support.",
                "Help create a low-risk information checklist.",
            ],
            "needs_user_or_professional": [
                "Immediate danger, violence, self-harm risk, or physical safety decisions.",
                "Any action that could escalate harm or put someone at risk.",
            ],
            "evidence_expectations": [
                "Record what is known, unknown, and user-provided.",
                "Avoid tactical instructions that increase risk.",
                "Keep safety uncertainty visible.",
            ],
            "safe_next_steps": [
                "Encourage contacting emergency services or trusted local help when danger is immediate.",
                "Ask what safe, non-escalating support the user wants next.",
            ],
            "suggested_user_message": (
                "This may involve safety risk. I can help organize immediate, low-risk next "
                "steps, but if anyone is in immediate danger, contact local emergency support now."
            ),
        },
        "general": {
            "title": "General Professional Boundary Template",
            "plain_boundary": (
                "I can help organize information and options, but I should not make "
                "high-impact professional decisions for the user."
            ),
            "what_agent_can_do": [
                "Clarify the goal, assumptions, and reversible next steps.",
                "Track sources, uncertainty, and decisions.",
                "Prepare questions for an appropriate professional if needed.",
            ],
            "needs_user_or_professional": [
                "Any irreversible, high-risk, regulated, or professional judgment call.",
                "Any decision where the user has personal risk tolerance or legal responsibility.",
            ],
            "evidence_expectations": [
                "Record evidence for factual claims.",
                "Call out uncertainty in plain language.",
                "Separate options from recommendations.",
            ],
            "safe_next_steps": [
                "Ask the user which risk boundary they want applied.",
                "Prefer reversible planning until the boundary is clear.",
            ],
            "suggested_user_message": (
                "This may require professional judgment. I can organize the facts and options, "
                "but I should not make the high-impact decision for you."
            ),
        },
    }
    return templates.get(domain, templates["general"])


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None."
