def requires_plan_gate(autonomy_level: str) -> bool:
    return autonomy_level == "gated_all"


def requires_merge_gate(autonomy_level: str) -> bool:
    return autonomy_level in {"gated_all", "gated_merge"}
