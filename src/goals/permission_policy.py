from __future__ import annotations

from pathlib import Path
import re

import yaml

from goals.models import (
    EcosystemRecommendation,
    PermissionDecision,
    PermissionPolicy,
    PermissionPolicyReport,
)

DECISION_RANK = {"allow": 0, "agent_decide": 1, "ask_user": 2, "deny": 3}
RISK_RANK = {"low": 0, "medium": 1, "high": 2}


def load_permission_policies(worktree: Path) -> list[PermissionPolicy]:
    path = _registry_path(worktree)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = data.get("permissions", {})
    if not isinstance(entries, dict):
        return []
    policies = []
    for policy_id, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        policies.append(PermissionPolicy(policy_id=str(policy_id), **entry))
    return policies


def decide_permission(
    worktree: Path,
    *,
    subject_kind: str,
    subject_name: str,
    action: str = "",
    label: str = "",
    reason: str = "",
    command_hint: str = "",
    fallback_needs_user: bool = False,
) -> PermissionDecision:
    policies = load_permission_policies(worktree)
    matched = _best_policy(
        policies,
        " ".join([subject_kind, subject_name, action, label, reason, command_hint]),
    )
    if matched is None:
        decision = "ask_user" if fallback_needs_user else "agent_decide"
        risk = "medium" if fallback_needs_user else "low"
        return PermissionDecision(
            subject_kind=_subject_kind(subject_kind),
            subject_name=subject_name,
            action=action,
            decision=decision,
            risk=risk,
            needs_user=fallback_needs_user,
            unsafe=False,
            reason=(
                "No matching permission policy; existing tool metadata requires approval."
                if fallback_needs_user
                else "No matching permission policy; this stays with the agent as a routine choice."
            ),
            user_question=(
                f"Approve use of {subject_kind} {subject_name}?" if fallback_needs_user else ""
            ),
            agent_action=(
                f"Ask for approval before using {subject_kind} {subject_name}."
                if fallback_needs_user
                else f"Use {subject_kind} {subject_name} if it fits the phase."
            ),
        )
    decision = matched.decision
    needs_user = decision == "ask_user"
    unsafe = decision == "deny"
    user_question = matched.user_question
    if needs_user and not user_question:
        user_question = f"Approve use of {subject_kind} {subject_name}?"
    agent_action = matched.agent_action
    if not agent_action:
        agent_action = _default_agent_action(subject_kind, subject_name, decision)
    return PermissionDecision(
        subject_kind=_subject_kind(subject_kind),
        subject_name=subject_name,
        action=action,
        decision=decision,
        risk=matched.risk,
        needs_user=needs_user,
        unsafe=unsafe,
        policy_id=matched.policy_id,
        reason=matched.description,
        user_question=user_question,
        agent_action=agent_action,
    )


def apply_permission_to_recommendation(
    worktree: Path,
    recommendation: EcosystemRecommendation,
) -> EcosystemRecommendation:
    decision = decide_permission(
        worktree,
        subject_kind=recommendation.kind,
        subject_name=recommendation.name,
        label=recommendation.label,
        reason=recommendation.reason,
        command_hint=recommendation.command_hint,
        fallback_needs_user=recommendation.user_approval_required,
    )
    return recommendation.model_copy(
        update={
            "user_approval_required": decision.needs_user or decision.unsafe,
            "reason": _append_policy_reason(recommendation.reason, decision),
        }
    )


def permission_report_for_recommendations(
    worktree: Path,
    recommendations: list[EcosystemRecommendation],
) -> PermissionPolicyReport:
    decisions = [
        decide_permission(
            worktree,
            subject_kind=recommendation.kind,
            subject_name=recommendation.name,
            label=recommendation.label,
            reason=recommendation.reason,
            command_hint=recommendation.command_hint,
            fallback_needs_user=recommendation.user_approval_required,
        )
        for recommendation in recommendations
    ]
    user_questions = [decision.user_question for decision in decisions if decision.user_question]
    agent_actions = [decision.agent_action for decision in decisions if decision.agent_action]
    return PermissionPolicyReport(
        summary=(
            f"Checked {len(decisions)} permission decision(s): "
            f"{len([item for item in decisions if item.needs_user])} need user approval, "
            f"{len([item for item in decisions if item.unsafe])} unsafe."
        ),
        decisions=decisions,
        user_questions=user_questions,
        agent_actions=agent_actions,
    )


def render_permission_report(report: PermissionPolicyReport) -> str:
    lines = [
        "# Permission Policy Report",
        "",
        report.summary,
        "",
        "## Needs The User",
        _bullets(report.user_questions or ["No permission decision is waiting on the user."]),
        "",
        "## Agent Can Do",
        _bullets(report.agent_actions or ["No permission action needed."]),
        "",
        "## Decisions",
    ]
    for decision in report.decisions:
        marker = " user" if decision.needs_user else (" unsafe" if decision.unsafe else "")
        lines.append(
            f"- [{decision.decision}{marker}] {decision.subject_kind}: {decision.subject_name} "
            f"({decision.risk}) - {decision.reason}"
        )
        if decision.policy_id:
            lines.append(f"  Policy: `{decision.policy_id}`")
    if not report.decisions:
        lines.append("- No permission decisions.")
    return "\n".join(lines) + "\n"


def _registry_path(worktree: Path) -> Path:
    local = worktree / "registries" / "permissions.yml"
    if local.exists():
        return local
    return Path(__file__).resolve().parents[2] / "registries" / "permissions.yml"


def _best_policy(policies: list[PermissionPolicy], text: str) -> PermissionPolicy | None:
    matches = [policy for policy in policies if _policy_matches(policy, text)]
    if not matches:
        return None
    return sorted(
        matches,
        key=lambda policy: (
            -DECISION_RANK[policy.decision],
            -RISK_RANK[policy.risk],
            policy.policy_id,
        ),
    )[0]


def _policy_matches(policy: PermissionPolicy, text: str) -> bool:
    normalized = text.lower()
    tokens = set(_tokens(normalized))
    for term in policy.match:
        normalized_term = str(term).strip().lower()
        term_tokens = _tokens(normalized_term)
        if not term_tokens:
            continue
        if len(term_tokens) == 1 and term_tokens[0] in tokens:
            return True
        if len(term_tokens) > 1 and (
            normalized_term in normalized or set(term_tokens).issubset(tokens)
        ):
            return True
    return False


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _append_policy_reason(reason: str, decision: PermissionDecision) -> str:
    suffix = (
        f" Permission policy `{decision.policy_id}` says {decision.decision}."
        if decision.policy_id
        else f" Permission policy fallback says {decision.decision}."
    )
    return reason + suffix


def _subject_kind(value: str) -> str:
    allowed = {"skill", "plugin", "adapter", "agent", "gate", "command", "other"}
    return value if value in allowed else "other"


def _default_agent_action(subject_kind: str, subject_name: str, decision: str) -> str:
    if decision == "deny":
        return f"Do not use {subject_kind} {subject_name}; choose a safer local alternative."
    if decision == "ask_user":
        return f"Ask the user before using {subject_kind} {subject_name}."
    return f"Use {subject_kind} {subject_name} if it fits the phase."


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
