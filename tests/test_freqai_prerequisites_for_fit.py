# tests/test_freqai_prerequisites_for_fit.py
import json  # Để load config thật
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Giả định các import này hoạt động đúng
from user_data.freqaimodels.MyComprehensiveRLModel import (
    LSTM_FEATURE_COLS,
    LSTM_LABEL_COL,
    LSTM_WINDOW_SIZE,
    MyComprehensiveRLModel,
)


# from freqtrade.constants import Config # Không thực sự cần Config đầy đủ ở đây

# --- Fixtures ---


@pytest.fixture(scope="module")
def full_config():
    """Loads the actual config.json file AND ensures 'user_data_dir' key exists."""
    config_path = Path("config.json")
    if not config_path.is_file():
        pytest.skip("config.json not found, skipping prerequisite tests.")
    try:
        with open(config_path, "r") as f:
            config_data = json.load(f)

        # --- THÊM KHÓA 'user_data_dir' NẾU CHƯA CÓ ---
        if "user_data_dir" not in config_data:
            # Sử dụng đường dẫn tương đối đến thư mục user_data từ gốc dự án
            # Giả định rằng bài test được chạy từ thư mục gốc freqtrade
            user_data_path = Path.cwd() / "user_data"
            # Quan trọng: Freqtrade mong đợi giá trị này là một đối tượng Path
            config_data["user_data_dir"] = user_data_path
            print(f"\nDEBUG: Added 'user_data_dir': {user_data_path} to config for test.")
        elif not isinstance(config_data["user_data_dir"], Path):
            # Nếu đã có nhưng không phải Path object, chuyển đổi nó
            config_data["user_data_dir"] = Path(config_data["user_data_dir"])
            print(
                f"\nDEBUG: Converted 'user_data_dir' to Path object: {config_data['user_data_dir']}"
            )

        # Đảm bảo FreqAI được bật trong config để test hợp lý
        if not config_data.get("freqai", {}).get("enabled", False):
            pytest.skip("FreqAI is disabled in config.json, skipping prerequisite tests.")

        return config_data
    except Exception as e:
        pytest.fail(f"Failed to load or parse config.json: {e}")


@pytest.fixture
def model_in_train_mode(full_config):
    """Initializes the model instance, simulating train mode."""
    try:
        # Khởi tạo model với config thật để lấy các tham số nội bộ
        model = MyComprehensiveRLModel(config=full_config)

        # --- Mô phỏng trạng thái FreqAI cung cấp trước khi gọi feature engineering ---
        # Quan trọng: Đặt mode là 'train'
        model.freqai_config = {"mode": "train"}
        # Cung cấp freqai_info cơ bản (có thể cần thêm nếu model dùng nhiều)
        model.freqai_info = full_config.get("freqai", {}).get("freqai_info", {})
        model.freqai_info["label_list"] = full_config.get("freqai", {}).get("label_list", [])

        # Đảm bảo model biết kích thước output LSTM từ config
        model.lstm_output_size = (
            full_config.get("freqai", {})
            .get("model_training_parameters", {})
            .get("lstm_config", {})
            .get("num_classes", 3)
        )

        return model
    except Exception as e:
        pytest.fail(f"Failed to initialize MyComprehensiveRLModel: {e}")


@pytest.fixture
def sample_dataframe():
    """Creates a sample DataFrame for testing feature engineering."""
    # Dữ liệu đủ dài để tạo ít nhất vài cửa sổ LSTM hợp lệ
    num_rows = LSTM_WINDOW_SIZE + 50  # Ví dụ: 60 + 50 = 110 hàng
    data = {
        "close": [100 + i * 0.1 for i in range(num_rows)],
        "open": [100 + i * 0.1 - 0.5 for i in range(num_rows)],
        "high": [100 + i * 0.1 + 1.0 for i in range(num_rows)],
        "low": [100 + i * 0.1 - 1.0 for i in range(num_rows)],
        "volume": [1000 + i * 10 for i in range(num_rows)],
    }
    df = pd.DataFrame(data)
    df["date"] = pd.date_range(start="2024-01-01", periods=len(df), freq="1min")
    # Thêm các cột 'gốc' mà feature_engineering_standard có thể cần
    # df['high'] = df['high'] # Đã có
    # df['low'] = df['low']   # Đã có
    # df['close'] = df['close']# Đã có
    return df


# --- Test Functions ---


def test_feature_engineering_produces_fit_inputs(
    model_in_train_mode, sample_dataframe, full_config
):
    """
    Tests if feature_engineering steps successfully produce the columns
    needed by the fit() method when in 'train' mode.
    This does NOT test the FreqAI framework calling fit(), only the prerequisites.
    """
    model = model_in_train_mode
    df = sample_dataframe
    freqai_config = full_config.get("freqai", {})
    required_features_for_rl = freqai_config.get("features", [])

    print(f"\nTesting prerequisites for fit() with {len(df)} data rows...")
    print(f"LSTM Window Size: {LSTM_WINDOW_SIZE}, Label Column: {LSTM_LABEL_COL}")
    print(f"LSTM Input Features: {LSTM_FEATURE_COLS}")
    print(f"Features required by RL model: {required_features_for_rl}")

    # 1. Chạy feature_engineering_standard
    try:
        print("Running feature_engineering_standard...")
        df_std = model.feature_engineering_standard(df.copy())  # Dùng copy để tránh thay đổi df gốc
        assert df_std is not None, "feature_engineering_standard returned None"
        print("feature_engineering_standard finished.")
        # Kiểm tra sơ bộ vài chỉ báo chuẩn
        assert "rsi" in df_std.columns, "Standard feature 'rsi' missing"
        assert "atr" in df_std.columns, "Standard feature 'atr' missing"
    except Exception as e:
        pytest.fail(f"feature_engineering_standard raised an exception: {e}", pytrace=True)

    # 2. Chạy feature_engineering_expand_all (quan trọng)
    # Lưu ý: Bước này trong test sẽ không có DataKitchen scaling thực sự.
    # Nó sẽ dùng dữ liệu từ df_std (bao gồm các cột gốc OHLCV và chỉ báo chuẩn)
    # để tạo cửa sổ và chạy inference LSTM (trên model chưa train).
    try:
        print("Running feature_engineering_expand_all (simulating train mode)...")
        df_expanded = model.feature_engineering_expand_all(df_std.copy())
        assert df_expanded is not None, "feature_engineering_expand_all returned None"
        print("feature_engineering_expand_all finished.")
    except Exception as e:
        pytest.fail(f"feature_engineering_expand_all raised an exception: {e}", pytrace=True)

    # 3. Kiểm tra các cột đầu ra CẦN THIẾT cho fit()
    print("Verifying required columns for fit()...")
    assert LSTM_LABEL_COL in df_expanded.columns, (
        f"CRITICAL FOR FIT: LSTM Label column '{LSTM_LABEL_COL}' was not generated."
    )
    assert "lstm_input_windows" in df_expanded.columns, (
        f"CRITICAL FOR FIT: LSTM input window column 'lstm_input_windows' was not generated (or was deleted)."
    )

    # 4. Kiểm tra tính hợp lệ của các cột cho fit()
    print("Verifying content validity for fit()...")
    # Kiểm tra label có giá trị không
    assert not df_expanded[LSTM_LABEL_COL].isnull().all(), (
        f"LSTM Label column '{LSTM_LABEL_COL}' contains only NaNs."
    )
    # Kiểm tra label có ít nhất một giá trị khác 0 (Hold) không? (Tùy chọn, tùy logic label)
    # assert (df_expanded[LSTM_LABEL_COL] != 0).any(), \
    #     f"LSTM Label column '{LSTM_LABEL_COL}' only contains 0 (Hold) values in this test data."

    # Kiểm tra cột cửa sổ
    assert not df_expanded["lstm_input_windows"].isnull().all(), (
        "LSTM window column 'lstm_input_windows' contains only NaNs/None."
    )

    # Kiểm tra một vài cửa sổ hợp lệ đầu tiên (sau đoạn None ban đầu)
    first_valid_window_index = df_expanded["lstm_input_windows"].first_valid_index()
    if first_valid_window_index is not None:
        print(f"Checking first valid LSTM window at index {first_valid_window_index}...")
        first_valid_window = df_expanded.loc[first_valid_window_index, "lstm_input_windows"]
        assert isinstance(first_valid_window, np.ndarray), (
            f"First valid LSTM window is not a numpy array (type: {type(first_valid_window)})."
        )
        expected_shape = (LSTM_WINDOW_SIZE, len(LSTM_FEATURE_COLS))
        assert first_valid_window.shape == expected_shape, (
            f"First valid LSTM window has incorrect shape. Expected {expected_shape}, got {first_valid_window.shape}."
        )
        assert not np.isnan(first_valid_window).any(), (
            "First valid LSTM window contains NaN values."
        )
    else:
        pytest.fail("Could not find any valid (non-None) LSTM window in 'lstm_input_windows'.")

    # 5. Kiểm tra các cột output LSTM (cần cho RL model)
    print("Verifying LSTM output features (for RL model)...")
    for i in range(model.lstm_output_size):
        col_name = f"lstm_pred_{i}"
        assert col_name in df_expanded.columns, f"LSTM output feature '{col_name}' missing."
        assert not df_expanded[col_name].isnull().all(), (
            f"LSTM output feature '{col_name}' contains only NaNs."
        )

    # 6. Kiểm tra sự tồn tại của tất cả features yêu cầu bởi RL model
    print("Verifying all features required by the main RL model exist...")
    missing_rl_features = [f for f in required_features_for_rl if f not in df_expanded.columns]
    assert not missing_rl_features, (
        f"Features required by RL model (config.freqai.features) are MISSING from the final dataframe: {missing_rl_features}"
    )

    print(
        "\nSUCCESS: Feature engineering steps produced necessary columns for fit() and RL model input."
    )


# --- Có thể thêm các test khác ---
# def test_custom_reward_initialization():
#     # Test riêng việc khởi tạo reward class (nếu có thể)
#     pass
