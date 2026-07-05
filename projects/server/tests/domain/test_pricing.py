from domain.pricing import ModelPrice, price_stage

PRICES = {
    "opus": ModelPrice(input=0.015, output=0.075),
    "sonnet": ModelPrice(input=0.003, output=0.015),
    "haiku": ModelPrice(input=0.001, output=0.005),
}


def test_price_stage_applies_input_and_output_rates_separately():
    # 1000 input @ 0.003 + 2000 output @ 0.015 = 0.003 + 0.030 = 0.033
    assert price_stage("sonnet", 1000, 2000, PRICES) == 0.033


def test_price_stage_opus_more_expensive_than_haiku():
    assert price_stage("opus", 1000, 1000, PRICES) > price_stage("haiku", 1000, 1000, PRICES)


def test_price_stage_unknown_model_is_zero():
    assert price_stage("gpt-9", 5000, 5000, PRICES) == 0.0


def test_price_stage_zero_tokens_is_zero():
    assert price_stage("opus", 0, 0, PRICES) == 0.0


def test_settings_ship_default_prices_and_budget():
    from interactors.api.settings import Settings
    s = Settings()
    assert s.budget_limit_usd == 100.0
    assert s.model_prices["sonnet"].output == 0.015
    assert set(s.model_prices) >= {"opus", "sonnet", "haiku"}
