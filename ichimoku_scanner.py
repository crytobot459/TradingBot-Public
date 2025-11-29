import ccxt
import pandas as pd
import numpy as np
import talib.abstract as ta
import warnings
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
import random
from collections import defaultdict
import logging
import asyncio
EXCHANGE = 'binance'
QUOTE_CURRENCY = 'USDT'
TIMEFRAMES = ['4h', '1h', '15m', '5m']
MIN_DAILY_VOLUME_USDT = 3000000
TOP_N_RESULTS = 10
BEST_PICKS_COUNT = 3
MAX_PRICE_EXTENSION_PERCENT_1H = 8.0
MIN_SAFETY_MARGIN_PERCENT = 0.75
MIN_MONTHLY_CANDLES_FOR_WHITELIST = 6
TOP_CMC_COINS = ['ETH', 'BNB', 'SOL', 'DOGE', 'MATIC', 'ADA', 'LINK', 'XRP', 'AVAX', 'XLM', 'SUI', 'BCH', 'HBAR', 'LTC', 'DOT']
STABLECOIN_LIST = ['USDC', 'USTC', 'PAXG', 'TUSD', 'FDUSD', 'DAI', 'BUSD', 'USDP', 'USUAL', 'XUSD', 'WBETH', 'EUR', 'EURI', 'USD1', 'WBTC', 'USDE', 'TRX', 'PEPE']
BTC_SYMBOL = 'BTC/USDT'
FILTER_THRESHOLDS = {'bullish': 10.0, 'neutral': 5.0, 'bearish': 3.0}
BTC_PUMP_FILTER_THRESHOLD_24H = 4.0
BTC_PUMP_RSI_THRESHOLD_4H = 75
MAX_ENTRY_DEVIATION_PERCENT = 2.5
MIN_SAFETY_MARGIN_PERCENT = 0.75
WARHORSE_BYPASS_ENABLED = True
WARHORSE_CANDIDATE_MIN_VOLUME_FACTOR = 3.0
WARHORSE_CANDIDATE_MIN_RANGE_POSITION = 0.85
WARHORSE_CANDIDATE_MAX_24H_CHANGE = 40.0
MAX_PRE_BREAKOUT_DEVIATION_PERCENT = 4.0
ETH_SYMBOL = 'ETH/USDT'
warnings.filterwarnings('ignore', category=RuntimeWarning)

def initialize_exchange(exchange_id: str) -> Optional[ccxt.Exchange]:
    """
    Khởi tạo và kết nối tới sàn giao dịch, bắt buộc chỉ sử dụng thị trường SPOT.
    v2.0: Luôn chỉ định 'defaultType': 'spot' để đảm bảo 100% không lấy nhầm
          dữ liệu từ thị trường Futures hay Vĩnh cửu (Perpetual).
    """
    try:
        exchange_options = {'options': {'defaultType': 'spot'}}
        exchange = getattr(ccxt, exchange_id)(exchange_options)
        exchange.load_markets()
        print(f'Khởi tạo sàn {exchange_id} ở chế độ SPOT thành công.')
        return exchange
    except Exception as e:
        print(f'LỖI NGHIÊM TRỌNG khi khởi tạo sàn {exchange_id} ở chế độ SPOT: {e}')
        return None

def _get_dynamic_tf_analysis(df: pd.DataFrame, lookback: int=5) -> Dict[str, Any]:
    """
    Hàm phân tích động lượng chuyên sâu v2.1 - Nhận diện Tín hiệu Kiệt sức.
    - Phân chia vùng RSI chi tiết hơn (mạnh, quá mua) để diễn giải chính xác hơn.
    - Có khả năng phát hiện khi "Đà mua đang yếu dần" ngay cả khi RSI vẫn còn
      trong vùng mạnh (ví dụ 60-70), giải quyết vấn đề người dùng báo cáo.
    """
    if df.empty or len(df) < lookback + 1:
        return {'state': 'Không đủ dữ liệu', 'rsi_val': 0, 'adx_val': 0, 'rsi_slope': 0, 'adx_slope': 0, 'momentum_verdict': 'Không xác định', 'full_analysis_string': 'Không đủ dữ liệu'}
    last_row = df.iloc[-1]
    close, ema50, ema200, rsi, adx = (last_row['close'], last_row['ema_50'], last_row['ema_200'], last_row['rsi'], last_row['adx'])
    ADX_TRENDING, RSI_BULLISH, RSI_BEARISH = (23, 55, 45)
    state = 'TRUNG LẬP'
    if close > ema50 > ema200 and adx > ADX_TRENDING and (rsi > RSI_BULLISH):
        state = 'TĂNG MẠNH'
    elif close < ema50 < ema200 and adx > ADX_TRENDING and (rsi < RSI_BEARISH):
        state = 'GIẢM MẠNH'
    elif ema50 < ema200 and close > ema50 and (rsi > RSI_BULLISH):
        state = 'PHỤC HỒI TỪ ĐÁY'
    elif close > ema50 > ema200:
        state = 'TÍCH LŨY TRÊN (Uptrend yếu)'
    elif ema50 > ema200 and close < ema50:
        state = 'ĐIỀU CHỈNH (trong Uptrend)'
    elif close < ema50 < ema200:
        state = 'XU HƯỚNG GIẢM'
    elif adx < 20:
        state = 'ĐI NGANG (Sideways)'
    rsi_series = df['rsi'].tail(lookback).values
    adx_series = df['adx'].tail(lookback).values
    x_axis = np.arange(len(rsi_series))
    rsi_slope = np.polyfit(x_axis, rsi_series, 1)[0]
    adx_slope = np.polyfit(x_axis, adx_series, 1)[0]
    rsi_verdict = ''
    if rsi < 35:
        if rsi_slope > 0.4:
            rsi_verdict = 'Áp lực bán giảm.'
        elif rsi_slope < -0.4:
            rsi_verdict = 'Áp lực bán tăng mạnh.'
        else:
            rsi_verdict = 'Đang tìm đáy.'
    elif rsi > 68:
        if rsi_slope < -0.4:
            rsi_verdict = 'Đà mua suy yếu (từ vùng quá mua).'
        elif rsi_slope > 0.4:
            rsi_verdict = 'Đà mua tăng rất mạnh (rủi ro cao).'
        else:
            rsi_verdict = 'Đang tìm đỉnh.'
    elif rsi > 58:
        if rsi_slope < -0.4:
            rsi_verdict = 'Đà mua đang yếu dần (dấu hiệu kiệt sức).'
        elif rsi_slope > 0.4:
            rsi_verdict = 'Đà mua duy trì tốt.'
        else:
            rsi_verdict = 'Động lượng chững lại ở vùng mạnh.'
    elif rsi_slope > 0.5:
        rsi_verdict = 'Đà mua đang tăng.'
    elif rsi_slope < -0.5:
        rsi_verdict = 'Đà bán đang tăng.'
    else:
        rsi_verdict = 'Động lượng chững lại.'
    adx_verdict = ''
    if adx > ADX_TRENDING:
        if adx_slope > 0.3:
            adx_verdict = 'Xu hướng hiện tại mạnh lên.'
        elif adx_slope < -0.3:
            adx_verdict = 'Xu hướng hiện tại yếu đi.'
        else:
            adx_verdict = 'Xu hướng duy trì.'
    elif adx_slope > 0.3:
        adx_verdict = 'Sắp có xu hướng mới.'
    else:
        adx_verdict = 'Tiếp tục đi ngang.'
    momentum_verdict = f'{rsi_verdict} {adx_verdict}'
    full_analysis_string = f'{state} (RSI: {rsi:.0f}, ADX: {adx:.0f}) | Động lượng: {momentum_verdict.strip()}'
    return {'state': state, 'rsi_val': rsi, 'adx_val': adx, 'rsi_slope': rsi_slope, 'adx_slope': adx_slope, 'momentum_verdict': momentum_verdict, 'full_analysis_string': full_analysis_string}

def _evaluate_market_factors(*args, **kwargs):
    """Hàm Trợ giúp v8.4 - Bộ Não Chấm Điểm & Sửa lỗi Logic "Mất Đà".

CẬP NHẬT:
- Tái cấu trúc logic xác định trạng thái. Việc kiểm tra ADX yếu (< 22) được
  thực hiện SAU KHI xác định cấu trúc EMA ban đầu, cho phép nó ghi đè
  và xác định chính xác trạng thái "Mất Đà" trong mọi bối cảnh (uptrend, downtrend,
  phục hồi), giải quyết triệt để lỗi người dùng báo cáo."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def analyze_market_context(*args, **kwargs):
    """HÀM PHÂN TÍCH BỐI CẢNH THỊ TRƯỜNG v8.5 - Bộ Cảm biến Bùng nổ ADX Đa Khung.

CẬP NHẬT (Theo yêu cầu người dùng):
- Mở rộng logic phát hiện bùng nổ ADX ra 3 khung thời gian chiến lược: 4h, 1h, 15m.
- Tính toán sự thay đổi ADX và trạng thái DMI cho từng khung.
- Đóng gói toàn bộ kết quả phân tích bùng nổ vào một dictionary mới là `adx_burst_analysis`
  để automation_manager có thể xử lý một cách linh hoạt.
- SỬA LỖI: Chuyển đổi tường minh `is_bearish_dmi` sang `bool` để tương thích JSON."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def get_altcoin_market_snapshot(tickers: Dict[str, Any]) -> Dict[str, Any]:
    """
    v3.1 -- Sửa lỗi JSON Serializable cho các giá trị boolean từ NumPy.
    - Chuyển đổi tường minh các giá trị boolean trong `market_regime` từ `numpy.bool_`
      sang `bool` gốc của Python để đảm bảo tương thích khi lưu file JSON.
    """
    snapshot = {'total_analyzed': 0, 'performance_dist': {'gainers': 0, 'losers': 0, 'neutral': 0}, 'gainers_percentage': 0.0, 'losers_percentage': 0.0, 'median_change_24h': 0.0, 'avg_gainer_change': 0.0, 'avg_loser_change': 0.0, 'volatility_index': 0.0, 'range_position_index': 0.0, 'breakout_strength_index': 0.0, 'verdict': 'Không đủ dữ liệu.', 'market_regime': {}}
    valid_altcoins = {s: t for s, t in tickers.items() if s.endswith(f'/{QUOTE_CURRENCY}') and t and (t.get('quoteVolume', 0) > MIN_DAILY_VOLUME_USDT) and ('UP/' not in s) and ('DOWN/' not in s) and (s.split('/')[0] not in STABLECOIN_LIST) and (s != BTC_SYMBOL) and (s != ETH_SYMBOL) and all((k in t and t[k] is not None for k in ['percentage', 'open', 'high', 'low', 'last']))}
    if not valid_altcoins:
        return snapshot
    data = []
    for symbol, ticker in valid_altcoins.items():
        price_range = ticker['high'] - ticker['low']
        data.append({'symbol': symbol, 'change_24h': ticker.get('percentage', 0.0), 'atr_percent': (ticker['high'] - ticker['low']) / ticker['open'] * 100 if ticker['open'] > 0 else 0, 'position_in_range': (ticker['last'] - ticker['low']) / price_range if price_range > 0 else 0.5})
    df = pd.DataFrame(data)
    if df.empty:
        return snapshot
    total_analyzed = len(df)
    gainers_df = df[df['change_24h'] > 1.0]
    losers_df = df[df['change_24h'] < -1.0]
    gainers = len(gainers_df)
    losers = len(losers_df)
    neutral = total_analyzed - gainers - losers
    snapshot.update({'total_analyzed': total_analyzed, 'performance_dist': {'gainers': gainers, 'losers': losers, 'neutral': neutral}, 'gainers_percentage': gainers / total_analyzed * 100 if total_analyzed > 0 else 0.0, 'losers_percentage': losers / total_analyzed * 100 if total_analyzed > 0 else 0.0, 'median_change_24h': df['change_24h'].median(), 'avg_gainer_change': gainers_df['change_24h'].mean() if not gainers_df.empty else 0.0, 'avg_loser_change': losers_df['change_24h'].mean() if not losers_df.empty else 0.0, 'volatility_index': df['atr_percent'].median(), 'range_position_index': df['position_in_range'].mean() * 100, 'breakout_strength_index': (df['position_in_range'] > 0.9).sum() / total_analyzed * 100 if total_analyzed > 0 else 0.0})
    for key, value in snapshot.items():
        if isinstance(value, (np.int64, np.int32)):
            snapshot[key] = int(value)
        elif isinstance(value, (np.float64, np.float32)):
            snapshot[key] = float(value)
    regime_numpy = {'is_trending_up': snapshot['gainers_percentage'] > 60 and snapshot['median_change_24h'] > 1.5, 'is_trending_down': snapshot['losers_percentage'] > 60 and snapshot['median_change_24h'] < -1.5, 'is_gainer_dominated': snapshot['gainers_percentage'] > max(40, snapshot['losers_percentage'] * 1.8), 'is_loser_dominated': snapshot['losers_percentage'] > max(40, snapshot['gainers_percentage'] * 1.8), 'is_high_volatility': snapshot['volatility_index'] > 8.0, 'is_low_volatility': snapshot['volatility_index'] < 3.5, 'has_strong_momentum': snapshot['range_position_index'] > 65 and snapshot['breakout_strength_index'] > 15, 'has_weak_momentum': snapshot['range_position_index'] < 35}
    regime = {key: bool(value) for key, value in regime_numpy.items()}
    snapshot['market_regime'] = regime
    if regime['is_trending_up']:
        verdict = f'THỊ TRƯỜNG TĂNG TRƯỞNG: {snapshot['gainers_percentage']:.0f}% số coin tăng giá, lực mua lan tỏa.'
    elif regime['is_trending_down']:
        verdict = f'THỊ TRƯỜNG SUY YẾU: {snapshot['losers_percentage']:.0f}% số coin giảm giá, áp lực bán lan tỏa.'
    elif regime['is_gainer_dominated'] and regime['has_strong_momentum']:
        verdict = f'THỊ TRƯỜNG NÓNG: Phe mua chiếm ưu thế rõ rệt ({snapshot['gainers_percentage']:.0f}%) với động lượng mạnh.'
    elif regime['is_loser_dominated']:
        verdict = f'THỊ TRƯỜNG LẠNH: Rủi ro cao, phe bán đang kiểm soát ({snapshot['losers_percentage']:.0f}%).'
    elif regime['is_low_volatility']:
        verdict = f'THỊ TRƯỜNG TÍCH LŨY: Biến động thấp (ATR {snapshot['volatility_index']:.1f}%), có thể sắp có biến động mạnh.'
    else:
        verdict = 'THỊ TRƯỜNG PHÂN HÓA: Không có xu hướng rõ ràng, cần lựa chọn cẩn thận.'
    snapshot['verdict'] = verdict
    return snapshot

def get_all_usdt_pairs(exchange: ccxt.Exchange) -> Tuple[List[str], Dict[str, Any], Dict[str, Any]]:
    """
    v2.7 - Sử dụng danh sách Top CoinMarketCap tĩnh.
    - CẬP NHẬT:
      - Loại bỏ hoàn toàn logic tính toán top 15 theo volume.
      - Thay thế bằng một danh sách các coin hàng đầu được định nghĩa sẵn (TOP_CMC_COINS).
      - Điều này đảm bảo bot luôn theo dõi một nhóm coin "blue-chip" ổn định.
    """
    market_context = analyze_market_context(exchange)
    base_threshold = market_context['btc_context']['filter_threshold']
    all_pairs_for_scan = []
    bypass_count = 0
    try:
        print('Đang tải dữ liệu ticker từ sàn...')
        tickers = exchange.fetch_tickers()
        print('Tải dữ liệu ticker hoàn tất.')
        top_15_cmc_pairs = [f'{coin}/{QUOTE_CURRENCY}' for coin in TOP_CMC_COINS]
        print(f'  -> [THÀNH CÔNG] Đã xác định danh sách theo dõi Top CoinMarketCap: {', '.join(top_15_cmc_pairs)}')
        for symbol, ticker in tickers.items():
            try:
                market_info = exchange.market(symbol)
            except ccxt.BadSymbol:
                continue
            is_valid_active_spot_market = market_info.get('spot', False) and market_info.get('active', False)
            if not (symbol.endswith(f'/{QUOTE_CURRENCY}') and ticker and is_valid_active_spot_market):
                continue
            base_currency = symbol.split('/')[0]
            if 'UP/' in symbol or 'DOWN/' in symbol or base_currency in STABLECOIN_LIST:
                continue
            quote_volume = ticker.get('quoteVolume', 0)
            change_24h = ticker.get('percentage')
            if not quote_volume or quote_volume < MIN_DAILY_VOLUME_USDT or change_24h is None:
                continue
            if change_24h <= market_context['btc_context']['filter_threshold']:
                all_pairs_for_scan.append(symbol)
                continue
            if WARHORSE_BYPASS_ENABLED and market_context['btc_context']['filter_threshold'] < change_24h <= WARHORSE_CANDIDATE_MAX_24H_CHANGE:
                has_high_volume = quote_volume > MIN_DAILY_VOLUME_USDT * WARHORSE_CANDIDATE_MIN_VOLUME_FACTOR
                high_24h, low_24h, last_price = (ticker.get('high'), ticker.get('low'), ticker.get('last'))
                has_sustained_momentum = False
                if high_24h and low_24h and last_price:
                    price_range = high_24h - low_24h
                    if price_range > 0 and (last_price - low_24h) / price_range >= WARHORSE_CANDIDATE_MIN_RANGE_POSITION:
                        has_sustained_momentum = True
                if has_high_volume and has_sustained_momentum:
                    all_pairs_for_scan.append(symbol)
                    bypass_count += 1
        altcoin_snapshot = get_altcoin_market_snapshot(tickers)
        print(f'\n--- Phân tích Sức nóng Altcoin (mẫu {altcoin_snapshot.get('total_analyzed', 0)} cặp) ---')
        if bypass_count > 0:
            print(f"  -> Cơ chế 'Vượt Rào' đã đặc cách cho {bypass_count} mã có dấu hiệu leader.")
        print(f'\nLọc hoàn tất. Tìm thấy {len(all_pairs_for_scan)} cặp hợp lệ để quét sâu.')
        summary = {'market_context': market_context, 'total_pairs_in_universe': len(all_pairs_for_scan), 'altcoin_snapshot': altcoin_snapshot, 'tickers': tickers, 'top_15_by_volume': top_15_cmc_pairs}
        return (all_pairs_for_scan, summary, tickers)
    except Exception as e:
        print(f'LỖI NGHIÊM TRỌNG khi lấy danh sách cặp giao dịch: {e}')
        empty_context = {'btc_context': {}, 'eth_context': {}}
        return ([], {'market_context': empty_context, 'total_pairs_in_universe': 0, 'altcoin_snapshot': {}, 'tickers': {}, 'top_15_by_volume': []}, {})

def fetch_ohlcv_data(exchange: ccxt.Exchange, pair: str, timeframe: str, limit: int=300) -> Optional[pd.DataFrame]:
    try:
        if not exchange.has['fetchOHLCV']:
            return None
        ohlcv = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df.set_index('timestamp')
    except Exception:
        return None

def add_relative_strength_data(df: pd.DataFrame, btc_df: pd.DataFrame) -> Optional[pd.DataFrame]:
    if df is None:
        return None
    if df.empty or btc_df is None or btc_df.empty or ('close' not in btc_df.columns):
        df['rs'] = np.nan
        df['rs_ma'] = np.nan
        return df
    df.index = pd.to_datetime(df.index)
    btc_df.index = pd.to_datetime(btc_df.index)
    data = pd.concat([df['close'], btc_df['close']], axis=1, keys=['asset', 'btc'])
    data['btc'] = data['btc'].reindex(data.index, method='ffill')
    data.dropna(subset=['asset'], inplace=True)
    if data.empty or 'btc' not in data.columns or data['btc'].isnull().all():
        df['rs'] = np.nan
        df['rs_ma'] = np.nan
        return df
    data['rs'] = data['asset'] / data['btc']
    data['rs_ma'] = ta.SMA(data['rs'], timeperiod=50)
    df['rs'] = data['rs']
    df['rs_ma'] = data['rs_ma']
    return df

def calculate_indicators(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Hàm tính toán chỉ báo v2.0 - Sửa lỗi logic tính toán Mây Ichimoku.
    - Đảm bảo các chỉ báo dịch chuyển (shifted) được tính toán trên bộ dữ liệu
      đầy đủ trước khi loại bỏ các hàng NaN, giúp bảo toàn dữ liệu dự báo.
    """
    if df is None or len(df) < 100:
        return None
    df['atr'] = ta.ATR(df, timeperiod=14)
    df['vol_ma_20'] = ta.SMA(df['volume'], timeperiod=20)
    df['ema_7'] = ta.EMA(df['close'], timeperiod=7)
    df['ema_8'] = ta.EMA(df['close'], timeperiod=8)
    df['ema_9'] = ta.EMA(df['close'], timeperiod=9)
    df['ema_21'] = ta.EMA(df, timeperiod=21)
    df['ema_50'] = ta.EMA(df, timeperiod=50)
    df['ema_200'] = ta.EMA(df, timeperiod=200)
    tenkan_period, kijun_period, senkou_b_period, displacement = (9, 26, 52, 26)
    df['tenkan_sen'] = (df['high'].rolling(window=tenkan_period).max() + df['low'].rolling(window=tenkan_period).min()) / 2
    df['kijun_sen'] = (df['high'].rolling(window=kijun_period).max() + df['low'].rolling(window=kijun_period).min()) / 2
    senkou_a_raw = (df['tenkan_sen'] + df['kijun_sen']) / 2
    df['senkou_a'] = senkou_a_raw.shift(displacement - 1)
    senkou_b_raw = (df['high'].rolling(window=senkou_b_period).max() + df['low'].rolling(window=senkou_b_period).min()) / 2
    df['senkou_b'] = senkou_b_raw.shift(displacement - 1)
    df['chikou_span'] = df['close'].shift(-(displacement - 1))
    df['adx'] = ta.ADX(df, timeperiod=14)
    df['plus_di'] = ta.PLUS_DI(df, timeperiod=14)
    df['minus_di'] = ta.MINUS_DI(df, timeperiod=14)
    bollinger = ta.BBANDS(df, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
    df['bb_upper'] = bollinger['upperband']
    df['bb_middle'] = bollinger['middleband']
    df['bb_lower'] = bollinger['lowerband']
    df['bb_width'] = np.where(df['bb_middle'] > 0, (df['bb_upper'] - df['bb_lower']) / df['bb_middle'], 0)
    df['bbw_percentile'] = df['bb_width'].rolling(100).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False) * 100
    df['rsi'] = ta.RSI(df, timeperiod=14)
    df['rsi_21'] = ta.RSI(df, timeperiod=21)
    df['cdl_shootingstar'] = ta.CDLSHOOTINGSTAR(df)
    df['cdl_hangingman'] = ta.CDLHANGINGMAN(df)
    df['cdl_engulfing'] = ta.CDLENGULFING(df)
    df['ma_trend'] = ta.EMA(df, timeperiod=27)
    df['ma_trend_rising'] = df['ma_trend'] > df['ma_trend'].shift(1)
    df['body_size'] = abs(df['close'] - df['open'])
    df['body_size_ma'] = df['body_size'].rolling(window=20).mean()
    df['local_high_20'] = df['high'].rolling(window=20).max().shift(1)
    df['cdl_hammer'] = ta.CDLHAMMER(df)
    df['cdl_doji'] = ta.CDLDOJI(df)
    df['cdl_piercing'] = ta.CDLPIERCING(df)
    stoch = ta.STOCH(df, fastk_period=14, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
    df['slowk'] = stoch['slowk']
    df['slowd'] = stoch['slowd']
    df.dropna(subset=['atr', 'vol_ma_20', 'ema_200', 'tenkan_sen', 'kijun_sen', 'adx', 'bb_middle', 'rsi', 'slowk', 'slowd'], inplace=True)
    if df.empty:
        return None
    return df

def _calculate_btc_volatility(df: pd.DataFrame, atr_period: int=14, atr_ma_period: int=50) -> Dict[str, Any]:
    """
    Phân tích biến động (volatility) dựa trên ATR.
    So sánh ATR ngắn hạn với ATR trung bình dài hạn để xác định
    biến động đang tăng, giảm hay ổn định.
    """
    if df is None or len(df) < atr_ma_period or 'atr' not in df.columns:
        return {'state': 'Không xác định', 'atr_value': 0, 'ratio': 1.0}
    df['atr_ma'] = ta.SMA(df['atr'], timeperiod=atr_ma_period)
    last_atr = df['atr'].iloc[-1]
    avg_atr = df['atr_ma'].iloc[-1]
    if avg_atr == 0:
        return {'state': 'Bình thường', 'atr_value': last_atr, 'ratio': 1.0}
    ratio = last_atr / avg_atr
    state = 'Bình thường'
    if ratio > 1.25:
        state = 'Mở rộng'
    elif ratio < 0.75:
        state = 'Thu hẹp'
    return {'state': state, 'atr_value': last_atr, 'ratio': ratio}

def _calculate_scenario_probability(btc_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ước tính xác suất thành công cho kịch bản chính dựa trên sự hội tụ
    của các yếu tố phân tích.
    """
    base_prob = 50.0
    factors = []
    state_4h = btc_context.get('analysis_4h', '')
    if 'TĂNG MẠNH' in state_4h:
        base_prob += 15
        factors.append('(+) Cấu trúc 4H tăng mạnh')
    elif 'GIẢM MẠNH' in state_4h or 'XU HƯỚNG GIẢM' in state_4h:
        base_prob -= 15
        factors.append('(-) Cấu trúc 4H giảm mạnh')
    mom_4h = btc_context.get('momentum_verdict_4h', '')
    mom_1h = btc_context.get('momentum_verdict_1h', '')
    if ('MUA' in mom_1h or 'TĂNG' in mom_1h) and ('MUA' in mom_4h or 'TĂNG' in mom_4h):
        base_prob += 10
        factors.append('(+) Động lượng 1H-4H đồng thuận tăng')
    elif ('BÁN' in mom_1h or 'GIẢM' in mom_1h) and ('BÁN' in mom_4h or 'GIẢM' in mom_4h):
        base_prob -= 10
        factors.append('(-) Động lượng 1H-4H đồng thuận giảm')
    else:
        factors.append('(~) Động lượng không đồng thuận')
    vol_1h_state = btc_context.get('volatility_1h', {}).get('state', '')
    prediction_dir = btc_context.get('price_prediction', {}).get('direction', '')
    if vol_1h_state == 'Mở rộng' and prediction_dir in ['TĂNG', 'GIẢM']:
        base_prob += 5
        factors.append('(+) Biến động ủng hộ xu hướng')
    elif vol_1h_state == 'Thu hẹp':
        base_prob -= 5
        factors.append('(-) Biến động thấp, rủi ro phá vỡ giả')
    conclusion = btc_context.get('conclusion', '')
    if 'ĐẢO CHIỀU' in conclusion or 'BÁN THÁO' in conclusion:
        base_prob -= 20
        factors.append('(-) Cảnh báo rủi ro cao (Phân kỳ/Bán tháo)')
    final_prob = max(10.0, min(90.0, base_prob))
    verdict = 'TRUNG BÌNH'
    if final_prob >= 70:
        verdict = 'CAO'
    elif final_prob >= 60:
        verdict = 'KHÁ'
    elif final_prob < 40:
        verdict = 'THẤP'
    return {'probability_percent': final_prob, 'verdict': verdict, 'factors': factors}

def analyze_rsi_adx_statistical_model(df: pd.DataFrame, timeframe_name: str) -> Dict[str, Any]:
    """
    MÔ HÌNH THỐNG KÊ RSI + ADX v1.0 - Bộ não Dự báo Xác suất.
    
    Phân tích 5 phiên gần nhất để xác định trạng thái và xu hướng của động lượng,
    từ đó tính toán xác suất tăng/giảm và đưa ra khuyến nghị.

    Returns:
        Một dictionary chứa xác suất, khuyến nghị và các bằng chứng phân tích.
    """
    analysis = {'probability_increase': 50.0, 'recommendation': 'CHỜ', 'verdict': 'Trung lập', 'evidence': []}
    if df is None or len(df) < 20:
        analysis['verdict'] = 'Không đủ dữ liệu'
        analysis['evidence'].append('Thiếu dữ liệu lịch sử.')
        return analysis
    recent_df = df.tail(5)
    if len(recent_df) < 5:
        analysis['verdict'] = 'Không đủ dữ liệu gần đây'
        analysis['evidence'].append('Không đủ 5 nến để phân tích chuỗi.')
        return analysis
    last_candle = recent_df.iloc[-1]
    x_axis = np.arange(5)
    rsi_slope = np.polyfit(x_axis, recent_df['rsi'], 1)[0]
    adx_slope = np.polyfit(x_axis, recent_df['adx'], 1)[0]
    total_score = 0
    rsi_score = 0
    current_rsi = last_candle['rsi']
    if current_rsi > 65:
        rsi_score -= 15
        analysis['evidence'].append(f'RSI Quá mua ({current_rsi:.1f})')
    elif current_rsi > 55:
        rsi_score += 20
        analysis['evidence'].append(f'RSI Đà tăng tốt ({current_rsi:.1f})')
    elif current_rsi < 35:
        rsi_score += 10
        analysis['evidence'].append(f'RSI Quá bán ({current_rsi:.1f})')
    elif current_rsi < 45:
        rsi_score -= 15
        analysis['evidence'].append(f'RSI Đà giảm ({current_rsi:.1f})')
    else:
        analysis['evidence'].append(f'RSI Trung lập ({current_rsi:.1f})')
    if rsi_slope > 1.0:
        rsi_score += 25
        analysis['evidence'].append('Chuỗi RSI tăng mạnh')
    elif rsi_slope > 0.3:
        rsi_score += 15
        analysis['evidence'].append('Chuỗi RSI tăng nhẹ')
    elif rsi_slope < -1.0:
        rsi_score -= 25
        analysis['evidence'].append('Chuỗi RSI giảm mạnh')
    elif rsi_slope < -0.3:
        rsi_score -= 15
        analysis['evidence'].append('Chuỗi RSI giảm nhẹ')
    total_score += rsi_score * 0.45
    adx_score = 0
    current_adx = last_candle['adx']
    plus_di = last_candle['plus_di']
    minus_di = last_candle['minus_di']
    is_trending = current_adx > 23
    is_bullish_trend = is_trending and plus_di > minus_di
    is_bearish_trend = is_trending and minus_di > plus_di
    if is_bullish_trend:
        adx_score += 30
        analysis['evidence'].append(f'ADX xác nhận Tăng ({current_adx:.1f})')
        if adx_slope > 0.3:
            adx_score += 20
            analysis['evidence'].append('Xu hướng tăng mạnh lên')
    elif is_bearish_trend:
        adx_score -= 30
        analysis['evidence'].append(f'ADX xác nhận Giảm ({current_adx:.1f})')
        if adx_slope > 0.3:
            adx_score -= 20
            analysis['evidence'].append('Xu hướng giảm mạnh lên')
    else:
        adx_score -= 10
        analysis['evidence'].append(f'ADX không có xu hướng ({current_adx:.1f})')
    total_score += adx_score * 0.55
    probability = 50.0 + total_score / 50.0 * 50.0
    analysis['probability_increase'] = max(0.0, min(100.0, probability))
    if analysis['probability_increase'] > 65:
        analysis['recommendation'] = 'ƯU TIÊN MUA SPOT'
        analysis['verdict'] = 'Tăng giá'
    elif analysis['probability_increase'] < 35:
        analysis['recommendation'] = 'CHỜ'
        analysis['verdict'] = 'Giảm giá'
    else:
        analysis['recommendation'] = 'CHỜ'
        analysis['verdict'] = 'Trung lập'
    return analysis

def analyze_trend_cycle(df_1h: pd.DataFrame) -> Dict[str, Any]:
    """
    v2.0 - Tái cấu trúc để sử dụng dữ liệu có sẵn và cung cấp phân tích chi tiết hơn.
    """
    if len(df_1h) < 50 or not all((c in df_1h.columns for c in ['close', 'high', 'rsi', 'ema_50', 'ema_200'])):
        return {'stage': 'Lỗi Dữ Liệu', 'score': 0, 'reason': 'Không đủ dữ liệu hoặc thiếu chỉ báo cần thiết'}
    recent_df = df_1h.tail(30).copy()
    if recent_df.empty:
        return {'stage': 'Lỗi Dữ Liệu', 'score': 0, 'reason': 'Không đủ dữ liệu gần đây'}
    last = recent_df.iloc[-1]
    high_prices = recent_df['high']
    rsi_values = recent_df['rsi']
    price_peak_idx = high_prices.idxmax()
    is_bearish_divergence = False
    if price_peak_idx == high_prices.index[-1]:
        second_price_peak = high_prices.drop(price_peak_idx).max()
        if not pd.isna(second_price_peak):
            second_price_peak_idx = high_prices[high_prices == second_price_peak].index[-1]
            if last['high'] > second_price_peak and last['rsi'] < rsi_values.loc[second_price_peak_idx]:
                is_bearish_divergence = True
    is_overextended = last['close'] > last['ema_50'] * 1.15
    if is_bearish_divergence and is_overextended:
        return {'stage': 'Sóng Cuối', 'score': -30, 'reason': 'Rủi ro Phân kỳ âm + Giá quá dãn'}
    is_strong_uptrend = last['close'] > last['ema_50'] > last['ema_200']
    is_rsi_healthy = 55 < last['rsi'] < 70
    if is_strong_uptrend and is_rsi_healthy:
        return {'stage': 'Sóng Giữa', 'score': 10, 'reason': 'Xu hướng tăng trưởng khỏe mạnh'}
    is_just_crossed_ema200 = df_1h.iloc[-2]['close'] < df_1h.iloc[-2]['ema_200'] and last['close'] > last['ema_200']
    if is_just_crossed_ema200 and (not is_strong_uptrend):
        return {'stage': 'Sóng Đầu', 'score': 5, 'reason': 'Giai đoạn đầu của xu hướng'}
    is_consolidating_up = last['close'] > last['ema_50'] and last['rsi'] > 50
    if is_consolidating_up:
        return {'stage': 'Tích Lũy Tăng', 'score': 3, 'reason': 'Tích lũy trong xu hướng tăng'}
    is_correcting = last['close'] < last['ema_50'] and last['ema_50'] > last['ema_200']
    if is_correcting:
        return {'stage': 'Điều Chỉnh', 'score': -5, 'reason': 'Điều chỉnh trong xu hướng tăng'}
    return {'stage': 'Đi Ngang', 'score': 0, 'reason': 'Đi ngang trên nền tảng vĩ mô'}

def find_bullish_divergence(*args, **kwargs):
    """v2.1 - Tìm kiếm phân kỳ tăng giá và trả về mức giá tại điểm đảo chiều."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def score_long_term_squeeze(*args, **kwargs):
    """Phân tích và chấm điểm cho các tín hiệu nén dài hạn v3.0 - Có "Trí nhớ".
Hàm này đánh giá chất lượng của cả giai đoạn tích lũy, không chỉ cây nến cuối."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def check_reversal_patterns_at_support(df: pd.DataFrame, timeframe_name: str) -> Tuple[int, List[str]]:
    """
    Kiểm tra các mẫu nến đảo chiều tăng giá (Hammer, Piercing) xuất hiện gần vùng hỗ trợ.
    """
    score = 0
    reasons = []
    if df is None or len(df) < 5 or (not all((c in df.columns for c in ['cdl_hammer', 'cdl_piercing', 'low', 'bb_lower', 'ema_50']))):
        return (0, [])
    for i in range(1, 4):
        if len(df) <= i:
            continue
        candle = df.iloc[-i]
        is_hammer = candle['cdl_hammer'] == 100
        is_piercing = candle['cdl_piercing'] == 100
        if not (is_hammer or is_piercing):
            continue
        support_levels = {'dải BB dưới': candle['bb_lower'], 'EMA 50': candle['ema_50']}
        pattern_name = 'Hammer' if is_hammer else 'Piercing Line'
        for support_name, support_price in support_levels.items():
            if support_price > 0 and abs(candle['low'] - support_price) / candle['low'] < 0.005:
                reason = f'Nến {pattern_name} {timeframe_name} tại {support_name}'
                if reason not in reasons:
                    score += 15
                    reasons.append(reason)
    return (score, reasons)

def check_oversold_oscillator(df: pd.DataFrame, timeframe_name: str) -> Tuple[int, List[str]]:
    """
    Kiểm tra tín hiệu mua từ Stochastic khi nó cắt lên từ vùng quá bán.
    """
    score = 0
    reasons = []
    if df is None or len(df) < 3 or (not all((c in df.columns for c in ['slowk', 'slowd']))):
        return (0, [])
    last = df.iloc[-1]
    prev = df.iloc[-2]
    is_crossover_in_oversold = prev['slowk'] < 25 and prev['slowd'] < 25 and (last['slowk'] > last['slowd']) and (prev['slowk'] < prev['slowd'])
    if is_crossover_in_oversold:
        score += 10
        reasons.append(f'Stochastic {timeframe_name} cắt lên từ vùng quá bán')
    return (score, reasons)

def score_trending_pullback_setup(*args, **kwargs):
    """Module chuyên chấm điểm cho chiến lược "Trending-Pullback".
(v2.1 - Tối ưu hóa hiệu năng, chống timeout)"""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def analyze_breakout_volume_quality(df: pd.DataFrame, breakout_candle_index: int) -> Dict[str, Any]:
    """
    Phân tích chất lượng Volume của một cú breakout.
    - Kiểm tra độ đột biến của nến breakout.
    - Kiểm tra sự duy trì (follow-through) của volume ở nến tiếp theo.
    """
    if breakout_candle_index < 1 or breakout_candle_index >= len(df) - 1:
        return {'is_quality': False, 'score_impact': 0, 'reason': 'Dữ liệu không đủ'}
    breakout_candle = df.iloc[breakout_candle_index]
    confirmation_candle = df.iloc[breakout_candle_index + 1]
    is_spike = breakout_candle['volume'] > breakout_candle['vol_ma_20'] * 2.5
    is_sustained = confirmation_candle['volume'] > breakout_candle['vol_ma_20'] * 1.5
    score_impact = 0
    reasons = []
    if is_spike:
        score_impact += 15
        reasons.append('Volume breakout đột biến')
    else:
        score_impact -= 30
        reasons.append('Volume breakout yếu')
    if is_sustained:
        score_impact += 20
        reasons.append('Volume xác nhận duy trì tốt')
    else:
        score_impact -= 40
        reasons.append('CẢNH BÁO: Volume tắt ngấm sau breakout')
    return {'is_quality': is_spike and is_sustained, 'score_impact': score_impact, 'reason': ' | '.join(reasons)}

def find_bearish_divergence(*args, **kwargs):
    """Tìm kiếm phân kỳ âm trên khung thời gian hiện tại.
Trả về (True, lý do) nếu tìm thấy."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def _synthesize_market_extremes(*args, **kwargs):
    """"HỘI ĐỒNG CHUYÊN GIA" v1.0 - Tổng hợp tín hiệu để xác định Đỉnh/Đáy tiềm năng.

Hàm này hoạt động như một bộ não cấp cao, lấy ý kiến từ nhiều chuyên gia
phân tích khác nhau để đưa ra một nhận định duy nhất về khả năng thị trường
đang ở một điểm cực trị quan trọng.

Returns:
    Một dictionary chứa kết luận, điểm tin cậy, và các bằng chứng đã được thu thập."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def analyze_breakout_structure(*args, **kwargs):
    """Phân tích cấu trúc breakout v2.0 - Tích hợp "Bộ Lọc Khoảng Cách".
- Vô hiệu hóa tín hiệu "Breakout-Pre" nếu giá hiện tại đã rơi quá xa
  khỏi vùng kháng cự, tránh các tín hiệu chờ đợi vô ích."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def score_breakout_setup(data_1h: pd.DataFrame) -> Dict[str, Any]:
    """
    Module chuyên chấm điểm cho Breakout v4.0 - Sử dụng "Trí Nhớ Tình Báo".
    Hàm này gọi bộ phân tích cấu trúc để đưa ra quyết định dựa trên bối cảnh.
    """
    if data_1h is None or len(data_1h) < 50:
        return {'score': 0, 'reasons': [], 'strategy_tag': None}
    structure_analysis = analyze_breakout_structure(data_1h)
    score = structure_analysis.get('score', 0)
    reasons = structure_analysis.get('reasons', [])
    stage = structure_analysis.get('stage')
    strategy_tag = None
    if not structure_analysis.get('is_valid', False):
        return {'score': 0, 'reasons': reasons, 'strategy_tag': None}
    if stage == 'CONSOLIDATING':
        strategy_tag = 'Breakout-Pre'
    elif stage in ['BREAKOUT_ATTEMPT', 'CONFIRMED_HOLD']:
        strategy_tag = 'Instant-Explosion'
    else:
        return {'score': 0, 'reasons': reasons, 'strategy_tag': None}
    has_divergence, div_reason = find_bearish_divergence(data_1h)
    if has_divergence:
        score -= 60
        reasons.append(f'CẢNH BÁO: {div_reason}')
    if score < 30:
        return {'score': 0, 'reasons': reasons, 'strategy_tag': strategy_tag}
    return {'score': score, 'reasons': reasons, 'strategy_tag': strategy_tag}

def find_double_bottom_pattern(*args, **kwargs):
    """Phát hiện sớm mẫu hình Hai Đáy (Double Bottom - W Pattern).
Đây là một tín hiệu đảo chiều tăng giá rất sớm."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def find_triple_bottom_pattern(*args, **kwargs):
    """Phát hiện sớm mẫu hình Ba Đáy (Triple Bottom).
Đây là một phiên bản nâng cao và đáng tin cậy hơn của Hai Đáy."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def detect_kumo_twist(*args, **kwargs):
    """Phát hiện Kumo Twist (Mây xoắn) tăng giá sắp xảy ra, một tín hiệu dự báo sớm.
Cộng điểm mạnh hơn nếu Mây tại điểm xoắn là mỏng."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def _measure_downward_momentum(*args, **kwargs):
    """"BỘ GHI NHẬN BỐI CẢNH" v1.1 (Đã nới lỏng)

Đo lường đà giảm gần đây để cung cấp bối cảnh. Sau khi tích hợp bộ lọc EMA7,
hàm này không còn đóng vai trò VETO mà chỉ áp dụng một điểm phạt nhẹ."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def _find_significant_recent_low(df: pd.DataFrame, lookback: int=20) -> Optional[Dict[str, Any]]:
    """
    "BỘ NHỚ NGẮN HẠN" - Tìm kiếm một "sự kiện đáy" quan trọng trong quá khứ gần.
    
    Hàm này quét `lookback` nến gần nhất để xác định điểm đáy thấp nhất và
    trả về thông tin chi tiết về nó, bao gồm giá, vị trí và thời gian đã trôi qua.
    
    Returns:
        Một dictionary chứa thông tin về đáy, hoặc None nếu không tìm thấy.
    """
    if df is None or len(df) < lookback:
        return None
    recent_df = df.tail(lookback)
    low_idx_in_recent = recent_df['low'].idxmin()
    bottom_candle = recent_df.loc[low_idx_in_recent]
    candles_ago = len(recent_df) - recent_df.index.get_loc(low_idx_in_recent) - 1
    if 1 <= candles_ago <= lookback - 5:
        return {'price': bottom_candle['low'], 'candle': bottom_candle, 'index': low_idx_in_recent, 'candles_ago': candles_ago}
    return None

def _assess_recovery_strength(df: pd.DataFrame, low_index: pd.Timestamp) -> Dict[str, Any]:
    """
    "MÁY ĐO SỨC MẠNH" - Đánh giá chất lượng của sự phục hồi sau khi đáy được hình thành.
    
    Hàm này phân tích các nến KỂ TỪ sau "sự kiện đáy" để tìm bằng chứng
    cho thấy phe mua đang quay trở lại.
    
    Returns:
        Một dictionary chứa điểm số và lý do cho sức mạnh hồi phục.
    """
    recovery_df = df[df.index > low_index]
    if recovery_df.empty:
        return {'score': -30, 'reasons': ['Chưa có dấu hiệu hồi phục']}
    score = 0
    reasons = []
    num_candles = len(recovery_df)
    green_candles = (recovery_df['close'] > recovery_df['open']).sum()
    green_ratio = green_candles / num_candles
    if green_ratio >= 0.6:
        score += 25
        reasons.append(f'Hồi phục tốt ({green_candles}/{num_candles} nến xanh)')
    elif green_ratio < 0.4:
        score -= 20
        reasons.append(f'Hồi phục yếu ({green_candles}/{num_candles} nến xanh)')
    last_recovery_candle = recovery_df.iloc[-1]
    if last_recovery_candle['close'] > last_recovery_candle['ema_9']:
        score += 15
        reasons.append('Giá đã lấy lại EMA 9')
    if last_recovery_candle['close'] > last_recovery_candle['tenkan_sen']:
        score += 10
        reasons.append('Giá đã vượt Tenkan-sen')
    if last_recovery_candle['rsi'] > 45:
        score += 10
        reasons.append('RSI đã thoát khỏi vùng nguy hiểm')
    return {'score': score, 'reasons': reasons}

def _analyze_ema7_positioning(df: pd.DataFrame, timeframe_name: str) -> Dict[str, Any]:
    """
    "CẢM BIẾN VẬN TỐC" EMA7 v2.1 - Tích hợp Phân tích Chất lượng Vượt cản.
    
    Phân tích vị trí của giá so với đường EMA7 để đánh giá động lượng ngắn hạn.
    - VETO (Phủ quyết): Nếu TẤT CẢ 3 NẾN CUỐI CÙNG đều nằm dưới EMA7, đây là
      dấu hiệu "dao rơi" với động lượng giảm tức thời rất mạnh và sẽ bị phủ quyết.
    - CỘNG ĐIỂM (Nâng cao): Cộng điểm thưởng cao (+25) nếu phát hiện một cú vượt lên
      trên EMA7 được xác nhận bởi cả NẾN XANH và VOLUME MẠNH.
      Hàm sẽ kiểm tra 2 nến cuối cùng cho tín hiệu chất lượng cao này.
    """
    if df is None or len(df) < 5 or 'ema_7' not in df.columns or ('vol_ma_20' not in df.columns):
        return {'score_impact': 0, 'reason': ''}
    VETO_LOOKBACK = 3
    last_three_candles = df.tail(VETO_LOOKBACK)
    all_three_below = (last_three_candles['close'] < last_three_candles['ema_7']).all()
    if all_three_below:
        score_impact = -50
        reason = f'VETO (Dao Rơi): Cả {VETO_LOOKBACK} nến cuối đều dưới EMA7 {timeframe_name}'
        return {'score_impact': score_impact, 'reason': reason}
    for i in range(1, 3):
        if len(df) <= i + 1:
            continue
        candle_to_check = df.iloc[-i]
        candle_before_that = df.iloc[-(i + 1)]
        is_crossover = candle_before_that['close'] < candle_before_that['ema_7'] and candle_to_check['close'] > candle_to_check['ema_7']
        is_green_candle = candle_to_check['close'] > candle_to_check['open']
        has_strong_volume = candle_to_check.get('volume', 0) > candle_to_check.get('vol_ma_20', 0) * 1.5
        if is_crossover and is_green_candle and has_strong_volume:
            score_impact = 25
            candle_age = 'hiện tại' if i == 1 else 'trước đó'
            reason = f'✅ Vượt EMA7 {timeframe_name} (Nến {candle_age} xanh, vol mạnh)'
            return {'score_impact': score_impact, 'reason': reason}
    return {'score_impact': 0, 'reason': ''}

def _apply_reversal_safety_filter(*args, **kwargs):
    """"CỔNG AN NINH" cho Chiến lược Bắt Đáy (v1.0).

Hàm này áp dụng một bộ lọc VETO nghiêm ngặt cho các tín hiệu đảo chiều:
1. VETO nếu giá 1H nằm dưới EMA7.
2. MIỄN TRỪ VETO chỉ khi RSI(21) trên 1H < 35 (xác nhận kiệt sức).

Returns:
    (is_vetoed, reason) - Tuple chứa cờ VETO và lý do."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def _find_reversal_opportunity(data_1h: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    "BỘ KÍCH HOẠT ĐẢO CHIỀU" v1.1 - Hệ thống 2 cấp độ RSI.

    Hàm này quét tìm các cơ hội bắt đáy với độ nhạy cao hơn:
    1. TÍN HIỆU QUÁ BÁN MẠNH (RSI < 35): Tín hiệu mạnh, điểm cơ bản cao.
    2. TÍN HIỆU CẢNH BÁO SỚM (35 <= RSI < 38): Tín hiệu yếu hơn, điểm cơ bản thấp hơn.
    3. TÍN HIỆU GẦN ĐÂY: Một đáy đáng kể đã hình thành trong vòng 12 nến vừa qua.

    Returns:
        Một dictionary chứa thông tin về tín hiệu nếu tìm thấy, ngược lại trả về None.
    """
    if data_1h is None or len(data_1h) < 20:
        return None
    last_candle = data_1h.iloc[-1]
    current_rsi = last_candle['rsi']
    if current_rsi < 35:
        return {'type': 'OVERSOLD_RSI', 'reason': f'🔥 RSI 1H đang quá bán mạnh ({current_rsi:.1f})', 'event_candle': last_candle, 'event_index': last_candle.name, 'base_score': 30}
    elif current_rsi < 38:
        return {'type': 'OVERSOLD_RSI', 'reason': f'⏳ RSI 1H tiến vào vùng yếu ({current_rsi:.1f})', 'event_candle': last_candle, 'event_index': last_candle.name, 'base_score': 20}
    bottom_event = _find_significant_recent_low(data_1h, lookback=12)
    if bottom_event:
        candles_ago = bottom_event['candles_ago']
        reason_str = f'Đáy hình thành cách đây {candles_ago} nến 1H'
        base_score = 40 if candles_ago <= 3 else 25
        return {'type': 'RECENT_LOW', 'reason': reason_str, 'event_candle': bottom_event['candle'], 'event_index': bottom_event['index'], 'base_score': base_score}
    return None

def score_reversal_setup(pair: str, data_4h: pd.DataFrame, data_1h: pd.DataFrame, data_5m: pd.DataFrame) -> Dict[str, Any]:
    """
    Module chuyên chấm điểm "Reversal-Scout" v6.0 - ĐÃ NGƯNG SỬ DỤNG.
    
    CẬP NHẬT:
    - Hàm này đã được vô hiệu hóa.
    - Logic bắt đáy giờ đây CHỈ dựa vào việc phát hiện các mẫu hình
      Hai Đáy (Double Bottom) và Ba Đáy (Triple Bottom) trong hàm `analyze_and_score`.
    - Điều này tuân thủ yêu cầu chiến lược mới: chỉ vào lệnh khi có cấu trúc đáy rõ ràng.
    """
    return {'score': 0, 'reasons': []}

def analyze_and_score(*args, **kwargs):
    """Hàm phân tích tổng hợp v6.9 - Chuyên sâu Bắt Đáy theo Mẫu hình.

CẬP NHẬT:
- Loại bỏ hoàn toàn việc gọi hàm `score_reversal_setup` cũ (dựa trên RSI).
- Chiến lược "Reversal-Scout" giờ đây chỉ được kích hoạt bởi các hàm phát hiện
  mẫu hình `find_triple_bottom_pattern` và `find_double_bottom_pattern`,
  đảm bảo chỉ các tín hiệu có cấu trúc đáy rõ ràng mới được xem xét."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def assess_short_term_health(*args, **kwargs):
    """v3.0 - Đưa ra "Tư thế Chiến thuật" thay vì chỉ là "Tốt/Rủi ro"."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def calculate_success_probability(*args, **kwargs):
    """Ước tính xác suất thành công của một kế hoạch tác chiến dựa trên tất cả các yếu tố."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def run_scan() -> Dict[str, Any]:
    print('--- Bắt đầu phiên quét mới ---')
    exchange = initialize_exchange(EXCHANGE)
    if not exchange:
        return {'recommendations': [], 'summary': {}}
    pairs, scan_summary, tickers = get_all_usdt_pairs(exchange)
    market_context = scan_summary.get('market_context', {})
    if not pairs:
        print('Không tìm thấy cặp giao dịch nào để quét.')
        return {'recommendations': [], 'summary': scan_summary}
    print('Đang tải dữ liệu BTC để phân tích Sức Mạnh Tương Đối...')
    btc_data_4h = fetch_ohlcv_data(exchange, BTC_SYMBOL, '4h', 300)
    btc_data_1h = fetch_ohlcv_data(exchange, BTC_SYMBOL, '1h', 300)
    if btc_data_1h is None or btc_data_4h is None:
        print('CẢNH BÁO: Không thể lấy dữ liệu BTC, phân tích RS sẽ bị bỏ qua.')
        btc_data_4h, btc_data_1h = (pd.DataFrame(), pd.DataFrame())
    results, total_pairs = ([], len(pairs))
    print(f'\nBắt đầu quá trình quét và phân tích sâu {total_pairs} mục tiêu...')
    for i, pair in enumerate(pairs):
        print(f'  Radar đang quét mục tiêu mới: {pair:<15} ({i + 1}/{total_pairs})', end='\r')
        data_1w = fetch_ohlcv_data(exchange, pair, '1w', 300)
        data_1d = fetch_ohlcv_data(exchange, pair, '1d', 300)
        data_4h = fetch_ohlcv_data(exchange, pair, '4h', 300)
        data_1h = fetch_ohlcv_data(exchange, pair, '1h', 300)
        data_15m = fetch_ohlcv_data(exchange, pair, '15m', 300)
        data_5m = fetch_ohlcv_data(exchange, pair, '5m', 300)
        data_4h = add_relative_strength_data(data_4h, btc_data_4h)
        data_1h = add_relative_strength_data(data_1h, btc_data_1h)
        data_1w = calculate_indicators(data_1w)
        data_1d = calculate_indicators(data_1d)
        data_4h = calculate_indicators(data_4h)
        data_1h = calculate_indicators(data_1h)
        data_15m = calculate_indicators(data_15m)
        data_5m = calculate_indicators(data_5m)
        if any((d is None or d.empty or len(d) < 2 for d in [data_4h, data_1h, data_15m, data_5m])):
            continue
        ticker_info = tickers.get(pair)
        current_price = ticker_info.get('last') if ticker_info else None
        recommendation = analyze_and_score(pair, data_1w, data_1d, data_4h, data_1h, data_15m, data_5m, market_context, current_price, minimum_score=1)
        if recommendation:
            results.append(recommendation)
    print('\nQuét mới hoàn tất.' + ' ' * 40)
    sorted_results = sorted(results, key=lambda x: x['final_score'], reverse=True)
    scan_summary['found_targets'] = len(sorted_results)
    return {'recommendations': sorted_results, 'summary': scan_summary}

def analyze_specific_pairs(pairs_to_analyze: List[str]) -> List[Dict[str, Any]]:
    if not pairs_to_analyze:
        return []
    print(f"\n--- Bắt đầu phân tích lại {len(pairs_to_analyze)} mục tiêu từ 'Bộ Nhớ' ---")
    exchange = initialize_exchange(EXCHANGE)
    if not exchange:
        return []
    market_context = analyze_market_context(exchange)
    try:
        tickers = exchange.fetch_tickers()
    except Exception:
        tickers = {}
        print('Cảnh báo: Không thể tải tickers khi phân tích lại, sẽ không có giá hiện tại.')
    print('Đang tải dữ liệu BTC để phân tích lại Sức Mạnh Tương Đối...')
    btc_data_4h = fetch_ohlcv_data(exchange, BTC_SYMBOL, '4h', 300)
    btc_data_1h = fetch_ohlcv_data(exchange, BTC_SYMBOL, '1h', 300)
    if btc_data_1h is None or btc_data_4h is None:
        print('CẢNH BÁO: Không thể lấy dữ liệu BTC, phân tích RS sẽ bị bỏ qua.')
        btc_data_4h, btc_data_1h = (pd.DataFrame(), pd.DataFrame())
    results, total_pairs = ([], len(pairs_to_analyze))
    for i, pair in enumerate(pairs_to_analyze):
        print(f'  Đánh giá lại (Bộ nhớ): {pair:<15} ({i + 1}/{total_pairs})', end='\r')
        data_1w = fetch_ohlcv_data(exchange, pair, '1w', 300)
        data_1d = fetch_ohlcv_data(exchange, pair, '1d', 300)
        data_4h = fetch_ohlcv_data(exchange, pair, '4h', 300)
        data_1h = fetch_ohlcv_data(exchange, pair, '1h', 300)
        data_15m = fetch_ohlcv_data(exchange, pair, '15m', 300)
        data_5m = fetch_ohlcv_data(exchange, pair, '5m', 300)
        data_4h = add_relative_strength_data(data_4h, btc_data_4h)
        data_1h = add_relative_strength_data(data_1h, btc_data_1h)
        data_1w = calculate_indicators(data_1w)
        data_1d = calculate_indicators(data_1d)
        data_4h = calculate_indicators(data_4h)
        data_1h = calculate_indicators(data_1h)
        data_15m = calculate_indicators(data_15m)
        data_5m = calculate_indicators(data_5m)
        if any((d is None or d.empty or len(d) < 2 for d in [data_4h, data_1h, data_15m, data_5m])):
            continue
        ticker_info = tickers.get(pair)
        current_price = ticker_info.get('last') if ticker_info else None
        recommendation = analyze_and_score(pair, data_1w, data_1d, data_4h, data_1h, data_15m, data_5m, market_context, current_price, minimum_score=1)
        if recommendation:
            results.append(recommendation)
    print("\nĐánh giá lại 'Bộ nhớ' hoàn tất." + ' ' * 40)
    return results

def _evaluate_15m_health(pair: str, data_15m: pd.DataFrame) -> Optional[Dict[str, Any]]:
    if data_15m is None or data_15m.empty or len(data_15m) < 50:
        return None
    if 'ma_trend' not in data_15m.columns:
        data_15m = calculate_indicators(data_15m)
        if data_15m is None:
            return None
    last = data_15m.iloc[-1]
    cond_price_above_ma = last['close'] > last['ma_trend']
    cond_ma_rising = last['ma_trend_rising']
    cond_adx_trending = last['adx'] > 20 and last['plus_di'] > last['minus_di']
    cond_rsi_healthy = last['rsi'] > 45
    cond_bearish_engulfing = last['cdl_engulfing'] == -100
    cond_high_volume_dump = last['close'] < last['open'] and last['volume'] > last['vol_ma_20'] * 2.0
    if cond_price_above_ma and cond_ma_rising and cond_adx_trending and cond_rsi_healthy:
        if cond_bearish_engulfing or cond_high_volume_dump:
            return {'pair': pair, 'status': 'Weak', 'reason': 'Cấu trúc tăng giá tốt nhưng xuất hiện nến giảm mạnh.'}
        return {'pair': pair, 'status': 'Good', 'reason': f'Giá trên MA dốc lên, ADX {last['adx']:.0f} xác nhận xu hướng tăng.'}
    else:
        reasons = []
        if not cond_price_above_ma:
            reasons.append('giá dưới MA')
        if not cond_ma_rising:
            reasons.append('MA đi ngang/giảm')
        if not cond_adx_trending:
            reasons.append(f'ADX yếu ({last['adx']:.0f})')
        if not cond_rsi_healthy:
            reasons.append(f'RSI yếu ({last['rsi']:.0f})')
        return {'pair': pair, 'status': 'Weak', 'reason': f'Cấu trúc suy yếu: {', '.join(reasons)}.'}

def analyze_open_trades(open_trade_pairs: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
    if not open_trade_pairs:
        return {}
    print(f'\n--- Bắt đầu đánh giá tình trạng 15m của {len(open_trade_pairs)} lệnh đang mở ---')
    exchange = initialize_exchange(EXCHANGE)
    if not exchange:
        return {pair: {'status': 'Weak', 'reason': 'Lỗi kết nối sàn.'} for pair in open_trade_pairs}
    analysis_results, total_pairs = ({}, len(open_trade_pairs))
    for i, pair in enumerate(open_trade_pairs):
        print(f'  Đánh giá (Lệnh mở 15m): {pair:<15} ({i + 1}/{total_pairs})', end='\r')
        data_15m = fetch_ohlcv_data(exchange, pair, '15m', 300)
        if data_15m is None or len(data_15m) < 100:
            analysis_results[pair] = {'status': 'Weak', 'reason': 'Không đủ dữ liệu 15m.'}
            continue
        data_15m = calculate_indicators(data_15m)
        health_assessment = _evaluate_15m_health(pair, data_15m)
        analysis_results[pair] = health_assessment
    print('\nĐánh giá lệnh đang mở hoàn tất.' + ' ' * 40)
    return analysis_results

def analyze_15m_warhorse_potential(df_15m: pd.DataFrame) -> Dict[str, Any]:
    if df_15m is None or len(df_15m) < 100:
        return {'is_warhorse': False, 'score': 0, 'reason': ''}
    if 'ema_200' not in df_15m.columns or 'vol_ma_20' not in df_15m.columns:
        return {'is_warhorse': False, 'score': 0, 'reason': ''}
    last_15m = df_15m.iloc[-1]
    prev_15m = df_15m.iloc[-2]
    is_perfect_ema_order = last_15m['close'] > last_15m['ema_21'] > last_15m['ema_50'] > last_15m['ema_200']
    is_ema_rising = last_15m['ema_50'] > prev_15m['ema_50']
    if not (is_perfect_ema_order and is_ema_rising):
        return {'is_warhorse': False, 'score': 0, 'reason': ''}
    score = 20
    reasons = ['Cấu trúc EMA 15m hoàn hảo']
    if last_15m['rsi'] > 58:
        score += 10
        reasons.append(f'RSI mạnh ({last_15m['rsi']:.0f})')
    if last_15m['adx'] > 23:
        score += 10
        reasons.append(f'ADX xác nhận trend ({last_15m['adx']:.0f})')
    df_15m['vol_ma_100'] = ta.SMA(df_15m['volume'], timeperiod=100)
    if not df_15m['vol_ma_100'].empty and last_15m['vol_ma_20'] > df_15m['vol_ma_100'].iloc[-1] * 1.2:
        score += 15
        reasons.append('Dòng tiền đang vào')
    recent_50_candles = df_15m.tail(50)
    green_candles_ratio = (recent_50_candles['close'] > recent_50_candles['open']).sum() / 50
    if green_candles_ratio > 0.6:
        score += 15
        reasons.append(f'Mua áp đảo ({green_candles_ratio * 100:.0f}% nến xanh)')
    if score > 30:
        return {'is_warhorse': True, 'score': score, 'reason': ' | '.join(reasons)}
    return {'is_warhorse': False, 'score': 0, 'reason': ''}

def _find_significant_swing_low(data: pd.DataFrame, lookback: int=20) -> Optional[float]:
    """Tìm điểm Swing Low quan trọng gần nhất."""
    df = data.tail(lookback).copy()
    if len(df) < 5:
        return None
    try:
        from scipy.signal import find_peaks
        troughs, _ = find_peaks(-df['low'], distance=3, width=1)
        if len(troughs) > 0:
            return df['low'].iloc[troughs[-1]]
    except (ImportError, Exception):
        pass
    df['swing_low'] = (df['low'] < df['low'].shift(1)) & (df['low'] < df['low'].shift(2)) & (df['low'] < df['low'].shift(-1)) & (df['low'] < df['low'].shift(-2))
    significant_lows = df[df['swing_low']]['low']
    if not significant_lows.empty:
        return significant_lows.iloc[-1]
    return df['low'].min()

def _find_nearest_resistance(entry_price: float, data_1h: pd.DataFrame, data_4h: pd.DataFrame) -> float:
    """Tìm vùng kháng cự đáng tin cậy gần nhất."""
    resistances = []
    recent_data_1h = data_1h.tail(150)
    highs_above_entry = recent_data_1h[recent_data_1h['high'] > entry_price * 1.005]['high']
    if not highs_above_entry.empty:
        s = highs_above_entry.sort_values()
        clusters = s[s.diff() < entry_price * 0.005]
        if not clusters.empty:
            resistances.append(clusters.mean())
        else:
            resistances.append(highs_above_entry.min())
    recent_data_4h = data_4h.tail(100)
    potential_resistances_4h = recent_data_4h[recent_data_4h['high'] > entry_price * 1.005]['high']
    if not potential_resistances_4h.empty:
        resistances.append(potential_resistances_4h.min())
    return min(resistances) if resistances else float('inf')

def _assess_reversal_context(*args, **kwargs):
    """Hàm "Cảm Biến Thị Trường" để phân biệt giữa Bán Tháo Hoảng Loạn và Điều Chỉnh Thông Thường.

Phân tích 'lookback' nến gần nhất để đánh giá bối cảnh của một tín hiệu đảo chiều.

Returns:
    Một tuple chứa (context_type, reason_string).
    context_type có thể là: "PANIC_SELL", "SHARP_CORRECTION", "NORMAL_CORRECTION"."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def calculate_trade_parameters(*args, **kwargs):
    """Hàm tính toán tham số giao dịch v12.2 - Sửa lỗi logic SL > Entry.

CẬP NHẬT:
- Sửa lỗi logic tính SL cho chiến lược Breakout/Squeeze. Thay vì đặt SL ở
  trung điểm của vùng tích lũy, giờ đây SL sẽ được đặt một cách an toàn
  BÊN DƯỚI đáy của vùng tích lũy (consolidation_low), đảm bảo SL
  luôn thấp hơn Entry.
- Tinh chỉnh logic SL cho Trending-Pullback để đảm bảo nó luôn nằm dưới
  các mức hỗ trợ quan trọng."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def format_15m_trade_status_telegram(trade_analysis: Dict[str, Optional[Dict[str, Any]]]) -> str:
    import html
    timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    message = f'📡 <b>Báo Cáo Giám Sát Lệnh (15m)</b> 📡\n<i>{timestamp}</i>\n\n'
    if not trade_analysis:
        message += '<i>- Không có lệnh nào đang mở để giám sát.</i>\n'
        return message
    good_trades, weak_trades, unknown_trades = ([], [], [])
    stance_emojis = {'TẤN CÔNG': '⚔️', 'PHÒNG THỦ': '🛡️', 'TIÊU CHUẨN': '⚖️'}
    for pair, analysis in trade_analysis.items():
        pair_safe = html.escape(pair)
        if not analysis or 'status' not in analysis:
            unknown_trades.append(pair_safe)
            continue
        status = analysis.get('status')
        reason = html.escape(analysis.get('reason', 'Không rõ lý do.'))
        open_rate = analysis.get('open_rate', 0.0)
        current_price = analysis.get('current_rate')
        sl = analysis.get('sl')
        tp1 = analysis.get('tp1')
        tp2 = analysis.get('tp2')
        stance = analysis.get('tactical_stance', 'TIÊU CHUẨN')
        stance_emoji = stance_emojis.get(stance, '⚙️')
        profit_emoji = '⚪'
        profit_str = 'N/A'
        if current_price and open_rate and (open_rate > 0):
            profit_pct = (current_price - open_rate) / open_rate * 100
            profit_abs = current_price - open_rate
            if profit_pct > 0.05:
                profit_emoji = '🟢'
            elif profit_pct < -0.05:
                profit_emoji = '🔴'
            if abs(profit_abs) > 1:
                abs_decimals = 2
            elif abs(profit_abs) > 0.1:
                abs_decimals = 4
            else:
                abs_decimals = 6
            profit_str = f'{profit_pct:+.2f}% ({profit_abs:+.{abs_decimals}f}$)'
        else:
            profit_pct_raw = analysis.get('profit_pct', 0.0) * 100
            if profit_pct_raw > 0:
                profit_emoji = '🟢'
            elif profit_pct_raw < 0:
                profit_emoji = '🔴'
            profit_str = f'{profit_pct_raw:+.2f}% (API)'
        price_for_decimal_check = open_rate or current_price or 0.0
        if price_for_decimal_check > 100:
            decimals = 2
        elif price_for_decimal_check > 10:
            decimals = 3
        elif price_for_decimal_check > 0.1:
            decimals = 4
        else:
            decimals = 6
        entry_price_str = f'{open_rate:.{decimals}f}'
        current_price_str = f'{current_price:.{decimals}f}' if current_price else 'N/A'
        trade_line = ''
        if status == 'Good':
            trade_line += f'✅ <code>{pair_safe:<12}</code> <b>TỐT</b> ({stance} {stance_emoji})\n'
        elif status == 'Weak':
            trade_line += f'⚠️ <code>{pair_safe:<12}</code> <b>SUY YẾU</b> ({stance} {stance_emoji})\n'
        trade_line += f'   - <b>Lãi/Lỗ: {profit_emoji} {profit_str}</b>\n   - <b>Giá Mua:</b> <code>{entry_price_str}</code> | <b>Hiện tại:</b> <code>{current_price_str}</code>'
        if sl and tp1 and current_price and (current_price > 0):
            sl_dist_pct = (current_price - sl) / current_price * 100
            tp1_dist_pct = (tp1 - current_price) / current_price * 100
            sl_str = f'{sl:.{decimals}f}'
            tp1_str = f'{tp1:.{decimals}f}'
            plan_line = f'\n   - <b>Kế Hoạch:</b> 🛡️ SL <code>{sl_str}</code> (cách {sl_dist_pct:.1f}%) | 🎯 TP1 <code>{tp1_str}</code> (cần {tp1_dist_pct:.1f}%)'
            if tp2 and tp2 > tp1:
                tp2_dist_pct = (tp2 - current_price) / current_price * 100
                tp2_str = f'{tp2:.{decimals}f}'
                plan_line += f' | 🚀 TP2 <code>{tp2_str}</code> (cần {tp2_dist_pct:.1f}%)'
            trade_line += plan_line
        assessment_text = f'<i>Đánh giá: {reason}</i>'
        if status == 'Weak':
            assessment_text += ' <b>Cân nhắc dời SL!</b>'
        trade_line += f'\n   - {assessment_text}'
        if status == 'Good':
            good_trades.append(trade_line)
        elif status == 'Weak':
            weak_trades.append(trade_line)
        else:
            unknown_trades.append(pair_safe)
    if good_trades:
        message += '<b><u>👍 Lệnh Trạng Thái Tốt:</u></b>\n' + '\n\n'.join(good_trades) + '\n\n'
    if weak_trades:
        message += '<b><u>🚨 Lệnh Cần Chú Ý (Suy Yếu):</u></b>\n' + '\n\n'.join(weak_trades) + '\n\n'
    if unknown_trades:
        message += '<b><u>❓ Lệnh Không Thể Đánh Giá:</u></b>\n' + '<code>' + ', '.join(unknown_trades) + '</code>\n'
    message += '\n<i>(Đây là báo cáo tự động từ Tổ Giám Sát 15m)</i>'
    return message

def generate_plan_for_unmanaged_trade(*args, **kwargs):
    """Hàm chuyên dụng để phân tích và tạo kế hoạch cho một lệnh đã được mở thủ công.
Phiên bản 2.1: Tích hợp cơ chế Fallback để luôn tạo kế hoạch ngay cả khi không có setup lý tưởng.
- Nếu bộ phân tích chính không tìm thấy chiến lược, nó sẽ chuyển sang chế độ dự phòng,
  sử dụng cấu trúc thị trường cơ bản (swing low) để đề xuất SL và tính TP tương ứng."""
    '[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been \nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------'
    pass

def main():
    print(f'--- Cố Vấn Tác Chiến v5.1 (Chạy thủ công) ---')
    print('\n\n--- [TEST] CHỨC NĂNG QUÉT TOÀN DIỆN (HÀNG GIỜ) ---')
    print(f'Bắt đầu quét trên sàn {EXCHANGE} lúc {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}')
    scan_data = run_scan()
    sorted_results = scan_data.get('recommendations', [])
    print('\n\n--- KẾT QUẢ QUÉT THỊ TRƯỜNG & DỰ BÁO TÁC CHIẾN ---')
    if not sorted_results:
        print('Không phát hiện mục tiêu tiềm năng nào cho các chiến lược đã chọn tại thời điểm này.')
        return
    emoji_map = {'Instant-Explosion': '💥', 'Breakout-Pre': '⏳', 'Reversal-Scout': '🎯', 'Trending-Pullback': '🌊', '15m-Warhorse': '🐴', 'Long-Term-Squeeze': '💎'}
    print(f'\nTop {TOP_N_RESULTS} mục tiêu có điểm cao nhất:\n')
    for i, res in enumerate(sorted_results[:TOP_N_RESULTS]):
        rank, pair, score = (i + 1, res['pair'], res['final_score'])
        strategy = res.get('strategy_type', 'N/A')
        emoji = emoji_map.get(strategy, '🔹')
        reason = res.get('reason', 'Không có lý do.')
        print(f'--- Hạng {rank}: {emoji} {pair} | Điểm: {score:.0f} | Chiến lược: {strategy} ---')
        prob_check = res.get('probability_check')
        if prob_check:
            print(f'  [Xác Suất Thắng]: {prob_check.get('probability_percent', 0):.1f}% ({prob_check.get('verdict', 'N/A')})')
        print(f'  [Lý do]: {reason}')
        if res.get('current_price'):
            print(f'  [Giá Hiện Tại]: {res['current_price']}')
        if 'entry' in res and 'sl' in res and ('tp1' in res) and ('tp2' in res):
            entry, sl, tp1, tp2 = (res['entry'], res['sl'], res['tp1'], res['tp2'])
            if entry > 10:
                decimals = 3
            elif entry > 0.1:
                decimals = 4
            else:
                decimals = 6
            risk = entry - sl
            if risk > 0:
                rr1, rr2 = ((tp1 - entry) / risk, (tp2 - entry) / risk)
                print(f'  [Kế Hoạch]: Mua: {entry:.{decimals}f} | SL: {sl:.{decimals}f} | TP1: {tp1:.{decimals}f} (R:R ~1:{rr1:.1f}) | TP2: {tp2:.{decimals}f} (R:R ~1:{rr2:.1f})')
        else:
            print('  [Kế Hoạch]: Không có tham số giao dịch được đề xuất.')
        print('-' * 80)
if __name__ == '__main__':
    main()