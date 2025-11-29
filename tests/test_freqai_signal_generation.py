# tests/test_freqai_signal_generation.py
import logging

import pandas as pd
import pytest

from freqtrade.constants import Config
from user_data.freqaimodels.MyComprehensiveRLModel import MyComprehensiveRLModel


logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def sample_config():
    import json
    from pathlib import Path

    config_path = Path("config.json")
    with open(config_path, "r") as f:
        config_data = json.load(f)
        config_data["freqai"]["mode"] = "train  "
    # Ensure user_data_dir là Path object
    if "user_data_dir" not in config_data:
        config_data["user_data_dir"] = Path.cwd() / "user_data"

    return config_data


@pytest.fixture
def model(sample_config):
    from user_data.freqaimodels.MyComprehensiveRLModel import MyComprehensiveRLModel

    model = MyComprehensiveRLModel(config=sample_config)
    model.freqai_config = {"mode": "train"}  # THÊM DÒNG NÀY
    return model


def test_lstm_label_distribution(model):
    # Dữ liệu mẫu: nên dùng FreqAI DataKitchen thực để tạo train_df, đây là demo
    data = {
        "close": [100 + i * 0.5 for i in range(100)],
        "open": [100 + i * 0.5 for i in range(100)],
        "high": [101 + i * 0.5 for i in range(100)],
        "low": [99 + i * 0.5 for i in range(100)],
        "volume": [1000] * 100,
    }
    df = pd.DataFrame(data)
    df["date"] = pd.date_range(start="2024-02-01", periods=len(df), freq="1min")

    # Giả lập feature_engineering_standard + expand_all
    df = model.feature_engineering_standard(df)
    df = model.feature_engineering_expand_all(df)

    assert "Trade_Labels" in df.columns, "Trade_Labels không được tạo"
    label_counts = df["Trade_Labels"].value_counts().to_dict()
    print("Phân phối nhãn LSTM:", label_counts)

    # Kiểm tra ít nhất có nhãn 1 (Buy) hoặc 2 (Sell)
    assert any(label_counts.get(i, 0) > 0 for i in [1, 2]), (
        "Không có nhãn Buy hoặc Sell nào được tạo!"
    )


def test_predict_output(model):
    # Tạo lại dataframe chuẩn đã có feature
    data = {
        "close": [100 + i * 0.5 for i in range(100)],
        "open": [100 + i * 0.5 for i in range(100)],
        "high": [101 + i * 0.5 for i in range(100)],
        "low": [99 + i * 0.5 for i in range(100)],
        "volume": [1000] * 100,
    }
    df = pd.DataFrame(data)
    df["date"] = pd.date_range(start="2024-02-01", periods=len(df), freq="1min")
    df = model.feature_engineering_standard(df)
    df = model.feature_engineering_expand_all(df)

    pred_df, _ = model.predict(df)

    print("Tổng số tín hiệu &enter_long:", pred_df["&enter_long"].sum())
    assert "&enter_long" in pred_df.columns, "predict không trả về &enter_long"
    assert pred_df["&enter_long"].sum() > 0, "Không có tín hiệu mua được sinh ra bởi RL model!"
