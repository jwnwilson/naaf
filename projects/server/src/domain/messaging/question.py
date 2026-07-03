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


def is_valid_option(payload: dict, option: str) -> bool:
    return any(o["id"] == option for o in payload.get("options", []))


def resolve_payload(payload: dict, option: str) -> dict:
    return {**payload, "resolved_option": option}
