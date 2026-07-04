APPROVE_REJECT: list[dict] = [
    {"id": "approve", "label": "Approve"},
    {"id": "reject", "label": "Reject"},
]


def question_payload(run_id: str, gate_kind: str) -> dict:
    return {
        "options": APPROVE_REJECT,
        "run_id": run_id,
        "gate_kind": gate_kind,
        "resolved_option": None,
    }


def run_proposal_payload(work_item_ids: list[str]) -> dict:
    """A lead's proposal to start development runs on the given work items."""
    return {
        "options": APPROVE_REJECT,
        "run_proposal": True,
        "work_item_ids": list(work_item_ids),
        "resolved_option": None,
    }


def is_run_proposal(payload: dict) -> bool:
    return bool(payload.get("run_proposal"))


def is_valid_option(payload: dict, option: str) -> bool:
    return any(o["id"] == option for o in payload.get("options", []))


def resolve_payload(payload: dict, option: str) -> dict:
    return {**payload, "resolved_option": option}
