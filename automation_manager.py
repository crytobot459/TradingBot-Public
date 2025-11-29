import json
import time
import requests
import schedule
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
import html
import pandas as pd
import ichimoku_scanner as scanner
CONFIG_PATH = 'config.json'
USER_DATA_DIR = ''
STRATEGY_OVERRIDES_FILENAME = 'strategy_overrides.json'
STRATEGY_OVERRIDES_PATH = ''
TRADE_PLAN_FILENAME = 'trade_plan.json'
TRADE_PLAN_PATH = ''
MANAGED_TRADES_FILENAME = 'managed_trades.json'
MANAGED_TRADES_PATH = ''
TRANSLATION_ENABLED = False
TRANSLATION_TARGET_LANG = 'en'
POTENTIAL_WATCHLIST_FILENAME = 'potential_watchlist.json'
POTENTIAL_WATCHLIST_PATH = ''
POTENTIAL_WATCHLIST_MIN_SCORE = 50
MAX_POTENTIAL_WATCHLIST_SIZE = 150
NORMAL_WHITELIST_SIZE = 10
CAUTION_WHITELIST_SIZE = 3
MARKET_HISTORY_FILENAME = 'market_history.json'
MARKET_HISTORY_PATH = ''
MARKET_HISTORY_MAX_ENTRIES = 72
EMERGENCY_FALLBACK_PAIR = 'USDC/USDT'
FREQTRADE_URL = ''
FT_USER = ''
FT_PASS = ''
TELEGRAM_ENABLED = False
TELEGRAM_BOT_TOKEN = ''
TELEGRAM_CHAT_ID = ''
TELEGRAM_TOP_N_TARGETS = 15
TELEGRAM_MESSAGE_CLEANUP_ENABLED = True
TELEGRAM_MESSAGE_CLEANUP_DAYS = 7
TELEGRAM_MESSAGE_LOG_FILENAME = 'telegram_message_log.json'
TELEGRAM_MESSAGE_LOG_PATH = ''
api_session = requests.Session()
exchange_instance = None
managed_manual_trade_ids = set()
BOT_OPERATIONAL_STATE = 'RUNNING'
IS_MAIN_JOB_RUNNING = False
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', handlers=[logging.FileHandler('automation_manager.log'), logging.StreamHandler()])

def load_freqtrade_api_config():
    """Load API configuration and necessary file paths from config.json.
This is an important startup function that sets global variables for the entire application."""
    global FREQTRADE_URL, FT_USER, FT_PASS, USER_DATA_DIR
    global STRATEGY_OVERRIDES_PATH, TRADE_PLAN_PATH, POTENTIAL_WATCHLIST_PATH
    global MANAGED_TRADES_PATH, MARKET_HISTORY_PATH
    global TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_MESSAGE_LOG_PATH
    global TRANSLATION_ENABLED, TRANSLATION_TARGET_LANG
    global exchange_instance
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        api_config = config['api_server']
        ip = api_config['listen_ip_address']
        port = api_config['listen_port']
        FT_USER = api_config['username']
        FT_PASS = api_config['password']
        FREQTRADE_URL = f'http://{ip}:{port}'
        USER_DATA_DIR = Path(config.get('user_data_dir', 'user_data'))
        STRATEGY_OVERRIDES_PATH = USER_DATA_DIR / STRATEGY_OVERRIDES_FILENAME
        TRADE_PLAN_PATH = USER_DATA_DIR / TRADE_PLAN_FILENAME
        POTENTIAL_WATCHLIST_PATH = USER_DATA_DIR / POTENTIAL_WATCHLIST_FILENAME
        TELEGRAM_MESSAGE_LOG_PATH = USER_DATA_DIR / TELEGRAM_MESSAGE_LOG_FILENAME
        MARKET_HISTORY_PATH = USER_DATA_DIR / MARKET_HISTORY_FILENAME
        MANAGED_TRADES_PATH = USER_DATA_DIR / MANAGED_TRADES_FILENAME
        tg_config = config.get('telegram', {})
        TELEGRAM_ENABLED = tg_config.get('enabled', False)
        TELEGRAM_BOT_TOKEN = tg_config.get('token')
        TELEGRAM_CHAT_ID = tg_config.get('chat_id')
        translation_config = config.get('translation', {})
        TRANSLATION_ENABLED = translation_config.get('enabled', False)
        TRANSLATION_TARGET_LANG = translation_config.get('target_language', 'en')
        if TRANSLATION_ENABLED:
            logging.info(f"DỊCH THUẬT TỰ ĐỘNG ĐÃ BẬT. Ngôn ngữ đích: '{TRANSLATION_TARGET_LANG}'")
        if exchange_instance is None:
            exchange_instance = scanner.initialize_exchange(scanner.EXCHANGE)
            if not exchange_instance:
                logging.critical('KHÔNG THỂ KHỞI TẠO EXCHANGE INSTANCE. Bot không thể lấy dữ liệu.')
                return False
        logging.info(f"Đã tải thành công toàn bộ cấu hình từ '{CONFIG_PATH}'")
        return True
    except FileNotFoundError:
        logging.critical(f"LỖI NGHIÊM TRỌNG: File cấu hình '{CONFIG_PATH}' không được tìm thấy!")
        return False
    except json.JSONDecodeError:
        logging.critical(f"LỖI NGHIÊM TRỌNG: File cấu hình '{CONFIG_PATH}' có định dạng JSON không hợp lệ!")
        return False
    except KeyError as e:
        logging.critical(f"LỖI NGHIÊM TRỌNG: Thiếu một khóa (key) bắt buộc trong file '{CONFIG_PATH}': {e}")
        return False
    except Exception as e:
        logging.critical(f'LỖI KHÔNG XÁC ĐỊNH khi tải cấu hình: {e}', exc_info=True)
        return False

def translate_text(text: str, target_lang: str) -> str:
    """Translate text into target language using deep-translator library.
Error safe: If translation fails, the original text will be returned."""
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        logging.error("Lỗi: Thư viện 'deep-translator' chưa được cài đặt. Vui lòng chạy 'pip install deep-translator'.")
        return text
    if not text or not text.strip():
        return text
    try:
        translated_text = GoogleTranslator(source='auto', target=target_lang).translate(text)
        return translated_text
    except Exception as e:
        logging.warning(f'Không thể dịch văn bản. Lỗi: {e}. Sử dụng văn bản gốc.')
        return text

def check_freqtrade_state() -> str:
    """Check the current operating status of the Freqtrade bot (RUNNING/STOPPED).
v1.2: Fixed using the correct /api/v1/show_config endpoint and extracting 'state' from there."""
    global BOT_OPERATIONAL_STATE
    try:
        response = api_session.get(f'{FREQTRADE_URL}/api/v1/show_config', timeout=10)
        response.raise_for_status()
        data = response.json()
        state = data.get('state', 'unknown').upper()
        if state in ['RUNNING', 'STOPPED']:
            return state
        return BOT_OPERATIONAL_STATE
    except requests.exceptions.RequestException as e:
        logging.warning(f'Không thể kiểm tra trạng thái Freqtrade, giả định trạng thái hiện tại là {BOT_OPERATIONAL_STATE}. Lỗi: {e}')
        return BOT_OPERATIONAL_STATE

def _load_managed_trades():
    """Load list of managed trade_ids from file."""
    global managed_manual_trade_ids
    if MANAGED_TRADES_PATH and MANAGED_TRADES_PATH.exists():
        try:
            with open(MANAGED_TRADES_PATH, 'r') as f:
                managed_manual_trade_ids = set(json.load(f))
            logging.info(f'Đã tải {len(managed_manual_trade_ids)} trade_id đã được quản lý.')
        except (json.JSONDecodeError, IOError):
            managed_manual_trade_ids = set()

def _save_managed_trades():
    """Save the list of managed trade_ids to file."""
    if MANAGED_TRADES_PATH:
        try:
            with open(MANAGED_TRADES_PATH, 'w') as f:
                json.dump(list(managed_manual_trade_ids), f)
        except IOError as e:
            logging.error(f'Không thể lưu file managed_trades: {e}')

def load_trade_plan():
    """Download the entire Strategy Plan (including market_state and pairs) from trade_plan.json.
Returns a dictionary with the structure {"market_state": ..., "pairs": ...}."""
    if not TRADE_PLAN_PATH.exists():
        return {'market_state': {}, 'pairs': {}}
    try:
        with open(TRADE_PLAN_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'market_state' not in data:
                data['market_state'] = {}
            if 'pairs' not in data:
                data['pairs'] = {}
            return data
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f'Lỗi khi đọc file Kế Hoạch Tác Chiến ({TRADE_PLAN_PATH}): {e}. Trả về cấu trúc rỗng.')
        return {'market_state': {}, 'pairs': {}}

def log_sent_telegram_message(message_id: int):
    if not TELEGRAM_MESSAGE_LOG_PATH:
        return
    try:
        log_data = []
        if TELEGRAM_MESSAGE_LOG_PATH.exists():
            with open(TELEGRAM_MESSAGE_LOG_PATH, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
        log_data.append({'message_id': message_id, 'timestamp': datetime.now().isoformat()})
        with open(TELEGRAM_MESSAGE_LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=4, ensure_ascii=False)
    except (IOError, json.JSONDecodeError) as e:
        logging.error(f'Lỗi khi ghi log tin nhắn Telegram: {e}')

def send_telegram_message(message: str, parse_mode: str='HTML'):
    """Unique communication gateway function to send notifications to Telegram.

Main features:
1. Security Gateway: Check if Telegram is enabled in the config.
2. Automatic translation: Automatically translate message content if enabled.
3. Handle long messages: Automatically split messages that exceed the 4096 character limit
   of Telegram intelligently (cut by line) to preserve formatting.
4. Durable and safe: Catch network connection errors to avoid crashing the entire program.
5. Log cleaning: Save message_id so it can be automatically deleted later."""
    if not TELEGRAM_ENABLED:
        return
    final_message = message
    if TRANSLATION_ENABLED and TRANSLATION_TARGET_LANG:
        logging.info(f"Đang dịch tin nhắn sang '{TRANSLATION_TARGET_LANG}'...")
        final_message = translate_text(message, TRANSLATION_TARGET_LANG)
    max_length = 4096
    messages_to_send = []
    if len(final_message) <= max_length:
        messages_to_send.append(final_message)
    else:
        logging.warning(f'Tin nhắn quá dài ({len(final_message)} ký tự), sẽ được chia nhỏ.')
        remaining_message = final_message
        while len(remaining_message) > max_length:
            cut_pos = remaining_message.rfind('\n', 0, max_length)
            if cut_pos == -1:
                cut_pos = max_length
            part = remaining_message[:cut_pos]
            messages_to_send.append(part)
            remaining_message = remaining_message[cut_pos:].lstrip()
        if remaining_message:
            messages_to_send.append(remaining_message)
    for i, msg_part in enumerate(messages_to_send):
        if not msg_part.strip():
            continue
        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_part, 'parse_mode': parse_mode, 'disable_web_page_preview': True}
        try:
            if i > 0:
                time.sleep(0.5)
            response = requests.post(url, json=payload, timeout=20)
            response.raise_for_status()
            if TELEGRAM_MESSAGE_CLEANUP_ENABLED:
                response_data = response.json()
                if response_data.get('ok'):
                    message_id = response_data['result']['message_id']
                    log_sent_telegram_message(message_id)
        except requests.exceptions.RequestException as e:
            logging.error(f'Lỗi khi gửi thông báo Telegram (Phần {i + 1}/{len(messages_to_send)}): {e}')

def format_manual_trade_takeover_message(pair: str, plan: Dict[str, Any]) -> str:
    """Format a detailed Telegram message when a bot takes over a manual command."""
    import html
    pair_safe = html.escape(pair)
    message = f'✅ <b>Bot Đã Tiếp Quản Lệnh Thủ Công: <u>{pair_safe}</u></b> ✅\n\n'
    message += '<b><u>🔬 Phân Tích & Đánh Giá Tức Thời:</u></b>\n'
    strategy_type = html.escape(plan.get('strategy_type', 'Không xác định'))
    message += f'▪️ <b>Phân loại Chiến lược:</b> <i>{strategy_type}</i>\n'
    stance = plan.get('tactical_stance', 'TIÊU CHUẨN')
    stance_emojis = {'TẤN CÔNG': '⚔️', 'PHÒNG THỦ': '🛡️', 'TIÊU CHUẨN': '⚖️'}
    stance_emoji = stance_emojis.get(stance, '⚙️')
    message += f'▪️ <b>Tư thế Quản lý:</b> {stance} {stance_emoji}\n'
    prob_check = plan.get('probability_check')
    if prob_check and 'probability_percent' in prob_check:
        prob_percent = prob_check.get('probability_percent', 0)
        prob_verdict = prob_check.get('verdict', 'N/A')
        prob_emoji = '🎯' if prob_verdict == 'CAO' else '👍' if prob_verdict == 'KHÁ CAO' else '📊'
        message += f'▪️ <b>Xác suất Thắng (Ước tính):</b> {prob_emoji} <b>{prob_percent:.1f}%</b> ({prob_verdict})\n'
    score = plan.get('score')
    if score:
        message += f'▪️ <b>Điểm Chất lượng:</b> {score:.0f}\n'
    message += '\n<b><u>⚙️ Kế Hoạch Tác Chiến Đã Áp Dụng:</u></b>\n'
    entry = plan.get('entry', 0)
    sl = plan.get('sl', 0)
    tp1 = plan.get('tp1', 0)
    if entry > 0 and sl > 0 and (tp1 > 0):
        if entry > 100:
            decimals = 2
        elif entry > 10:
            decimals = 3
        elif entry > 0.1:
            decimals = 4
        else:
            decimals = 6
        risk = entry - sl
        if risk > 0:
            rr1 = (tp1 - entry) / risk
            message += f'▪️ <b>Entry:</b> <code>{entry:.{decimals}f}</code> (Giá của bạn)\n'
            message += f'▪️ <b>Stoploss:</b> <code>{sl:.{decimals}f}</code>\n'
            message += f'▪️ <b>TP1:</b> <code>{tp1:.{decimals}f}</code> (R:R ≈ 1:{rr1:.1f})\n'
            tp2 = plan.get('tp2')
            if tp2 and tp2 > tp1:
                rr2 = (tp2 - entry) / risk
                message += f'▪️ <b>TP2:</b> <code>{tp2:.{decimals}f}</code> (R:R ≈ 1:{rr2:.1f})\n'
    else:
        message += '<i>Lỗi: Không thể hiển thị kế hoạch chi tiết.</i>\n'
    message += '\n<i>Bot sẽ tự động quản lý lệnh này theo kế hoạch trên.</i>'
    return message

def load_potential_watchlist():
    if not POTENTIAL_WATCHLIST_PATH.exists():
        return {}
    try:
        with open(POTENTIAL_WATCHLIST_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_potential_watchlist(watchlist: Dict[str, Dict]):
    try:
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(POTENTIAL_WATCHLIST_PATH, 'w', encoding='utf-8') as f:
            json.dump(watchlist, f, indent=4, ensure_ascii=False)
        logging.info(f"Đã làm mới 'Bộ Nhớ Tác chiến', hiện có {len(watchlist)} mục tiêu đang được theo dõi.")
    except IOError as e:
        logging.error(f"Lỗi khi lưu file 'Bộ Nhớ': {e}")

def update_market_history(new_entry: Dict[str, Any]):
    """Read market log file, add latest entry at the beginning, limit quantity
and securely record the JSON file."""
    if not MARKET_HISTORY_PATH:
        logging.warning('MARKET_HISTORY_PATH chưa được cấu hình. Bỏ qua việc ghi nhật ký.')
        return
    history = []
    if MARKET_HISTORY_PATH.exists():
        try:
            with open(MARKET_HISTORY_PATH, 'r', encoding='utf-8') as f:
                history = json.load(f)
            if not isinstance(history, list):
                logging.warning(f'File {MARKET_HISTORY_FILENAME} có định dạng không đúng (không phải list). Sẽ tạo lại file mới.')
                history = []
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f'Lỗi khi đọc file nhật ký thị trường ({MARKET_HISTORY_PATH}): {e}. Sẽ tạo lại file mới.')
            history = []
    history.insert(0, new_entry)
    trimmed_history = history[:MARKET_HISTORY_MAX_ENTRIES]
    try:
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(MARKET_HISTORY_PATH, 'w', encoding='utf-8') as f:
            json.dump(trimmed_history, f, indent=4, ensure_ascii=False)
        logging.info(f'Đã cập nhật Nhật ký Thị trường, hiện có {len(trimmed_history)}/{MARKET_HISTORY_MAX_ENTRIES} mục.')
    except IOError as e:
        logging.error(f'Lỗi nghiêm trọng khi ghi file Nhật ký Thị trường: {e}')

def format_btc_analysis_telegram(btc_context: Dict[str, Any]) -> str:
    """BTC Report Format v8.1 - Displays strategy alerts from the Expert Panel."""
    if not btc_context:
        return '⚠️ Không có dữ liệu phân tích BTC.'
    timestamp = datetime.now().strftime('%H:%M:%S')
    message = f'🔬 <b>Báo Cáo Phân Tích & Kịch Bản BTC (v8.1)</b> 🔬\n<i>(Lúc {timestamp})</i>\n\n'
    model_analysis = btc_context.get('probability_model', {})
    extremes_analysis = btc_context.get('extremes_analysis', {})
    current_price = btc_context.get('current_price', 0)
    extremes_verdict = extremes_analysis.get('verdict')
    if extremes_verdict and extremes_verdict != 'NEUTRAL':
        emoji = '🚨' if extremes_verdict == 'POTENTIAL_TOP' else '🎯'
        message += f'<b><u>{emoji} CẢNH BÁO CHIẾN LƯỢC TỪ HỘI ĐỒNG {emoji}</u></b>\n'
        message += f'▪️ <b>Kết luận: {html.escape(extremes_verdict)}</b>\n'
        evidence = extremes_analysis.get('evidence', [])
        if evidence:
            message += f'▪️ <b>Bằng chứng:</b> <i>{html.escape(', '.join(evidence))}</i>\n'
        message += '\n'
    message += '<b><u>🎯 Kết Luận & Kịch Bản từ Mô Hình Xác Suất:</u></b>\n'
    narrative_from_model = model_analysis.get('narrative', 'Không có phân tích từ mô hình.')
    message += f'<i>{html.escape(narrative_from_model)}</i>\n\n'
    contributing_factors = model_analysis.get('contributing_factors', [])
    if contributing_factors:
        message += '<b>Các yếu tố ảnh hưởng chính (Mô hình):</b>\n'
        for factor in contributing_factors:
            message += f'▪️ {html.escape(factor)}\n'
        message += '\n'
    message += '<b><u>🗺️ Bản Đồ & Vùng Tranh Chấp:</u></b>\n'
    dynamic_range = model_analysis.get('dynamic_range', {})
    support = dynamic_range.get('low', 0)
    resistance = dynamic_range.get('high', 0)
    if current_price > 0:
        message += f'▪️ <b>Giá hiện tại: <code>${current_price:,.0f}</code></b>\n'
        if support > 0 and resistance > 0:
            message += f'▪️ <b>Vùng dao động dự kiến (ATR 1H):</b> HT <code>${support:,.0f}</code> - KC <code>${resistance:,.0f}</code>\n\n'
        else:
            message += '▪️ <i>Không thể xác định vùng dao động.</i>\n\n'
    else:
        message += '<i>Không thể lấy dữ liệu giá và S/R để xây dựng bản đồ.</i>\n\n'
    message += '<b><u>📊 Bằng Chứng Phân Tích (Đa khung):</u></b>\n'
    analysis_4h = html.escape(btc_context.get('analysis_4h', 'N/A'))
    analysis_1h = html.escape(btc_context.get('analysis_1h', 'N/A'))
    analysis_15m = html.escape(btc_context.get('analysis_15m', 'N/A'))
    message += f'▪️ <b>Vĩ mô (4h):</b> {analysis_4h}\n'
    message += f'▪️ <b>Ngắn hạn (1h):</b> {analysis_1h}\n'
    message += f'▪️ <b>Chiến thuật (15m):</b> {analysis_15m}\n'
    return message

def analyze_market_state(*args, **kwargs):
    """Integrated intelligence analysis v8.9 - Live Overbought Filter.

UPDATE (According to user request):
- Added a new emergency OVERRIDE filter.
- If there is no clear bottoming signal AND RSI 1H exceeds the overbought threshold
  (default is 72), the system will immediately declare `DEFCON 3: CAUTION`
  to prevent the risk of sudden adjustments."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been\nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def get_bot_instructions(*args, **kwargs):
    """v2.0 - Create detailed explanations that accurately reflect the bot's status."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been\nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def format_telegram_summary(open_trade_analysis: Dict[str, Optional[Dict[str, Any]]], recommendations: List[Dict[str, Any]], cycle_summary: Dict[str, Any]) -> str:
    timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    message = f'📡 <b>Điện Tín Tác Chiến & Cố Vấn v5.8</b> 📡\n<i>{timestamp}</i>\n\n'
    market_state = cycle_summary.get('market_state', {})
    level = market_state.get('level', 'UNKNOWN')
    narrative = html.escape(market_state.get('narrative', 'Không có phân tích diễn biến.'))
    emoji = '⚙️'
    if 'DEFCON 1' in level or 'DEFCON 2' in level:
        emoji = '🚨'
    elif 'DEFCON 3' in level:
        emoji = '⚠️'
    elif 'DEFCON 4' in level:
        emoji = '🔄'
    elif 'DEFCON 5' in level:
        emoji = '✅'
    message += f'<b><u>{emoji} Báo Cáo Tình Báo & Trạng Thái Báo Động</u></b>\n'
    message += f'▪️ <b>Cấp độ: {level}</b>\n'
    message += f'▪️ <b>Diễn biến:</b> <i>{narrative}</i>\n\n'
    message += '<b><u>📊 Đánh giá Lệnh Đang Mở (15m):</u></b>\n'
    if not open_trade_analysis:
        message += '<i>- Không có lệnh nào đang mở để đánh giá.</i>\n\n'
    else:
        for pair, analysis in open_trade_analysis.items():
            pair_safe = html.escape(pair)
            reason_safe = html.escape(analysis.get('reason', '')) if analysis else 'Không có lý do.'
            status = analysis.get('status') if analysis else 'Unknown'
            if status == 'Good':
                message += f'✅ <code>{pair_safe:<12}</code> <b>TỐT</b>. {reason_safe}\n'
            elif status == 'Weak':
                message += f'⚠️ <code>{pair_safe:<12}</code> <b>SUY YẾU</b>. {reason_safe} <b>Cân nhắc dời SL.</b>\n'
            else:
                message += f'❓ <code>{pair_safe:<12}</code> <b>Không thể đánh giá</b>. Kiểm tra thủ công.\n'
        message += '\n'
    all_recommendations_map = {rec['pair']: rec for rec in recommendations}
    selected_targets = [all_recommendations_map[pair] for pair in cycle_summary.get('new_targets_in_whitelist', []) if pair in all_recommendations_map]
    sorted_selected_targets = sorted(selected_targets, key=lambda x: x.get('final_score', 0), reverse=True)
    message += f'<b><u>🎯 Kế Hoạch & Chỉ Thị Tác Chiến cho Bot ({len(sorted_selected_targets)} mục tiêu)</u></b>\n'
    message += '<i>Bot Freqtrade sẽ tự động theo dõi và chỉ hành động khi các điều kiện cụ thể được đáp ứng.</i>\n\n'
    if not sorted_selected_targets:
        message += '<i>- Không có mục tiêu mới nào được chọn vào whitelist đợt này.</i>\n\n'
    else:
        for i, rec in enumerate(sorted_selected_targets):
            pair = html.escape(rec['pair'])
            score = rec.get('final_score', 0)
            is_a_grade = rec.get('is_A_grade', False)
            grade_emoji = '🏅' if is_a_grade else '🔹'
            message += f'<b>{i + 1}. {grade_emoji} <u>{pair}</u></b> | Điểm: <b>{score:.0f}</b>\n'
            strategy_name = html.escape(rec.get('strategy_type', 'N/A'))
            message += f'   - <b>Chiến lược:</b> <i>{strategy_name}</i>\n'
            reason_safe = html.escape(rec.get('reason', 'Không có lý do.'))
            message += f'   - <i>Lý do: {reason_safe}</i>\n'
            prob_check = rec.get('probability_check')
            if prob_check:
                prob_percent = prob_check.get('probability_percent', 0)
                prob_verdict = prob_check.get('verdict', 'N/A')
                prob_emoji = '🎯' if prob_verdict == 'CAO' else '👍' if prob_verdict == 'KHÁ CAO' else '📊'
                message += f'   - <b>Xác suất Thắng:</b> {prob_emoji} <b>{prob_percent:.1f}%</b> (Mức độ: <b>{prob_verdict}</b>)\n'
            if all((k in rec for k in ['entry', 'sl', 'tp1', 'current_price'])):
                entry, sl, tp1, current_price = (rec['entry'], rec['sl'], rec['tp1'], rec['current_price'])
                if entry > 10:
                    decimals = 3
                elif entry > 0.1:
                    decimals = 4
                else:
                    decimals = 6
                entry_status_msg = ''
                if current_price and entry > 0:
                    deviation = (current_price - entry) / entry * 100
                    if deviation > 2.0:
                        entry_status_msg = f'✅ Đã qua điểm vào ({deviation:+.1f}%)'
                    elif deviation > -2.0:
                        entry_status_msg = f'⏳ <b>SẮP TỚI ĐIỂM VÀO</b> ({deviation:+.1f}%)'
                    else:
                        entry_status_msg = f'... Chờ đợi (cách {deviation:.1f}%)'
                message += f'   - <b>Giá hiện tại:</b> <code>{current_price:.{decimals}f}</code> | <i>{entry_status_msg}</i>\n'
                risk = entry - sl
                rr1_text = ''
                if risk > 0:
                    rr1 = (tp1 - entry) / risk
                    rr1_text = f' (R:R ~1:{rr1:.1f})'
                message += f'   - <b>Kế Hoạch:</b> Mua <code>{entry:.{decimals}f}</code> | SL <code>{sl:.{decimals}f}</code> | TP1 <code>{tp1:.{decimals}f}</code>{rr1_text}\n'
            else:
                message += '   - <i>(Không có kế hoạch giao dịch chi tiết được đề xuất.)</i>\n'
            message += get_bot_instructions(rec)
            message += '\n'
    a_grade_targets = cycle_summary.get('a_grade_targets', [])
    b_grade_targets = cycle_summary.get('b_grade_targets', [])
    message += '<b><u>🔬 Tổng Kết Hoạt Động Của Cố Vấn:</u></b>\n'
    message += f'- Radar đã quét <b>{cycle_summary.get('total_pairs_in_universe', 'N/A')}</b> cặp, phát hiện <b>{len(a_grade_targets)} Hạng A</b> & <b>{len(b_grade_targets)} Hạng B</b>.\n'
    if cycle_summary.get('fallback_activated'):
        message += '- ⚠️ <b>CẢNH BÁO:</b> Whitelist trống, đã kích hoạt chế độ phòng thủ tuyệt đối với cặp an toàn.\n'
    message += '✅ <i>Kế Hoạch Tác Chiến, Chỉ thị và Whitelist mới đã được gửi tới Bot.</i>'
    return message

def ft_login() -> bool:
    global api_session
    api_session = requests.Session()
    try:
        api_session.auth = (FT_USER, FT_PASS)
        response = api_session.get(f'{FREQTRADE_URL}/api/v1/balance', timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f'ĐĂNG NHẬP THẤT BẠI. Lỗi: {e}.')
        return False

def check_open_trades() -> Optional[List[Dict[str, Any]]]:
    try:
        response = api_session.get(f'{FREQTRADE_URL}/api/v1/status', timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f'Lỗi khi kiểm tra lệnh mở: {e}.')
        return None

def update_files_and_reload(new_whitelist: List[str], final_trade_plans_data: Dict[str, Any], force_reload: bool=True):
    """Update configuration files and reload Freqtrade.
v7.1: Fix NameError due to still referencing the deleted MANUAL_TRADE_WHITELIST_PAIRS."""
    try:
        UNIVERSAL_STRATEGY_NAME = 'ExternalSignalStrategy'
        with open(TRADE_PLAN_PATH, 'w', encoding='utf-8') as f:
            json.dump(final_trade_plans_data, f, indent=4, ensure_ascii=False)
        logging.info(f'Đã cập nhật Kế Hoạch Tác Chiến và Trạng Thái Thị Trường ({TRADE_PLAN_FILENAME}).')
        final_whitelist_set = set(new_whitelist)
        new_overrides = {pair: UNIVERSAL_STRATEGY_NAME for pair in final_whitelist_set}
        with open(STRATEGY_OVERRIDES_PATH, 'w', encoding='utf-8') as f:
            json.dump(new_overrides, f, indent=4, ensure_ascii=False)
        logging.info(f"Đã cập nhật Sổ Lệnh để trỏ {len(new_overrides)} mục tới '{UNIVERSAL_STRATEGY_NAME}'.")
        config_updated, _ = update_config_file(list(final_whitelist_set))
        if config_updated or force_reload:
            logging.info(f'Cấu hình đã thay đổi. Chờ 5s trước khi gửi lệnh reload...')
            time.sleep(5)
            if reload_freqtrade_config():
                logging.info('Lệnh reload đã được gửi. Chờ 20 giây để Freqtrade khởi động lại hoàn toàn...')
                time.sleep(20)
            else:
                logging.error('Gửi lệnh reload THẤT BẠI.')
        else:
            logging.info('Whitelist không thay đổi. Không cần reload.')
    except Exception as e:
        logging.error(f'Lỗi nghiêm trọng khi cập nhật file và reload: {e}', exc_info=True)

def update_config_file(new_whitelist: list) -> Tuple[bool, int]:
    try:
        sorted_new_whitelist = sorted(new_whitelist)
        with open(CONFIG_PATH, 'r+', encoding='utf-8') as f:
            config_data = json.load(f)
            current_whitelist = sorted(config_data.get('exchange', {}).get('pair_whitelist', []))
            if current_whitelist == sorted_new_whitelist:
                return (False, len(current_whitelist))
            config_data['exchange']['pair_whitelist'] = sorted_new_whitelist
            f.seek(0)
            json.dump(config_data, f, indent=4, ensure_ascii=False)
            f.truncate()
            logging.info(f"Đã cập nhật thành công whitelist trong '{CONFIG_PATH}'.")
            return (True, len(current_whitelist))
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logging.error(f"Lỗi khi cập nhật file '{CONFIG_PATH}': {e}")
        return (False, 0)

def reload_freqtrade_config() -> bool:
    try:
        response = api_session.post(f'{FREQTRADE_URL}/api/v1/reload_config', timeout=15)
        response.raise_for_status()
        logging.info(f"Yêu cầu 'Tải Lại Lệnh' thành công. Trạng thái: '{response.json().get('status', 'unknown')}'")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Lỗi khi yêu cầu 'Tải Lại Lệnh': {e}")
        return False

def proactive_trade_manager_job():
    """Bot status monitoring function (simplified version).

The main function is to run every minute to check what status the Freqtrade bot is in
RUNNING or STOPPED. If it is detected that the bot has just been /started (switched from STOPPED
to RUNNING), which immediately triggers a full scan cycle (`main_job`).

NOTE: This version has removed the manual command takeover logic and plan cleanup
to focus only on status monitoring."""
    global BOT_OPERATIONAL_STATE, IS_MAIN_JOB_RUNNING
    try:
        current_ft_state = check_freqtrade_state()
        if current_ft_state != BOT_OPERATIONAL_STATE:
            logging.info(f"PHÁT HIỆN THAY ĐỔI TRẠNG THÁI: Freqtrade chuyển từ '{BOT_OPERATIONAL_STATE}' sang '{current_ft_state}'.")
            send_telegram_message(f'ℹ️ <b>Trạng Thái Bot Thay Đổi</b> ℹ️\nCố vấn đã ghi nhận Freqtrade chuyển từ trạng thái <b>{BOT_OPERATIONAL_STATE}</b> sang <b>{current_ft_state}</b>.')
            BOT_OPERATIONAL_STATE = current_ft_state
            if BOT_OPERATIONAL_STATE == 'RUNNING' and (not IS_MAIN_JOB_RUNNING):
                logging.info('Lệnh /start được ghi nhận. Kích hoạt chu kỳ Cố vấn Tác chiến ngay lập tức...')
                send_telegram_message('🚀 <b>Lệnh /start được ghi nhận!</b>\nBắt đầu chu kỳ Cố vấn Tác chiến ngay lập tức...')
                main_job()
                return
    except Exception as e:
        logging.error(f'Lỗi khi kiểm tra trạng thái Freqtrade trong giám sát 1 phút: {e}', exc_info=True)

def monitor_open_trades_job():
    """Runs periodically every 15 minutes to monitor the "health" of open orders.
This function performs the following steps:
1. Get the list of open orders from Freqtrade.
2. Download current battle plan (SL/TP, posture).
3. Call the analyzer to evaluate the status of each command on the 15m frame.
4. Synthesize data from API (profit/loss, current price), plans, and analysis results.
5. Send a detailed summary report to Telegram."""
    try:
        logging.info('--- [Giám sát 15m] Bắt đầu chu kỳ giám sát lệnh đang mở ---')
        open_trades_details = check_open_trades()
        if not open_trades_details:
            logging.info('--- [Giám sát 15m] Không có lệnh mở. Bỏ qua. ---')
            return
        full_plan_data = load_trade_plan()
        existing_trade_plans = full_plan_data.get('pairs', {})
        open_trade_pairs = [trade['pair'] for trade in open_trades_details]
        health_analysis = scanner.analyze_open_trades(open_trade_pairs)
        combined_analysis = {}
        for trade in open_trades_details:
            pair = trade['pair']
            combined_data = health_analysis.get(pair, {'status': 'Unknown', 'reason': 'Không thể lấy phân tích sức khỏe.'})
            combined_data['open_rate'] = trade.get('open_rate')
            combined_data['profit_pct'] = trade.get('profit_pct')
            combined_data['current_rate'] = trade.get('current_rate')
            plan = existing_trade_plans.get(pair, {})
            combined_data['sl'] = plan.get('sl')
            combined_data['tp1'] = plan.get('tp1')
            combined_data['tp2'] = plan.get('tp2')
            combined_data['tactical_stance'] = plan.get('tactical_stance', 'TIÊU CHUẨN')
            combined_analysis[pair] = combined_data
        if combined_analysis:
            send_telegram_message(scanner.format_15m_trade_status_telegram(combined_analysis))
        logging.info('--- [Giám sát 15m] Hoàn thành. ---')
    except Exception as e:
        logging.error(f'LỖI trong chu kỳ giám sát 15 phút: {e}', exc_info=True)
        send_telegram_message(f'🚨 <b>LỖI Giám Sát 15m:</b>\n<pre>{html.escape(str(e))}</pre>')

def manage_open_trade_plan(*args, **kwargs):
    """SL/TP management function for open orders v3.2 - Calculation Specialist.
- Get the decided 'Tactical Pose' from main_job.
- Just focus on adjusting SL and recalculating TP based on that posture.
- Retains emergency R:R override logic according to DEFCON for maximum safety."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been\nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def main_job():
    """Main function of Operational Advisor v7.1 - Fair Selection Logic.
- UPDATE (v7.1):
  - Completely removed the priority logic for the 'Reversal-Scout' strategy.
  - Whitelist is now chosen fairly: take N targets with points
    The highest 'final_score' after passing the DEFCON risk filter, regardless
    Which strategy is it?"""
    global IS_MAIN_JOB_RUNNING, BOT_OPERATIONAL_STATE
    if IS_MAIN_JOB_RUNNING:
        logging.warning('Một chu kỳ main_job khác đang chạy. Bỏ qua lần kích hoạt này.')
        return
    IS_MAIN_JOB_RUNNING = True
    try:
        print('\n')
        logging.info(f'{'=' * 60}\nBắt đầu chu kỳ Cố Vấn Tác Chiến v7.1 (Hàng giờ) lúc {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}')
        BOT_OPERATIONAL_STATE = check_freqtrade_state()
        if BOT_OPERATIONAL_STATE == 'STOPPED':
            logging.warning('!!! CHẾ ĐỘ CỐ VẤN: Freqtrade đang ở trạng thái STOPPED. Báo cáo sẽ chỉ mang tính tham khảo. !!!')
            send_telegram_message('⚠️ <b>Bot đang ở chế độ /stop (Cố vấn).</b>\nBắt đầu quét thị trường để gửi báo cáo tham khảo...')
        else:
            send_telegram_message('🚀 <b>Bắt đầu chu kỳ Cố Vấn Tác Chiến (HÀNG GIỜ)...</b>')
        if not ft_login():
            logging.error('Đăng nhập Freqtrade thất bại. Hủy bỏ chu kỳ.')
            send_telegram_message('🚨 <b>LỖI NGHIÊM TRỌNG:</b> Không thể đăng nhập vào Freqtrade API. Chu kỳ bị hủy.')
            return
        cycle_summary = {}
        final_trade_plans = {}
        logging.info('\n--- BƯỚC 1: Quét Toàn diện & Tải trạng thái Chiến trường ---')
        open_trades_details = check_open_trades() or []
        open_trades_map = {trade['pair']: trade for trade in open_trades_details}
        existing_trade_plans = load_trade_plan().get('pairs', {})
        logging.info(' -> Bắt đầu quét toàn diện thị trường (có thể mất vài phút)...')
        scan_data = scanner.run_scan()
        all_results_map = {res['pair']: res for res in scan_data.get('recommendations', [])}
        logging.info('\n--- BƯỚC 2: Phân tích Tình báo & Xác định Cấp độ Báo động ---')
        summary_data = scan_data.get('summary', {})
        market_state = analyze_market_state(summary_data)
        defcon_level = market_state.get('level', 'DEFCON 4: NORMAL')
        cycle_summary['market_state'] = market_state
        cycle_summary.update(summary_data)
        btc_context = summary_data.get('market_context', {}).get('btc_context', {})
        send_telegram_message(format_btc_analysis_telegram(btc_context))
        time.sleep(1)
        logging.info(f'\n--- BƯỚC 3: Xây dựng Kế Hoạch Tác Chiến theo {defcon_level} ---')
        logging.info(f' -> Tái đánh giá và quản lý {len(open_trades_map)} lệnh đang mở...')
        open_trade_pairs = list(open_trades_map.keys())
        for pair in open_trade_pairs:
            if pair in existing_trade_plans:
                new_scan_result = all_results_map.get(pair)
                trade_details = open_trades_map[pair]
                base_stance = new_scan_result.get('tactical_stance') if new_scan_result else existing_trade_plans[pair].get('tactical_stance', 'TIÊU CHUẨN')
                final_stance = base_stance
                if 'DEFCON 1' in defcon_level or 'DEFCON 2' in defcon_level:
                    final_stance = 'PHÒNG THỦ'
                elif 'DEFCON 3' in defcon_level:
                    final_stance = 'PHÒNG THỦ'
                if final_stance != base_stance:
                    logging.info(f"    - [{pair}] TƯ THẾ BẮT BUỘC: từ '{base_stance}' -> '{final_stance}' do {defcon_level}")
                else:
                    logging.info(f"    - [{pair}] TƯ THẾ GIỮ NGUYÊN: '{final_stance}'")
                managed_plan = manage_open_trade_plan(pair, existing_trade_plans[pair], new_scan_result, trade_details, market_state, final_stance)
                final_trade_plans[pair] = managed_plan
        logging.info(' -> Áp dụng Bộ lọc Chiến lược Thích ứng để tìm mục tiêu mới...')
        potential_targets = [rec for rec in sorted(all_results_map.values(), key=lambda x: x.get('final_score', 0), reverse=True) if rec['pair'] not in open_trade_pairs]
        limit_new_targets = NORMAL_WHITELIST_SIZE
        min_score_threshold = 90
        allowed_strategy = None
        disallowed_strategies = []
        if 'DEFCON 1' in defcon_level or 'DEFCON 2' in defcon_level or 'DEFCON 3' in defcon_level:
            limit_new_targets = 5
            min_score_threshold = 110 if 'DEFCON 1' in defcon_level else 100
            allowed_strategy = 'Reversal-Scout'
            logging.info(f"   -> {defcon_level}: KÍCH HOẠT CHẾ ĐỘ 'SĂN ĐÁY'. Chỉ cho phép 'Reversal-Scout', điểm > {min_score_threshold}, giới hạn {limit_new_targets} cặp.")
        elif 'DEFCON 4' in defcon_level:
            disallowed_strategies = ['Breakout-Pre']
            logging.info(f"   -> {defcon_level}: Loại bỏ chiến lược 'Breakout-Pre', điểm > {min_score_threshold}.")
        else:
            logging.info(f'   -> {defcon_level}: Cho phép tất cả các chiến lược, điểm > {min_score_threshold}.')
        logging.info(f'--- [BỘ LỌC CHI TIẾT] Đánh giá {len(potential_targets)} mục tiêu tiềm năng ---')
        filtered_targets = []
        for rec in potential_targets:
            pair, score, strategy = (rec.get('pair', 'UNKNOWN'), rec.get('final_score', 0), rec.get('strategy_type', 'N/A'))
            if score < min_score_threshold:
                logging.info(f'    -> [LOẠI] {pair:<15} | Lý do: Điểm số quá thấp ({score:.0f} < {min_score_threshold})')
                continue
            if allowed_strategy and allowed_strategy not in strategy:
                logging.info(f"    -> [LOẠI] {pair:<15} | Lý do: Chiến lược '{strategy}' không được phép (chỉ cho phép '{allowed_strategy}')")
                continue
            if strategy in disallowed_strategies:
                logging.info(f"    -> [LOẠI] {pair:<15} | Lý do: Chiến lược '{strategy}' bị cấm trong cấp độ {defcon_level}")
                continue
            logging.info(f'    -> [OK] {pair:<15} | Điểm: {score:.0f} | Chiến lược: {strategy}')
            filtered_targets.append(rec)
        logging.info(f'--- [BỘ LỌC CHI TIẾT] Hoàn tất. Tìm thấy {len(filtered_targets)} mục tiêu hợp lệ. ---')
        logging.info(' -> Tuyển chọn các mục tiêu điểm cao nhất một cách công bằng (không ưu tiên chiến lược).')
        selected_targets = filtered_targets[:limit_new_targets]
        new_targets_for_whitelist = [rec['pair'] for rec in selected_targets]
        logging.info(f' -> Đã chọn {len(new_targets_for_whitelist)} mục tiêu hàng đầu sau đây vào whitelist:')
        for target in selected_targets:
            logging.info(f'    - [{target['pair']}] Điểm: {target.get('final_score', 0):.0f}, Chiến lược: {target.get('strategy_type', 'N/A')}')
        logging.info(f' -> Bổ sung Kế Hoạch cho {len(new_targets_for_whitelist)} mục tiêu mới...')
        for pair in new_targets_for_whitelist:
            rec = all_results_map.get(pair)
            if rec and all((k in rec for k in ['entry', 'sl', 'tp1', 'tp2'])):
                recommended_stance = rec.get('tactical_stance', 'TIÊU CHUẨN')
                final_stance_for_new_target = recommended_stance
                if any((s in defcon_level for s in ['DEFCON 1', 'DEFCON 2', 'DEFCON 3'])):
                    final_stance_for_new_target = 'PHÒNG THỦ'
                final_trade_plans[pair] = {'entry': rec['entry'], 'sl': rec['sl'], 'tp1': rec['tp1'], 'tp2': rec['tp2'], 'strategy_type': rec.get('strategy_type'), 'score': rec.get('final_score'), 'tactical_stance': final_stance_for_new_target}
        logging.info('\n--- BƯỚC 4: Hoàn thiện Whitelist & Xử lý dữ liệu báo cáo ---')
        top_cmc_pairs = summary_data.get('top_15_by_volume', [])
        if top_cmc_pairs:
            logging.info(f' -> Bổ sung danh sách Top CoinMarketCap vào whitelist: {top_cmc_pairs}')
        planned_pairs = list(final_trade_plans.keys())
        final_whitelist = sorted(list(set(planned_pairs).union(set(top_cmc_pairs))))
        if not final_whitelist:
            logging.warning(f'!!! WHITELIST TRỐNG. Kích hoạt chế độ phòng thủ dự phòng với cặp {EMERGENCY_FALLBACK_PAIR}.')
            final_whitelist = [EMERGENCY_FALLBACK_PAIR]
            cycle_summary['fallback_activated'] = True
        new_potential_watchlist = {r['pair']: {'last_score': r.get('final_score', 0), 'timestamp': datetime.now().isoformat()} for r in all_results_map.values() if r.get('final_score', 0) > POTENTIAL_WATCHLIST_MIN_SCORE}
        save_potential_watchlist(dict(sorted(new_potential_watchlist.items(), key=lambda item: item[1]['last_score'], reverse=True)[:MAX_POTENTIAL_WATCHLIST_SIZE]))
        open_trade_analysis_15m = scanner.analyze_open_trades(open_trade_pairs)
        cycle_summary.update({'a_grade_targets': [r['pair'] for r in all_results_map.values() if r.get('is_A_grade')], 'b_grade_targets': [r['pair'] for r in all_results_map.values() if not r.get('is_A_grade')], 'final_whitelist': final_whitelist, 'new_targets_in_whitelist': new_targets_for_whitelist})
        logging.info('\n--- BƯỚC 5: Gửi Báo cáo & Triển khai Kế Hoạch Tác Chiến tới Bot ---')
        send_telegram_message(format_telegram_summary(open_trade_analysis_15m, sorted(all_results_map.values(), key=lambda x: x.get('final_score', 0), reverse=True), cycle_summary))
        final_plans_data = {'market_state': market_state, 'pairs': final_trade_plans}
        if BOT_OPERATIONAL_STATE == 'RUNNING':
            logging.info('Bot đang ở trạng thái RUNNING. Triển khai kế hoạch tác chiến...')
            update_files_and_reload(final_whitelist, final_plans_data, force_reload=True)
            send_telegram_message('✅ <b>Chu kỳ Cố Vấn Tác Chiến (HÀNG GIỜ) hoàn tất và đã áp dụng.</b>')
        else:
            logging.warning('!!! Bot đang ở trạng thái STOPPED. Hoạt động ở chế độ Cố Vấn. Bỏ qua cập nhật whitelist và reload. !!!')
            with open(TRADE_PLAN_PATH, 'w', encoding='utf-8') as f:
                json.dump(final_plans_data, f, indent=4, ensure_ascii=False)
            logging.info(f'Đã lưu Kế Hoạch Tác Chiến tham khảo vào {TRADE_PLAN_FILENAME}.')
            send_telegram_message('⚠️ <b>Bot Đang Dừng (/stop)</b> ⚠️\nBáo cáo trên chỉ mang tính tham khảo và <b>KHÔNG</b> được áp dụng cho bot Freqtrade.')
        update_market_history(cycle_summary)
        logging.info(f'Hoàn thành chu kỳ Cố Vấn Tác Chiến. {'=' * 60}')
    except Exception as e:
        logging.critical(f'LỖI KHÔNG MONG MUỐN trong main_job: {e}', exc_info=True)
        send_telegram_message(f'🚨 <b>LỖI NGHIÊM TRỌNG (HÀNG GIỜ):</b>\n<pre>{html.escape(str(e))}</pre>')
    finally:
        IS_MAIN_JOB_RUNNING = False

def delete_old_telegram_messages():
    if not TELEGRAM_ENABLED or not TELEGRAM_MESSAGE_CLEANUP_ENABLED:
        return
    logging.info('--- [Dọn dẹp Telegram] Bắt đầu chu kỳ dọn dẹp tin nhắn cũ ---')
    if not TELEGRAM_MESSAGE_LOG_PATH.exists():
        return
    try:
        with open(TELEGRAM_MESSAGE_LOG_PATH, 'r') as f:
            log_data = json.load(f)
        if not log_data:
            return
        cutoff_date = datetime.now() - timedelta(days=TELEGRAM_MESSAGE_CLEANUP_DAYS)
        messages_to_keep, messages_deleted = ([], 0)
        for msg_info in log_data:
            try:
                if datetime.fromisoformat(msg_info['timestamp']) < cutoff_date:
                    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage'
                    payload = {'chat_id': TELEGRAM_CHAT_ID, 'message_id': msg_info['message_id']}
                    response = requests.post(url, json=payload, timeout=5)
                    if response.status_code == 200:
                        messages_deleted += 1
                else:
                    messages_to_keep.append(msg_info)
            except Exception:
                messages_to_keep.append(msg_info)
        with open(TELEGRAM_MESSAGE_LOG_PATH, 'w') as f:
            json.dump(messages_to_keep, f, indent=4)
        logging.info(f'--- [Dọn dẹp Telegram] Hoàn tất. Đã xóa {messages_deleted} tin nhắn. ---')
    except (IOError, json.JSONDecodeError) as e:
        logging.error(f'Lỗi khi xử lý file log Telegram: {e}')

def print_schedule_status(last_status_str=''):
    next_main = next((j.next_run for j in schedule.jobs if j.job_func.__name__ == 'main_job'), None)
    next_monitor = next((j.next_run for j in schedule.jobs if j.job_func.__name__ == 'monitor_open_trades_job'), None)
    main_str = next_main.strftime('%H:%M') if next_main else 'N/A'
    monitor_str = next_monitor.strftime('%H:%M') if next_monitor else 'N/A'
    current_status_str = f'Lượt tiếp: [Toàn diện] {main_str} | [Giám sát] {monitor_str}'
    if current_status_str != last_status_str:
        print(f'[{datetime.now().strftime('%H:%M:%S')}] {current_status_str}   ', end='\r')
    return current_status_str
if __name__ == '__main__':
    if not load_freqtrade_api_config():
        exit(1)
    _load_managed_trades()
    if not ft_login():
        logging.critical('Không thể đăng nhập vào Freqtrade khi khởi động. Thoát.')
        exit(1)
    initial_state = check_freqtrade_state()
    BOT_OPERATIONAL_STATE = initial_state
    main_scan_time = ':02'
    monitor_time = ':01'
    cleanup_time = '03:03'
    logging.info('-' * 60)
    logging.info(f'Khởi động Trợ Lý Tác Chiến Chủ Động v6.4.')
    logging.info(f'Trạng thái Freqtrade ban đầu: {BOT_OPERATIONAL_STATE}')
    logging.info('-' * 60)
    schedule.every().hour.at(main_scan_time).do(main_job)
    logging.info(f"Lập lịch [CỐ VẤN HÀNG GIỜ] vào phút '{main_scan_time[1:]}' của mỗi giờ.")
    schedule.every(15).minutes.at(monitor_time).do(monitor_open_trades_job)
    logging.info(f'Lập lịch [GIÁM SÁT LỆNH 15 PHÚT] để gửi báo cáo sức khỏe lệnh đang mở.')
    schedule.every(1).minutes.do(proactive_trade_manager_job)
    logging.info('Lập lịch [TRỢ LÝ CHỦ ĐỘNG 1 PHÚT] để tiếp quản lệnh thủ công và giám sát trạng thái /start /stop.')
    if TELEGRAM_MESSAGE_CLEANUP_ENABLED:
        schedule.every().day.at(cleanup_time).do(delete_old_telegram_messages)
        logging.info(f'Lập lịch [DỌN DẸP TELEGRAM] tự động vào {cleanup_time} hàng ngày.')
    logging.info('-' * 60)
    logging.info('Thực hiện lần chạy đầu tiên (CỐ VẤN HÀNG GIỜ) ngay bây giờ...')
    main_job()
    logging.info('Thực hiện lần chạy đầu tiên (TRỢ LÝ CHỦ ĐỘNG) ngay bây giờ...')
    proactive_trade_manager_job()
    logging.info('Bắt đầu vòng lặp chờ lịch trình...')
    last_status = ''

    def print_schedule_status(last_status_str=''):
        next_main = next((j.next_run for j in schedule.jobs if j.job_func.__name__ == 'main_job'), None)
        next_proactive = next((j.next_run for j in schedule.jobs if j.job_func.__name__ == 'proactive_trade_manager_job'), None)
        next_monitor = next((j.next_run for j in schedule.jobs if j.job_func.__name__ == 'monitor_open_trades_job'), None)
        main_str = next_main.strftime('%H:%M') if next_main else 'N/A'
        proactive_str = next_proactive.strftime('%H:%M:%S') if next_proactive else 'N/A'
        monitor_str = next_monitor.strftime('%H:%M') if next_monitor else 'N/A'
        current_status_str = f'Lượt tiếp: [Cố vấn] {main_str} | [Giám sát] {monitor_str} | [Trợ lý] {proactive_str} | Trạng thái: {BOT_OPERATIONAL_STATE}'
        if current_status_str != last_status_str:
            print(f'[{datetime.now().strftime('%H:%M:%S')}] {current_status_str}   ', end='\r')
        return current_status_str
    while True:
        try:
            schedule.run_pending()
            if datetime.now().second % 5 == 0:
                last_status = print_schedule_status(last_status)
            time.sleep(1)
        except KeyboardInterrupt:
            print('\nĐã nhận tín hiệu dừng. Kết thúc chương trình.')
            break
        except Exception as e:
            logging.critical(f'\nLỖI NGHIÊM TRỌNG TRONG VÒNG LẶP CHÍNH: {e}', exc_info=True)
            time.sleep(10)