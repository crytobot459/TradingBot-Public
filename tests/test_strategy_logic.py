# test_strategy_logic.py

from datetime import datetime, timezone

import numpy as np  # Thêm import numpy
import pandas as pd
import pytest
from rsi_pattern_strategy_mtf_v2 import HTF_TREND_SECONDARY  # PROCESSED_HTFS # Bỏ comment nếu cần
from rsi_pattern_strategy_mtf_v2 import (  # CANDLE_SR_N_PERIODS_HTF, CANDLE_SR_WEIGHT_BASE_HTF, # Bỏ comment nếu cần; RSI_PERIODS_FOR_SR_HTF, RSI_SR_WEIGHT_BASE_HTF, # Bỏ comment nếu cần; HTF_KEY_LEVEL_WEIGHT_IN_POI, POI_CLUSTER_PROXIMITY_PERCENT, # Bỏ comment nếu cần; MIN_CONFLUENCE_SCORE_POI, # Bỏ comment nếu cần
    EMA_PERIOD_HTF,
    HTF_KEY_LEVEL_LOOKBACK,
    HTF_KEY_LEVEL_TIMEFRAME,
    HTF_TREND_PRIMARY,
    RsiPatternStrategyMTF2,
)


@pytest.fixture
def strategy_config():
    """Cung cấp một cấu hình strategy cơ bản."""
    return {
        "timeframe": "1m",
        "minimal_roi": {"0": 0.01},
        "stoploss": -0.05,
        # Thêm các cấu hình khác của strategy nếu cần cho test
    }


@pytest.fixture
def strategy(strategy_config):
    """Khởi tạo chiến lược để test (không dùng dp/phụ thuộc ngoài)."""
    # Trong môi trường test thực tế của Freqtrade, config sẽ được truyền vào
    # nhưng ở đây chúng ta khởi tạo trực tiếp cho test đơn vị logic.
    # Nếu các hàm test của bạn gọi đến self.dp, bạn cần mock nó.
    # Ví dụ: strategy_instance.dp = MagicMock()
    return RsiPatternStrategyMTF2(config=strategy_config)


@pytest.fixture
def sample_dataframe_htf_key_levels():
    """DataFrame mẫu để test HTF Key Levels."""
    # Sử dụng HTF_KEY_LEVEL_LOOKBACK từ module chiến lược
    lookback_periods = HTF_KEY_LEVEL_LOOKBACK
    data_length = lookback_periods + 5

    data = {
        "date": pd.date_range(
            start="2023-01-01", periods=data_length, freq="1h", tz=timezone.utc
        ),  # Thêm tz
        "open": list(range(100, 100 + data_length)),
        "high": [120 if i == 5 else (105 + i) for i in range(data_length)],
        "low": [80 if i == 7 else (95 - i) for i in range(data_length)],
        "close": list(range(102, 102 + data_length)),
        "volume": [1000] * data_length,
    }
    df = pd.DataFrame(data)
    df.set_index("date", inplace=True)
    return df


def test_htf_key_level_calculation(strategy, sample_dataframe_htf_key_levels):
    """Test tính toán HTF Key Levels: htf_key_low, htf_key_high."""
    df = sample_dataframe_htf_key_levels
    # Gọi hàm populate trực tiếp (trong test đơn vị, không qua informative decorator)
    result_df = strategy._populate_common_htf_indicators(df.copy(), HTF_KEY_LEVEL_TIMEFRAME)

    key_low_col = "htf_key_low"  # Tên cột được định nghĩa trong _populate_common_htf_indicators
    key_high_col = "htf_key_high"

    assert key_low_col in result_df.columns
    assert key_high_col in result_df.columns

    # Kiểm tra giá trị sau khi shift(1) và rolling
    # Dữ liệu tại result_df.iloc[HTF_KEY_LEVEL_LOOKBACK] sẽ được tính toán dựa trên
    # cửa sổ df.iloc[0 : HTF_KEY_LEVEL_LOOKBACK-1] (tức là 20 bản ghi đầu tiên nếu LOOKBACK=20)
    if len(result_df) > HTF_KEY_LEVEL_LOOKBACK:
        # Giá trị 'low' trong 20 bản ghi đầu (index 0 đến 19):
        # low[0]=95, low[1]=94, ..., low[7]=80, ..., low[19]=95-19=76. Min là 76.
        expected_key_low = 76.0

        # Giá trị 'high' trong 20 bản ghi đầu (index 0 đến 19):
        # high[0]=105, high[1]=106, ..., high[5]=120, ..., high[19]=105+19=124. Max là 124.
        expected_key_high = 124.0

        actual_key_low = result_df[key_low_col].iloc[HTF_KEY_LEVEL_LOOKBACK]
        actual_key_high = result_df[key_high_col].iloc[HTF_KEY_LEVEL_LOOKBACK]

        assert pd.notna(actual_key_low), "Key low không nên là NaN"
        assert pd.notna(actual_key_high), "Key high không nên là NaN"

        assert actual_key_low == expected_key_low, (
            f"Expected {expected_key_low}, got {actual_key_low}"
        )
        assert actual_key_high == expected_key_high, (
            f"Expected {expected_key_high}, got {actual_key_high}"
        )

        # Kiểm tra một vài giá trị NaN ở đầu do rolling và shift
        assert pd.isna(result_df[key_low_col].iloc[0]), (
            "Giá trị đầu tiên của key_low phải là NaN do shift"
        )
        assert pd.isna(result_df[key_high_col].iloc[0]), (
            "Giá trị đầu tiên của key_high phải là NaN do shift"
        )
        if HTF_KEY_LEVEL_LOOKBACK > 1:  # Nếu lookback đủ lớn để tạo NaN sau shift
            assert pd.isna(result_df[key_low_col].iloc[1]), (
                "Giá trị thứ hai của key_low phải là NaN"
            )


def test_get_htf_sr_levels(strategy):
    """Test lấy danh sách các mức HTF S/R từ nến."""
    now = datetime(
        2023, 1, 2, 10, 0, 0, tzinfo=timezone.utc
    )  # Quan trọng: dùng tzinfo=timezone.utc

    # Tạo một Series mẫu đầy đủ hơn, bao gồm cả các cột mà _get_htf_sr_levels sẽ tìm kiếm
    # Dựa trên PROCESSED_HTFS và CANDLE_SR_N_PERIODS_HTF
    candle_data = {
        "date": now,
        "close_1m": 101.0,  # Giả sử giá hiện tại của timeframe cơ sở
        # HTF Key Levels (giả sử HTF_KEY_LEVEL_TIMEFRAME là '4h')
        f"htf_key_low_{HTF_KEY_LEVEL_TIMEFRAME}": 90.0,
        f"htf_key_high_{HTF_KEY_LEVEL_TIMEFRAME}": 110.0,
    }

    # Thêm các mức S/R từ nến và RSI cho các timeframe trong PROCESSED_HTFS
    # Đây là một ví dụ cho '1h' và '4h'
    # '1h'
    candle_data[f"prev_low_N10_1h"] = 95.0
    candle_data[f"prev_high_N10_1h"] = 105.0
    candle_data[f"prev_low_N15_1h"] = 94.0
    candle_data[f"prev_high_N15_1h"] = 106.0
    candle_data[f"sup_rsi14_1h"] = 96.0
    candle_data[f"res_rsi14_1h"] = 107.0  # Đổi thành 107 để khác với prev_high

    # '4h' (giả sử cũng có các chỉ báo này, và HTF_KEY_LEVEL_TIMEFRAME='4h' đã có ở trên)
    candle_data[f"prev_low_N15_4h"] = 92.0
    candle_data[f"prev_high_N15_4h"] = 108.0
    candle_data[f"prev_low_N20_4h"] = 91.0
    candle_data[f"prev_high_N20_4h"] = 109.0
    candle_data[f"sup_rsi14_4h"] = 93.0
    candle_data[f"res_rsi14_4h"] = 111.0  # Đổi để khác

    # Thêm các cột trend nếu hàm _get_htf_sr_levels hoặc các hàm nó gọi có sử dụng
    # (Hiện tại _get_htf_sr_levels không trực tiếp dùng, nhưng để đầy đủ)
    candle_data[f"close_{HTF_TREND_PRIMARY}"] = 210.0
    candle_data[f"ema{EMA_PERIOD_HTF}_{HTF_TREND_PRIMARY}"] = 200.0
    candle_data[f"close_{HTF_TREND_SECONDARY}"] = 105.0
    candle_data[f"ema{EMA_PERIOD_HTF}_{HTF_TREND_SECONDARY}"] = 100.0

    candle = pd.Series(candle_data)

    levels = strategy._get_htf_sr_levels(
        candle, "BTC/USDT", 123
    )  # candle_idx là tùy ý cho test này

    assert isinstance(levels, list)
    assert len(levels) > 0, "Phải có ít nhất một vài level được tìm thấy"

    # Kiểm tra sự tồn tại của các loại level mong đợi
    # Lưu ý: các type này phụ thuộc vào định nghĩa trong _get_htf_sr_levels
    # và các hằng số như CANDLE_SR_N_PERIODS_HTF
    found_sup_htf_key = any(
        l["type"] == "Sup_HTFKey" and l["tf"] == HTF_KEY_LEVEL_TIMEFRAME for l in levels
    )
    found_res_htf_key = any(
        l["type"] == "Res_HTFKey" and l["tf"] == HTF_KEY_LEVEL_TIMEFRAME for l in levels
    )
    found_sup_candle_n = any(l["type"].startswith("Sup_CandleN") for l in levels)
    found_res_candle_n = any(l["type"].startswith("Res_CandleN") for l in levels)
    found_sup_rsi = any(l["type"].startswith("Sup_RSI") for l in levels)
    found_res_rsi = any(l["type"].startswith("Res_RSI") for l in levels)

    assert found_sup_htf_key, f"Không tìm thấy Sup_HTFKey cho timeframe {HTF_KEY_LEVEL_TIMEFRAME}"
    assert found_res_htf_key, f"Không tìm thấy Res_HTFKey cho timeframe {HTF_KEY_LEVEL_TIMEFRAME}"
    assert found_sup_candle_n, "Không tìm thấy Sup_CandleN"
    assert found_res_candle_n, "Không tìm thấy Res_CandleN"
    assert found_sup_rsi, "Không tìm thấy Sup_RSI"
    assert found_res_rsi, "Không tìm thấy Res_RSI"

    # Kiểm tra một giá trị cụ thể nếu cần
    expected_htf_key_low_level = candle_data[f"htf_key_low_{HTF_KEY_LEVEL_TIMEFRAME}"]
    htf_key_low_in_levels = next(
        (l for l in levels if l["type"] == "Sup_HTFKey" and l["tf"] == HTF_KEY_LEVEL_TIMEFRAME),
        None,
    )
    assert htf_key_low_in_levels is not None, "Sup_HTFKey level bị thiếu"
    assert htf_key_low_in_levels["level"] == expected_htf_key_low_level

    # Kiểm tra số lượng level mong đợi (có thể thay đổi tùy theo cấu hình)
    # Ví dụ: 2 (HTFKey) + 2*2 (CandleN 1h) + 2 (RSI 1h) + 2*2 (CandleN 4h) + 2 (RSI 4h)
    # Đây là một ước tính, bạn cần tính toán chính xác dựa trên PROCESSED_HTFS và CANDLE_SR_N_PERIODS_HTF
    # trong chiến lược của bạn.
    # Ví dụ: PROCESSED_HTFS = ['1d', '4h', '1h', '30m', '15m', '5m']
    # CANDLE_SR_N_PERIODS_HTF = {'1d': [20, 30], '4h': [15, 20], '1h': [10, 15], ...}
    # RSI_PERIODS_FOR_SR_HTF = [14] (1 cặp sup/res cho mỗi tf)
    # HTF_KEY_LEVEL_WEIGHT_IN_POI > 0 (1 cặp sup/res cho HTF_KEY_LEVEL_TIMEFRAME)
    # Giả sử dữ liệu mẫu chỉ cung cấp cho 1h và 4h, và HTF_KEY_LEVEL_TIMEFRAME='4h'
    # HTFKey ('4h'): 2
    # CandleN '1h' (N10, N15): 2*2 = 4
    # RSI '1h' (rsi14): 2
    # CandleN '4h' (N15, N20): 2*2 = 4
    # RSI '4h' (rsi14): 2
    # Tổng cộng dự kiến: 2+4+2+4+2 = 14
    assert len(levels) == 14, f"Số lượng S/R levels không như kỳ vọng. Got: {len(levels)}"
    for level_info in levels:
        assert "level" in level_info
        assert "tf" in level_info
        assert "type" in level_info
        assert "weight" in level_info
        assert isinstance(level_info["level"], float)
        assert isinstance(level_info["weight"], float)


# Bạn có thể thêm các bài test khác cho các phần logic khác của chiến lược ở đây
# Ví dụ: _cluster_sr_levels, _analyze_htf_context_for_base_tf_candle,
# populate_indicators, populate_entry_trend, v.v.
# Đối với các hàm gọi self.dp, bạn sẽ cần mock self.dp.get_analyzed_dataframe()
# hoặc các phương thức khác của DataProvider.


# Ví dụ test cho populate_indicators (cần DataFrame có sẵn các cột OHLCV)
@pytest.fixture
def sample_dataframe_ohlcv():
    data_length = 50  # Cần đủ dữ liệu cho các chỉ báo TA-Lib
    dates = pd.date_range(start="2023-01-01", periods=data_length, freq="1m", tz=timezone.utc)
    data = {
        "date": dates,
        "open": np.random.rand(data_length) * 10 + 100,
        "high": np.random.rand(data_length) * 5 + 105,  # high > open
        "low": np.random.rand(data_length) * -5 + 95,  # low < open
        "close": np.random.rand(data_length) * 10 + 100,
        "volume": np.random.rand(data_length) * 1000 + 500,
    }
    # Đảm bảo high >= open, close và low <= open, close
    df = pd.DataFrame(data)
    df["high"] = df[["high", "open", "close"]].max(axis=1)
    df["low"] = df[["low", "open", "close"]].min(axis=1)
    df.set_index("date", inplace=True)
    return df


def test_populate_indicators(strategy, sample_dataframe_ohlcv):
    """Test việc tạo các chỉ báo cơ bản trên timeframe chính."""
    metadata = {"pair": "BTC/USDT"}
    df = strategy.populate_indicators(sample_dataframe_ohlcv.copy(), metadata)

    tf_suffix = f"_{strategy.timeframe}"
    assert f"rsi{RSI_BASE_TF_P_SHORT}{tf_suffix}" in df.columns
    assert f"rsi{RSI_BASE_TF_P_MID}{tf_suffix}" in df.columns
    assert f"rsi{RSI_BASE_TF_P_LONG}{tf_suffix}" in df.columns
    assert f"atr_{ATR_PERIOD_BASE_TF_STOP}{tf_suffix}" in df.columns
    assert "rsi_chum_spread" in df.columns
    assert f"cond_{strategy.timeframe}_rsi_chum_curr" in df.columns
    assert f"cdl_hammer{tf_suffix}" in df.columns  # Ví dụ một chỉ báo nến

    # Kiểm tra giá trị NaN ở đầu (do tính toán chỉ báo)
    assert pd.isna(df[f"rsi{RSI_BASE_TF_P_SHORT}{tf_suffix}"].iloc[0])
    # Kiểm tra giá trị không NaN sau một số kỳ nhất định
    # (RSI_BASE_TF_P_SHORT là số kỳ tối thiểu cho RSI)
    if len(df) > RSI_BASE_TF_P_SHORT:
        assert pd.notna(df[f"rsi{RSI_BASE_TF_P_SHORT}{tf_suffix}"].iloc[RSI_BASE_TF_P_SHORT])

    # Kiểm tra các cột debug được khởi tạo
    assert "poi_sup_level" in df.columns
    assert "final_entry_sl" in df.columns  # Một trong những cột debug cuối cùng được thêm
