from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from freqtrade.configuration import Configuration
from freqtrade.persistence import Trade
from user_data.freqaimodels.MyComprehensiveRLModel import MyComprehensiveRLModel


@pytest.fixture
def dummy_dataframe():
    """
    Fake one-candle DataFrame for prediction.
    """
    df = pd.DataFrame(
        [
            {
                "date": datetime.now(timezone.utc),
                "close": 10100,
                "rsi": 50,
                "macd_val": 0.01,
                "macd_signal": 0.005,
                "macd_hist": 0.005,
                "bb_upperband": 10200,
                "bb_lowerband": 9800,
                "bb_middleband": 10000,
                "atr": 100,
                "rsi_divergence": 0,
            }
        ]
    )
    df.index = pd.date_range(end=datetime.now(timezone.utc), periods=1, freq="1min")
    return df


@pytest.fixture
def dummy_trade_open():
    """
    Fake trade object using SimpleNamespace to bypass SQLAlchemy and ORM logic.
    """
    return SimpleNamespace(
        id=1,
        pair="BTC/USDT",
        open_rate=10000.0,
        open_date=datetime.now(timezone.utc),
        amount=0.01,
        is_open=True,
        fee_open=0.001,
        fee_close=0.001,
        close_profit_pct=0.01,
        trade_duration=6,
    )


def test_predict_entry_signal(monkeypatch, dummy_dataframe):
    """
    Test that when action == 1 (enter), the model sets &enter_long = 1 in pred_df.
    """
    config = Configuration.from_files(["config.json"])
    model = MyComprehensiveRLModel(config=config)

    model.freqai_info = {
        "active_trade": None,
        "action": 1,
        "feature_list": config["freqai"]["features"],
        "state_list": config["freqai"]["states"],
        "label_list": ["&enter_long", "&exit_long", "enter_tag", "exit_tag"],
    }

    pred_df, do_predict = model.predict(dummy_dataframe, metadata={"pair": "BTC/USDT"})

    assert "&enter_long" in pred_df.columns, "Prediction missing &enter_long column"
    assert pred_df["&enter_long"].iloc[0] == 1, "Action == 1 but &enter_long not set"
    assert do_predict[0] == 1, "'do_predict' should default to 1"


def test_predict_exit_signal(dummy_dataframe, dummy_trade_open):
    """
    Test that predict() runs without crashing when a trade is open.
    """
    config = Configuration.from_files(["config.json"])
    model = MyComprehensiveRLModel(config=config)

    model.freqai_info = {
        "active_trade": dummy_trade_open,
        "action": 2,
        "feature_list": config["freqai"]["features"],
        "state_list": config["freqai"]["states"],
        "label_list": ["&enter_long", "&exit_long", "enter_tag", "exit_tag"],
    }

    pred_df, do_predict = model.predict(dummy_dataframe, metadata={"pair": "BTC/USDT"})

    assert isinstance(pred_df, pd.DataFrame), "predict() should return a DataFrame"
    assert "&exit_long" in pred_df.columns, "Prediction missing &exit_long column"
