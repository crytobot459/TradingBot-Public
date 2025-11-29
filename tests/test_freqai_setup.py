# --- START OF FILE user_data/tests/test_freqai_setup.py ---
import logging

# Tạm thời thêm user_data vào sys.path để import các module tùy chỉnh
# Điều này có thể cần thiết tùy thuộc vào cách bạn chạy unittest
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # Thêm thư mục gốc freqtrade
sys.path.insert(0, str(Path(__file__).parent.parent))  # Thêm user_data

# Freqtrade imports (đảm bảo môi trường ảo đã được kích hoạt)
try:
    from freqaimodels.my_custom_reward import MyCustomReward

    # Import các lớp tùy chỉnh của bạn
    from freqaimodels.MyComprehensiveRLModel import MyComprehensiveRLModel

    from freqtrade.constants import Config
    from freqtrade.freqai.freqai_interface import IFreqaiModel
    from freqtrade.persistence import Trade
except ImportError as e:
    print(f"Error importing Freqtrade modules: {e}")
    print("Make sure your virtual environment is activated and Freqtrade is installed.")
    sys.exit(1)

# Tắt bớt logging không cần thiết trong test
logging.basicConfig(level=logging.WARNING)
log = logging.getLogger(__name__)

# --- Mẫu Config gần giống với config của bạn ---
# (Loại bỏ các phần không liên quan trực tiếp đến FreqAI để đơn giản hóa)
SAMPLE_CONFIG: Config = {
    "max_open_trades": 3,
    "stake_currency": "USDT",
    "stake_amount": 20,
    "dry_run": True,
    "initial_state": "running",
    "strategy": "MyFreqAIStrategy",  # Quan trọng để model đọc config động
    "freqaimodel": "MyComprehensiveRLModel",  # Thêm mục này để nhất quán
    "exchange": {
        "name": "binance",
        "pair_whitelist": ["BTC/USDT", "ETH/USDT", "BNB/USDT"],
    },
    "pairlists": [{"method": "StaticPairList"}],
    "freqai": {
        "enabled": True,
        "identifier": "FreshTrain_May03_Test",  # Sử dụng identifier riêng cho test
        "train_period_days": 30,
        "backtest_period_days": 7,
        "freqai_info": {
            "feature_engineering_module": "user_data.freqaimodels.MyComprehensiveRLModel",
            "feature_engineering_class": "MyComprehensiveRLModel",
            "rl_reward_function_module": "user_data.freqaimodels.my_custom_reward",
            "rl_reward_function": "MyCustomReward",
            "model_training_parameters": {
                "custom_rl_config": {
                    # Đảm bảo có khóa khớp với strategy_name_from_config
                    "MyFreqAIStrategy": {
                        "enable_intermediate_loss_exit": True,
                        "intermediate_loss_pct_threshold": 0.02,
                        "enable_indicator_reversal_exit": False,
                        "indicator_reversal_rsi_threshold": 30.0,
                        "indicator_reversal_macd_cross": True,
                        "enable_trailing_stop": True,
                        "stop_loss_atr_multiplier": 2.5,
                        "take_profit_atr_multiplier": 3.0,
                        "trailing_stop_atr_multiplier": 1.5,
                    }
                },
                "custom_reward_params": {
                    "profit_reward_weight": 3.0,
                    "loss_penalty": 1.5,
                    "holding_time_penalty_weight": 0.00015,
                    "max_holding_time_penalty": 0.0005,
                    "holding_penalty_grace_period": 12,
                    "reward_clip_min": -1.0,
                    "reward_clip_max": 1.0,
                },
            },
        },
        "data_split_parameters": {"test_size": 0.2},
        "features": ["rsi", "macd_val"],  # Giảm bớt features cho test
        "states": ["open_profit_pct"],  # Giảm bớt states
        "data_kitchen_parameters": {},  # Bỏ qua chi tiết data kitchen
        "feature_parameters": {},
        "model": {
            "name": "PPO",
            "type": "rl",
            "backend": "stable_baselines3",
            "actions_to_enter": [1],
            "actions_to_exit": [2],
            "rl_config": {"n_steps": 128},  # Giảm n_steps cho test nhanh hơn nếu cần
            "total_timesteps": 1000,  # Giảm total_timesteps
        },
    },
}


class TestFreqaiTrainingSetup(unittest.TestCase):
    def setUp(self):
        """Thiết lập môi trường test."""
        # Tạo config copy để tránh thay đổi global
        self.config = SAMPLE_CONFIG.copy()
        # Mô phỏng freqai_info được truyền vào FreqAI model constructor
        self.freqai_info_mock = self.config.get("freqai", {}).get("freqai_info", {})
        self.freqai_info_mock["feature_list"] = self.config.get("freqai", {}).get("features", [])
        self.freqai_info_mock["state_list"] = self.config.get("freqai", {}).get("states", [])
        self.freqai_info_mock["label_list"] = [
            "&enter_long",
            "&exit_long",
            "enter_tag",
            "exit_tag",
        ]  # Typical labels

    def test_01_my_comprehensive_rl_model_initialization(self):
        """Kiểm tra xem MyComprehensiveRLModel có khởi tạo và đọc config đúng không."""
        log.info("Running test_01_my_comprehensive_rl_model_initialization")
        try:
            # Truyền freqai_info đã được chuẩn bị
            model = MyComprehensiveRLModel(config=self.config)
            model.freqai_info = self.freqai_info_mock  # Gán freqai_info giả lập

            # Kiểm tra xem strategy_name có được đọc đúng không
            self.assertEqual(model.strategy_name_from_config, "MyFreqAIStrategy")

            # Kiểm tra xem các tham số động có được đọc từ cấu trúc lồng nhau không
            self.assertTrue(model.enable_intermediate_loss_exit)
            self.assertEqual(model.intermediate_loss_pct_threshold, 0.02)
            self.assertFalse(model.enable_indicator_reversal_exit)
            self.assertEqual(model.indicator_reversal_rsi_threshold, 30.0)
            self.assertTrue(model.indicator_reversal_macd_cross)
            self.assertTrue(model.enable_trailing_stop)
            self.assertEqual(model.stop_loss_atr_multiplier, 2.5)
            self.assertEqual(model.take_profit_atr_multiplier, 3.0)
            self.assertEqual(model.trailing_stop_atr_multiplier, 1.5)

            log.info("MyComprehensiveRLModel initialized and read dynamic config successfully.")

        except Exception as e:
            log.exception(f"Error during MyComprehensiveRLModel initialization test: {e}")
            self.fail(f"MyComprehensiveRLModel initialization failed: {e}")

    @patch("freqtrade.freqai.freqai_interface.Path")  # Mock Path để kiểm tra file model
    def test_02_freqai_core_initialization_and_params(self, MockPath):
        """Kiểm tra xem lớp FreqAI có đọc đúng các tham số cơ bản từ config không."""
        log.info("Running test_02_freqai_core_initialization_and_params")

        # --- Giả lập môi trường: Không có model tồn tại ---
        # Cấu hình mock Path(...).exists() trả về False
        # Giả sử đường dẫn model được kiểm tra là `user_data/models/IDENTIFIER/model.zip`
        identifier = self.config["freqai"]["identifier"]
        mock_model_path_instance = MagicMock()
        mock_model_path_instance.exists.return_value = False  # Giả lập file không tồn tại
        # Mock hàm tạo Path để trả về instance đã được cấu hình khi đường dẫn cụ thể được gọi
        # Cần xác định chính xác đường dẫn mà FreqAI sẽ kiểm tra
        # Dựa trên mã nguồn FreqAI (có thể thay đổi):
        expected_model_dir = Path("user_data/models") / identifier
        expected_model_file = expected_model_dir / f"{self.config['strategy']}_{identifier}.zip"

        def path_side_effect(*args, **kwargs):
            path_requested = Path(*args)
            log.debug(f"Mock Path called with: {path_requested}")
            if path_requested == expected_model_file.parent:  # Check for directory path
                log.debug(f"Returning mock for directory: {expected_model_file.parent}")
                dir_mock = MagicMock(spec=Path)
                dir_mock.exists.return_value = False  # Giả lập thư mục không tồn tại
                dir_mock.__truediv__.return_value = expected_model_file  # Path / filename
                return dir_mock
            elif path_requested == expected_model_file:  # Check for file path
                log.debug(f"Returning mock for file: {expected_model_file}")
                file_mock = MagicMock(spec=Path)
                file_mock.exists.return_value = False  # Giả lập file không tồn tại
                return file_mock
            else:
                # Return a default mock or raise error for unexpected paths
                log.debug(f"Returning default Path mock for: {path_requested}")
                default_mock = MagicMock(spec=Path)
                default_mock.exists.return_value = False  # Default to not existing
                return default_mock

        MockPath.side_effect = path_side_effect
        # MockPath.return_value = mock_model_path_instance # Cách mock đơn giản hơn nếu chỉ kiểm tra 1 path

        # --- Khởi tạo FreqAI ---
        # FreqAI constructor cần thêm một số đối số mà bot thường cung cấp
        # Chúng ta sẽ dùng MagicMock để giả lập chúng
        mock_dp = MagicMock()  # Giả lập DataProvider
        mock_exchange = MagicMock()  # Giả lập Exchange
        mock_strategy = MagicMock()  # Giả lập Strategy object
        mock_strategy.timeframe = "5m"  # Cần thiết cho một số logic bên trong

        try:
            freqai = FreqAI(self.config, mock_strategy, mock_dp, mock_exchange)

            # Kiểm tra các thuộc tính cơ bản đọc từ config
            self.assertTrue(freqai.config["freqai"]["enabled"])
            self.assertEqual(freqai.identifier, identifier)
            self.assertEqual(freqai.config["freqai"]["train_period_days"], 30)
            self.assertEqual(freqai.config["freqai"]["backtest_period_days"], 7)
            self.assertEqual(
                freqai.freqai_info.get("feature_engineering_class"), "MyComprehensiveRLModel"
            )
            self.assertEqual(freqai.freqai_info.get("rl_reward_function"), "MyCustomReward")

            # Kiểm tra (gián tiếp) xem việc không tìm thấy model có được nhận diện không
            # Trong FreqAI, việc huấn luyện được thêm vào hàng đợi `collect_all_pairs_and_train`
            # Chúng ta có thể kiểm tra xem hàng đợi đó có chứa các cặp không
            # Lưu ý: Đây là kiểm tra implementation detail, có thể thay đổi giữa các phiên bản
            self.assertIn("BTC/USDT", freqai.pairs_to_train)
            self.assertIn("ETH/USDT", freqai.pairs_to_train)
            self.assertIn("BNB/USDT", freqai.pairs_to_train)
            log.info(f"FreqAI initialized. Training queue contains pairs: {freqai.pairs_to_train}")
            log.info(
                "Indicates that the need for training (due to non-existent model) was likely detected."
            )

        except Exception as e:
            log.exception(f"Error during FreqAI initialization test: {e}")
            self.fail(f"FreqAI initialization failed: {e}")

    def test_03_custom_reward_calculation(self):
        """Kiểm tra xem hàm reward tùy chỉnh có tính toán reward cơ bản không."""
        log.info("Running test_03_custom_reward_calculation")
        # --- Thiết lập ---
        # Tạo instance của lớp reward (nó kế thừa ReinforcementLearner, cần freqai_info)
        reward_calculator = MyCustomReward.__new__(
            MyCustomReward
        )  # Tạo instance mà không gọi __init__
        reward_calculator.freqai_info = self.freqai_info_mock  # Gán freqai_info giả lập

        # Tạo trade giả lập (đã đóng, có lãi)
        trade_profit = MagicMock(spec=Trade)
        trade_profit.is_open = False
        trade_profit.close_profit_pct = 0.05  # 5% profit
        trade_profit.id = 1

        # Tạo trade giả lập (đã đóng, lỗ)
        trade_loss = MagicMock(spec=Trade)
        trade_loss.is_open = False
        trade_loss.close_profit_pct = -0.03  # 3% loss
        trade_loss.id = 2

        # Tạo trade giả lập (đang mở, giữ lâu)
        trade_open_long = MagicMock(spec=Trade)
        trade_open_long.is_open = True
        trade_open_long.id = 3
        trade_open_long.trade_duration = 100  # Giữ 100 phút (nến)
        # Mock hàm calculate_profit_percent
        trade_open_long.calculate_profit_percent = MagicMock(return_value=0.01)  # Đang lãi nhẹ
        # Dataframe giả lập cho nến hiện tại
        df_current = pd.DataFrame({"close": [105]}, index=[pd.Timestamp("2023-01-01 12:00:00")])

        # --- Tính toán & Kiểm tra ---
        reward_p = reward_calculator.calculate_reward(trade_profit, df_current)
        reward_l = reward_calculator.calculate_reward(trade_loss, df_current)
        reward_h = reward_calculator.calculate_reward(trade_open_long, df_current)

        # Lấy trọng số từ config để kiểm tra chính xác
        profit_weight = self.freqai_info_mock["model_training_parameters"]["custom_reward_params"][
            "profit_reward_weight"
        ]
        loss_penalty = self.freqai_info_mock["model_training_parameters"]["custom_reward_params"][
            "loss_penalty"
        ]
        holding_penalty_weight = self.freqai_info_mock["model_training_parameters"][
            "custom_reward_params"
        ]["holding_time_penalty_weight"]
        grace_period = self.freqai_info_mock["model_training_parameters"]["custom_reward_params"][
            "holding_penalty_grace_period"
        ]
        max_holding_penalty = self.freqai_info_mock["model_training_parameters"][
            "custom_reward_params"
        ]["max_holding_time_penalty"]
        reward_clip_min = self.freqai_info_mock["model_training_parameters"][
            "custom_reward_params"
        ]["reward_clip_min"]
        reward_clip_max = self.freqai_info_mock["model_training_parameters"][
            "custom_reward_params"
        ]["reward_clip_max"]

        expected_reward_p = np.clip(0.05 * profit_weight, reward_clip_min, reward_clip_max)
        expected_reward_l = np.clip(-0.03 * loss_penalty, reward_clip_min, reward_clip_max)

        # Tính penalty giữ lệnh
        holding_penalty = min(
            np.sqrt(100 - grace_period) * holding_penalty_weight, max_holding_penalty
        )
        # Tính reward tiềm năng (nhỏ hơn) + penalty
        potential_profit_reward = (0.01 * profit_weight) * 0.1
        expected_reward_h = np.clip(
            potential_profit_reward - holding_penalty, reward_clip_min, reward_clip_max
        )

        log.debug(
            f"Calculated rewards: Profit={reward_p:.4f}, Loss={reward_l:.4f}, Holding={reward_h:.4f}"
        )
        log.debug(
            f"Expected rewards: Profit={expected_reward_p:.4f}, Loss={expected_reward_l:.4f}, Holding={expected_reward_h:.4f}"
        )

        # Sử dụng assertAlmostEqual để xử lý sai số float
        self.assertAlmostEqual(reward_p, expected_reward_p, places=5)
        self.assertAlmostEqual(reward_l, expected_reward_l, places=5)
        self.assertAlmostEqual(reward_h, expected_reward_h, places=5)

        log.info("Custom reward function calculated basic rewards successfully.")


if __name__ == "__main__":
    unittest.main()

# --- END OF FILE user_data/tests/test_freqai_setup.py ---
