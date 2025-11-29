#!/bin/bash
# Script này được tạo tự động bởi setup_service.py v3.2
# Nó sẽ thay đổi địa chỉ MAC và kết nối lại mạng Wifi khi khởi động.
set -e # Thoát ngay nếu có lỗi

echo "--- [MAC Changer] Bắt đầu quy trình làm mới mạng ---"

# Kiểm tra các lệnh cần thiết
command -v nmcli >/dev/null 2>&1 || { echo >&2 "Lỗi: Lệnh 'nmcli' không tồn tại. Vui lòng cài đặt network-manager."; exit 1; }
command -v macchanger >/dev/null 2>&1 || { echo >&2 "Lỗi: Lệnh 'macchanger' không tồn tại. Vui lòng cài đặt (sudo apt install macchanger)."; exit 1; }

echo "[1/7] Ngắt kết nối wifi 'CAFE THANH CONG'..."
nmcli con down "CAFE THANH CONG" || echo "   -> Cảnh báo: Không thể ngắt kết nối. Có thể nó chưa được kết nối."

echo "[2/7] Tắt card mạng 'wlp3s0'..."
ip link set wlp3s0 down
echo "   -> Đã tắt wlp3s0."

echo "[3/7] Đổi địa chỉ MAC ngẫu nhiên cho 'wlp3s0'..."
macchanger -r wlp3s0

echo "[4/7] Bật lại card mạng 'wlp3s0'..."
ip link set wlp3s0 up
echo "   -> Đã bật wlp3s0."

echo "[5/7] Chờ 5 giây để card mạng sẵn sàng..."
sleep 5

echo "[6/7] Kết nối lại wifi 'CAFE THANH CONG'..."
nmcli con up "CAFE THANH CONG"
echo "   -> Đã gửi lệnh kết nối tới 'CAFE THANH CONG'."

echo "[7/7] Chờ 10 giây để kết nối ổn định..."
sleep 10

echo "--- [MAC Changer] Hoàn tất quy trình làm mới mạng ---"
