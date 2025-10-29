from bot.venue_adapter import order_params


def test_binance_futures_params_include_gtx_when_futures():
    params = order_params("binanceusdm", trigger="index")
    assert params["timeInForce"] == "GTX"
    assert params["postOnly"] is True
    assert params["workingType"] == "INDEX_PRICE"


def test_binance_spot_params_skip_gtx():
    params = order_params("binance", post_only=True)
    assert "timeInForce" not in params


def test_bybit_trigger_mapping_includes_index():
    params = order_params("bybit", trigger="index", reduce_only=True)
    assert params["postOnly"] is True
    assert params["reduce_only"] is True
    assert params["triggerBy"] == "IndexPrice"


def test_okx_does_not_set_tdmode():
    params = order_params("okx", post_only=True, reduce_only=True, trigger="last")
    assert params["ordType"] == "post_only"
    assert params["reduceOnly"] is True
    assert params["triggerPxType"] == "last"
    assert "tdMode" not in params


def test_fallback_sets_generic_flags():
    params = order_params("unknown", post_only=True, reduce_only=True)
    assert params["postOnly"] is True
    assert params["reduceOnly"] is True
