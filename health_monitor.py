# --- START OF FILE health_monitor.py ---

# health_monitor.py (v1.5 - Tối ưu cho Server, Tự động Reboot định kỳ)
# Phiên bản này bổ sung tính năng tự động khởi động lại toàn bộ hệ thống
# sau một khoảng thời gian hoạt động nhất định (mặc định là 7 ngày) để
# đảm bảo sự ổn định lâu dài.
import logging
import os
import subprocess
import time

import psutil  # Cần cài đặt: sudo apt install python3-psutil
import requests


# --- CẤU HÌNH ---
# Ngưỡng sử dụng RAM. Nếu vượt quá, hệ thống sẽ bị khởi động lại.
RAM_THRESHOLD_PERCENT = 90.0

# Thời gian (giây) giữa các lần kiểm tra.
CHECK_INTERVAL_SECONDS = 300  # 5 phút

# Số lần kiểm tra API Freqtrade thất bại liên tiếp trước khi quyết định khởi động lại các dịch vụ.
API_FAILURE_THRESHOLD_COUNT = 3

# >>> TÍNH NĂNG MỚI: TỰ ĐỘNG KHỞI ĐỘNG LẠI ĐỊNH KỲ <<<
# Số ngày hoạt động liên tục trước khi hệ thống tự động khởi động lại.
# Điều này giúp làm mới hệ thống, giải phóng RAM và tránh các lỗi tiềm ẩn.
REBOOT_INTERVAL_DAYS = 7.0

# --- CẤU HÌNH API FREQTRADE ---
FREQTRADE_API_BASE_URL = "http://127.0.0.1:8080"
FREQTRADE_API_ENDPOINT = "/api/v1/ping"
API_TIMEOUT_SECONDS = 15  # Tăng timeout lên một chút

# --- THIẾT LẬP LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (HealthMonitor) %(message)s",
    handlers=[logging.FileHandler("health_monitor.log"), logging.StreamHandler()],
)

# --- BIẾN TOÀN CỤC ĐỂ ĐẾM LỖI ---
api_failure_count = 0


def check_uptime_and_schedule_reboot() -> bool:
    """
    Kiểm tra thời gian hoạt động của hệ thống (uptime).
    Trả về True nếu thời gian hoạt động trong giới hạn, False nếu đã đến lúc cần khởi động lại.
    """
    try:
        boot_time_timestamp = psutil.boot_time()
        uptime_seconds = time.time() - boot_time_timestamp
        uptime_days = uptime_seconds / (24 * 60 * 60)

        logging.info(
            f"Kiểm tra Uptime: Hệ thống đã hoạt động được {uptime_days:.2f} / {REBOOT_INTERVAL_DAYS} ngày."
        )

        if uptime_days >= REBOOT_INTERVAL_DAYS:
            logging.critical(
                f"!!! HỆ THỐNG ĐÃ ĐẠT ĐẾN NGƯỠNG THỜI GIAN HOẠT ĐỘNG ({uptime_days:.2f} >= {REBOOT_INTERVAL_DAYS} ngày) !!!"
            )
            return False  # Báo hiệu cần khởi động lại
        return True  # Thời gian hoạt động vẫn trong giới hạn
    except Exception as e:
        logging.error(f"Lỗi khi kiểm tra uptime hệ thống: {e}")
        return True  # Giả sử an toàn nếu không thể kiểm tra


def check_ram_usage() -> bool:
    """Kiểm tra tỷ lệ sử dụng RAM. Trả về True nếu an toàn, False nếu quá tải."""
    ram_percent = psutil.virtual_memory().percent
    logging.info(
        f"Kiểm tra RAM: Đang sử dụng {ram_percent:.1f}% (Ngưỡng: {RAM_THRESHOLD_PERCENT}%)"
    )
    if ram_percent >= RAM_THRESHOLD_PERCENT:
        logging.critical(
            f"!!! CẢNH BÁO RAM QUÁ TẢI: {ram_percent:.1f}% > {RAM_THRESHOLD_PERCENT}% !!!"
        )
        return False
    return True


def check_freqtrade_api() -> bool:
    """
    Kiểm tra xem API của Freqtrade có đang hoạt động và phản hồi không.
    Nếu API hoạt động, điều này ngầm xác nhận rằng cả Freqtrade và kết nối mạng đều ổn.
    """
    global api_failure_count
    url = f"{FREQTRADE_API_BASE_URL}{FREQTRADE_API_ENDPOINT}"
    try:
        response = requests.get(url, timeout=API_TIMEOUT_SECONDS)
        if response.status_code == 200 and response.json().get("status") == "pong":
            logging.info("Kiểm tra API Freqtrade: API hoạt động tốt (ping -> pong).")
            api_failure_count = 0  # Reset khi thành công
            return True
        else:
            api_failure_count += 1
            logging.warning(
                f"Kiểm tra API Freqtrade: API trả về trạng thái không mong muốn. Status: {response.status_code}, Data: {response.text} "
                f"(Lỗi lần {api_failure_count}/{API_FAILURE_THRESHOLD_COUNT})"
            )
            return False

    except requests.exceptions.RequestException as e:
        # Lỗi này bao gồm cả "Connection refused" và lỗi timeout
        api_failure_count += 1
        logging.warning(
            f"Kiểm tra API Freqtrade: KHÔNG THỂ KẾT NỐI. Freqtrade có thể đã bị treo/crash hoặc mất kết nối mạng. "
            f"(Lỗi lần {api_failure_count}/{API_FAILURE_THRESHOLD_COUNT}). Chi tiết: {e}"
        )
        return False


def restart_all_services(reason: str):
    """
    Ghi lại lý do và chạy lại script setup_service.py để khởi động lại
    toàn bộ chuỗi dịch vụ một cách có trật tự.
    """
    logging.critical("=" * 60)
    logging.critical("!!! HỆ THỐNG GIÁM SÁT QUYẾT ĐỊNH KHỞI ĐỘNG LẠI CÁC DỊCH VỤ !!!")
    logging.critical(f"LÝ DO: {reason}")
    logging.critical("Hành động: Thực thi lại 'setup_service.py' để tự chữa lành.")
    logging.critical("=" * 60)

    try:
        # Chạy script setup_service với cờ --clean để đảm bảo dọn dẹp triệt để trước khi khởi động lại
        command = ["python3", "setup_service.py", "--clean"]
        logging.info(f"Đang thực thi lệnh: {' '.join(command)}")
        # Sử dụng Popen để không bị block
        subprocess.Popen(command)
        # Tạm dừng monitor trong một khoảng thời gian để các dịch vụ có thời gian khởi động lại
        logging.info("Tạm dừng Health Monitor trong 5 phút để các dịch vụ ổn định...")
        time.sleep(300)
        return
    except Exception as e:
        logging.critical(
            f"LỖI NGHIÊM TRỌNG khi cố gắng chạy lại setup_service.py: {e}", exc_info=True
        )
        time.sleep(300)


def reboot_system(reason: str):
    """Ghi lại lý do và thực hiện lệnh khởi động lại TOÀN BỘ HỆ THỐNG."""
    logging.critical("=" * 60)
    logging.critical("!!! HỆ THỐNG GIÁM SÁT QUYẾT ĐỊNH KHỞI ĐỘNG LẠI MÁY !!!")
    logging.critical(f"LÝ DO: {reason}")
    logging.critical(f"Hành động sẽ được thực hiện trong 15 giây...")
    logging.critical("=" * 60)
    time.sleep(15)
    os.system("reboot")


def main_monitor_loop():
    """Vòng lặp giám sát chính."""
    logging.info("=" * 60)
    logging.info("Hệ Thống Giám Sát Sức Khỏe v1.5 (Server & Auto Reboot) đã được kích hoạt.")
    logging.info(f"Kiểm tra định kỳ mỗi {CHECK_INTERVAL_SECONDS} giây.")
    logging.info(
        f"Hệ thống sẽ được tự động khởi động lại sau {REBOOT_INTERVAL_DAYS} ngày hoạt động."
    )
    logging.info("=" * 60)

    while True:
        try:
            # 1. Kiểm tra thời gian hoạt động (Ưu tiên cao nhất)
            if not check_uptime_and_schedule_reboot():
                reboot_system(f"Khởi động lại định kỳ sau {REBOOT_INTERVAL_DAYS} ngày hoạt động.")
                break  # Thoát vòng lặp để hệ thống reboot

            # 2. Kiểm tra RAM (Ưu tiên thứ hai)
            if not check_ram_usage():
                reboot_system("Sử dụng RAM vượt ngưỡng an toàn.")
                break  # Thoát vòng lặp để hệ thống reboot

            # 3. Kiểm tra API Freqtrade (chỉ số quan trọng thứ ba)
            if not check_freqtrade_api():
                if api_failure_count >= API_FAILURE_THRESHOLD_COUNT:
                    restart_all_services(
                        "API Freqtrade không phản hồi, có thể bot đã bị treo hoặc mất mạng."
                    )
                    # Không cần break, hàm restart_all_services đã có sleep

            logging.info(f"--- Hoàn tất chu kỳ kiểm tra. Nghỉ {CHECK_INTERVAL_SECONDS} giây. ---")
            time.sleep(CHECK_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            logging.info("Đã nhận tín hiệu dừng. Kết thúc giám sát.")
            break
        except Exception as e:
            logging.critical(f"LỖI KHÔNG MONG MUỐN trong vòng lặp giám sát: {e}", exc_info=True)
            time.sleep(60)


if __name__ == "__main__":
    if os.geteuid() != 0:
        logging.error("Lỗi: Script này cần quyền root để hoạt động. Vui lòng chạy với 'sudo'.")
        exit(1)

    main_monitor_loop()

# --- END OF FILE health_monitor.py ---```
