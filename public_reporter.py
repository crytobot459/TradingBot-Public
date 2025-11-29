# --- START OF FILE public_reporter.py ---
import json
import time
import requests
import logging
from pathlib import Path
from datetime import datetime
import html

# ==============================================================================
# --- CẤU HÌNH (SỬA LẠI CHO PHÙ HỢP VỚI BẠN) ---
# ==============================================================================

# 1. Token của Bot Telegram MỚI (Dùng để gửi tin miễn phí)
PUBLIC_BOT_TOKEN = "7808261052:AAHmvA1TkCmwylBZeKMgV3SMFbadkNnIPLU"
# 2. ID của Public Channel (Ví dụ: @MyFreeSignals)
PUBLIC_CHANNEL_ID = "@WarhorseDemoSignals_bot"

# Đường dẫn đến file dữ liệu của Bot Chính (Phải trỏ đúng thư mục user_data của bot chính)
USER_DATA_DIR = Path("user_data") 
TRADE_PLAN_PATH = USER_DATA_DIR / "trade_plan.json"

# Cấu hình Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] PUBLIC REPORTER: %(message)s"
)

# ==============================================================================
# --- CÁC HÀM XỬ LÝ ---
# ==============================================================================

def send_telegram_message(message: str):
    """Gửi tin nhắn đến Public Channel"""
    url = f"https://api.telegram.org/bot{PUBLIC_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': PUBLIC_CHANNEL_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("✅ Đã gửi báo cáo công khai thành công.")
    except Exception as e:
        logging.error(f"❌ Lỗi gửi Telegram: {e}")

def format_public_report(data: dict) -> str:
    """
    Tạo nội dung báo cáo 'rút gọn' (Teaser) cho cộng đồng miễn phí.
    Chỉ hiện DEFCON và Tên Coin, giấu Entry/SL chi tiết.
    """
    market_state = data.get("market_state", {})
    pairs_data = data.get("pairs", {})
    
    # 1. Tiêu đề & Thời gian
    timestamp = datetime.now().strftime('%d/%m %H:%M')
    emoji_map = {
        "DEFCON 1": "🔴 MAX RISK",
        "DEFCON 2": "qh HIGH RISK",
        "DEFCON 3": "⚠️ CAUTION",
        "DEFCON 4": "🟢 STABLE",
        "DEFCON 5": "🚀 UPTREND"
    }
    
    level_raw = market_state.get('level', 'UNKNOWN')
    # Lấy level rút gọn (ví dụ "DEFCON 4") để map emoji
    level_key = next((k for k in emoji_map if k in level_raw), "UNKNOWN")
    level_display = emoji_map.get(level_key, level_raw)
    
    msg = f"📡 <b>MARKET INTELLIGENCE REPORT</b> 📡\n"
    msg += f"🕒 <i>Update: {timestamp} (UTC+7)</i>\n\n"
    
    # 2. Tình trạng thị trường (DEFCON)
    msg += f"<b>🛡️ Market Status: {level_display}</b>\n"
    narrative = market_state.get('narrative', 'No data.')
    # Rút gọn narrative để không lộ quá nhiều logic
    if len(narrative) > 150:
        narrative = narrative[:145] + "..."
    msg += f"<i>📝 Insight: {html.escape(narrative)}</i>\n\n"
    
    # 3. Top Coins (Lọc ra các coin ngon nhất)
    # Sắp xếp theo điểm số (score) giảm dần
    sorted_pairs = sorted(
        pairs_data.items(), 
        key=lambda x: x[1].get('score', 0), 
        reverse=True
    )
    
    msg += "<b>🔥 TOP POTENTIAL SETUPS (H1/M15):</b>\n"
    
    if not sorted_pairs:
        msg += "<i>(No high-probability setups detected this hour)</i>"
    else:
        # Chỉ lấy Top 5 để gửi miễn phí
        for i, (pair, info) in enumerate(sorted_pairs[:5]):
            strategy = info.get('strategy_type', 'N/A')
            score = info.get('score', 0)
            stance = info.get('tactical_stance', 'NORMAL')
            
            # Icon chiến lược
            strat_icon = "💥" if "Explosion" in strategy else "🌊" if "Pullback" in strategy else "🎯"
            
            msg += f"{i+1}. <b>{pair}</b> {strat_icon}\n"
            msg += f"   ├ Strategy: <i>{strategy}</i>\n"
            msg += f"   ├ Quality Score: <b>{score:.0f}/100</b>\n"
            msg += f"   └ Mode: <b>{stance}</b>\n\n"
            
    # 4. Footer (Call To Action - Dẫn về thuê bạn)
    msg += "----------------------------------\n"
    msg += "🤖 <i>This is an automated report from my AI Trading System.</i>\n"
    msg += "💼 <b>Want a bot like this? Hire me on Upwork!</b>\n"
    msg += "👉 <a href='LINK_UPWORK_CUA_BAN'>Click here to view my profile</a>"
    
    return msg

def main():
    logging.info("Khởi động Public Reporter...")
    
    # Kiểm tra file tồn tại
    if not TRADE_PLAN_PATH.exists():
        logging.error(f"Không tìm thấy file {TRADE_PLAN_PATH}. Hãy chạy automation_manager.py trước!")
        return

    last_modified_time = 0
    
    while True:
        try:
            # Kiểm tra thời gian sửa đổi file
            current_mtime = TRADE_PLAN_PATH.stat().st_mtime
            
            # Nếu file mới được cập nhật (Bot chính vừa chạy xong)
            if current_mtime > last_modified_time:
                logging.info("Phát hiện dữ liệu mới! Đang xử lý báo cáo...")
                
                # Đọc dữ liệu
                with open(TRADE_PLAN_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Tạo nội dung báo cáo
                message = format_public_report(data)
                
                # Gửi tin nhắn
                send_telegram_message(message)
                
                # Cập nhật thời gian
                last_modified_time = current_mtime
                logging.info("Hoàn tất. Chờ chu kỳ tiếp theo...")
            
            # Ngủ 60s rồi kiểm tra lại
            time.sleep(60)
            
        except Exception as e:
            logging.error(f"Lỗi vòng lặp chính: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()