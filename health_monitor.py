import logging
import os
import subprocess
import time
import psutil
import requests
RAM_THRESHOLD_PERCENT = 90.0
CHECK_INTERVAL_SECONDS = 300
API_FAILURE_THRESHOLD_COUNT = 3
REBOOT_INTERVAL_DAYS = 7.0
FREQTRADE_API_BASE_URL = 'http://127.0.0.1:8080'
FREQTRADE_API_ENDPOINT = '/api/v1/ping'
API_TIMEOUT_SECONDS = 15
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] (HealthMonitor) %(message)s', handlers=[logging.FileHandler('health_monitor.log'), logging.StreamHandler()])
api_failure_count = 0

def check_uptime_and_schedule_reboot() -> bool:
    """Check system uptime (uptime).
Returns True if the uptime is within the limit, False if it's time to reboot."""
    try:
        boot_time_timestamp = psutil.boot_time()
        uptime_seconds = time.time() - boot_time_timestamp
        uptime_days = uptime_seconds / (24 * 60 * 60)
        logging.info(f'Kiểm tra Uptime: Hệ thống đã hoạt động được {uptime_days:.2f} / {REBOOT_INTERVAL_DAYS} ngày.')
        if uptime_days >= REBOOT_INTERVAL_DAYS:
            logging.critical(f'!!! HỆ THỐNG ĐÃ ĐẠT ĐẾN NGƯỠNG THỜI GIAN HOẠT ĐỘNG ({uptime_days:.2f} >= {REBOOT_INTERVAL_DAYS} ngày) !!!')
            return False
        return True
    except Exception as e:
        logging.error(f'Lỗi khi kiểm tra uptime hệ thống: {e}')
        return True

def check_ram_usage() -> bool:
    """Check RAM usage rate. Returns True if safe, False if overloaded."""
    ram_percent = psutil.virtual_memory().percent
    logging.info(f'Kiểm tra RAM: Đang sử dụng {ram_percent:.1f}% (Ngưỡng: {RAM_THRESHOLD_PERCENT}%)')
    if ram_percent >= RAM_THRESHOLD_PERCENT:
        logging.critical(f'!!! CẢNH BÁO RAM QUÁ TẢI: {ram_percent:.1f}% > {RAM_THRESHOLD_PERCENT}% !!!')
        return False
    return True

def check_freqtrade_api() -> bool:
    """Check if Freqtrade's API is active and responding.
If the API works, this implicitly confirms that both Freqtrade and the network connection are fine."""
    global api_failure_count
    url = f'{FREQTRADE_API_BASE_URL}{FREQTRADE_API_ENDPOINT}'
    try:
        response = requests.get(url, timeout=API_TIMEOUT_SECONDS)
        if response.status_code == 200 and response.json().get('status') == 'pong':
            logging.info('Kiểm tra API Freqtrade: API hoạt động tốt (ping -> pong).')
            api_failure_count = 0
            return True
        else:
            api_failure_count += 1
            logging.warning(f'Kiểm tra API Freqtrade: API trả về trạng thái không mong muốn. Status: {response.status_code}, Data: {response.text} (Lỗi lần {api_failure_count}/{API_FAILURE_THRESHOLD_COUNT})')
            return False
    except requests.exceptions.RequestException as e:
        api_failure_count += 1
        logging.warning(f'Kiểm tra API Freqtrade: KHÔNG THỂ KẾT NỐI. Freqtrade có thể đã bị treo/crash hoặc mất kết nối mạng. (Lỗi lần {api_failure_count}/{API_FAILURE_THRESHOLD_COUNT}). Chi tiết: {e}')
        return False

def restart_all_services(reason: str):
    """Note the reason and rerun the setup_service.py script to reboot
entire service chain in an orderly manner."""
    logging.critical('=' * 60)
    logging.critical('!!! HỆ THỐNG GIÁM SÁT QUYẾT ĐỊNH KHỞI ĐỘNG LẠI CÁC DỊCH VỤ !!!')
    logging.critical(f'LÝ DO: {reason}')
    logging.critical("Hành động: Thực thi lại 'setup_service.py' để tự chữa lành.")
    logging.critical('=' * 60)
    try:
        command = ['python3', 'setup_service.py', '--clean']
        logging.info(f'Đang thực thi lệnh: {' '.join(command)}')
        subprocess.Popen(command)
        logging.info('Tạm dừng Health Monitor trong 5 phút để các dịch vụ ổn định...')
        time.sleep(300)
        return
    except Exception as e:
        logging.critical(f'LỖI NGHIÊM TRỌNG khi cố gắng chạy lại setup_service.py: {e}', exc_info=True)
        time.sleep(300)

def reboot_system(reason: str):
    """Note down the reason and execute the FULL SYSTEM reboot command."""
    logging.critical('=' * 60)
    logging.critical('!!! HỆ THỐNG GIÁM SÁT QUYẾT ĐỊNH KHỞI ĐỘNG LẠI MÁY !!!')
    logging.critical(f'LÝ DO: {reason}')
    logging.critical(f'Hành động sẽ được thực hiện trong 15 giây...')
    logging.critical('=' * 60)
    time.sleep(15)
    os.system('reboot')

def main_monitor_loop():
    """Main monitoring loop."""
    logging.info('=' * 60)
    logging.info('Hệ Thống Giám Sát Sức Khỏe v1.5 (Server & Auto Reboot) đã được kích hoạt.')
    logging.info(f'Kiểm tra định kỳ mỗi {CHECK_INTERVAL_SECONDS} giây.')
    logging.info(f'Hệ thống sẽ được tự động khởi động lại sau {REBOOT_INTERVAL_DAYS} ngày hoạt động.')
    logging.info('=' * 60)
    while True:
        try:
            if not check_uptime_and_schedule_reboot():
                reboot_system(f'Khởi động lại định kỳ sau {REBOOT_INTERVAL_DAYS} ngày hoạt động.')
                break
            if not check_ram_usage():
                reboot_system('Sử dụng RAM vượt ngưỡng an toàn.')
                break
            if not check_freqtrade_api():
                if api_failure_count >= API_FAILURE_THRESHOLD_COUNT:
                    restart_all_services('API Freqtrade không phản hồi, có thể bot đã bị treo hoặc mất mạng.')
            logging.info(f'--- Hoàn tất chu kỳ kiểm tra. Nghỉ {CHECK_INTERVAL_SECONDS} giây. ---')
            time.sleep(CHECK_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logging.info('Đã nhận tín hiệu dừng. Kết thúc giám sát.')
            break
        except Exception as e:
            logging.critical(f'LỖI KHÔNG MONG MUỐN trong vòng lặp giám sát: {e}', exc_info=True)
            time.sleep(60)
if __name__ == '__main__':
    if os.geteuid() != 0:
        logging.error("Lỗi: Script này cần quyền root để hoạt động. Vui lòng chạy với 'sudo'.")
        exit(1)
    main_monitor_loop()