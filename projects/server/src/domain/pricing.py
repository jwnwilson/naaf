from pydantic import BaseModel


class ModelPrice(BaseModel):
    """USD per 1000 tokens for a model alias."""

    input: float
    output: float


def price_stage(
    model: str, input_tokens: int, output_tokens: int, prices: dict[str, ModelPrice]
) -> float:
    """Cost of one stage's LLM usage. Unknown model → 0.0 (e.g. an alias with no
    configured price, or the subscription path where cost is notional)."""
    p = prices.get(model)
    if p is None:
        return 0.0
    return round(input_tokens / 1000 * p.input + output_tokens / 1000 * p.output, 6)
