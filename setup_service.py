import os
import shutil
import subprocess
import sys
from pathlib import Path
FREQTRADE_SERVICE_NAME = 'freqtrade'
STRATEGY_NAME = 'ExternalSignalStrategy'
CONFIG_FILE = 'config.json'
AUTOMATION_SERVICE_NAME = 'automation_manager'
AUTOMATION_SCRIPT_NAME = 'automation_manager.py'
HEALTH_MONITOR_SERVICE_NAME = 'ft_health_monitor'
HEALTH_MONITOR_SCRIPT_NAME = 'health_monitor.py'
ENABLE_MAC_CHANGER_SERVICE = False
MAC_CHANGER_SERVICE_NAME = 'mac_changer'
WIFI_SSID = ''
WIFI_INTERFACE = ''
MAC_CHANGER_SCRIPT_NAME = 'change_mac.sh'
ALL_SERVICES = [HEALTH_MONITOR_SERVICE_NAME, AUTOMATION_SERVICE_NAME, FREQTRADE_SERVICE_NAME]
if ENABLE_MAC_CHANGER_SERVICE:
    ALL_SERVICES.insert(0, MAC_CHANGER_SERVICE_NAME)

def run_command(command: list, can_fail=False):
    """Run a system command and check for errors."""
    print(f'⚡ Đang chạy: {' '.join(command)}')
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
        if result.stdout.strip():
            print(f'   -> {result.stdout.strip()}')
        return True
    except FileNotFoundError:
        print(f"❌ Lỗi: Không tìm thấy lệnh '{command[0]}'.")
        if can_fail:
            return True
        return False
    except subprocess.CalledProcessError as e:
        if can_fail:
            print(f'   -> (Bỏ qua lỗi) {e.stderr.strip()}')
            return True
        print(f'❌ Lỗi khi chạy lệnh: {' '.join(command)}')
        print(f'   -> Mã lỗi: {e.returncode}')
        print(f'   -> Stderr: {e.stderr.strip()}')
        return False
    except subprocess.TimeoutExpired:
        print(f'❌ Lỗi: Lệnh chạy quá thời gian: {' '.join(command)}')
        if can_fail:
            return True
        return False

def check_system_dependencies():
    """Check if the required Python packages for the monitor are installed on the system."""
    print('[+] Kiểm tra các gói phụ thuộc của Health Monitor...')
    try:
        import psutil
        import requests
        print("✅ 'psutil' và 'requests' đã được cài đặt trên hệ thống.")
        return True
    except ImportError as e:
        print(f'❌ Lỗi: Thiếu gói Python hệ thống: {e.name}.')
        print('   Vui lòng cài đặt nó bằng lệnh sau và chạy lại script:')
        print(f'   sudo apt-get update && sudo apt-get install python3-{e.name} -y')
        return False

def create_and_write_service_file(service_name, description, user, working_dir, exec_start, **kwargs):
    """Helper function to create content and write .service files."""
    print(f"\n[+] Tạo file dịch vụ '{service_name}.service'...")
    unit_lines = ['[Unit]', f'Description={description}', kwargs.get('after'), kwargs.get('wants')]
    unit_section = '\n'.join(filter(None, unit_lines))
    group = user if user != 'root' else 'root'
    service_lines = ['[Service]', f'Type={kwargs.get('service_type', 'simple')}', f'User={user}', f'Group={group}']
    if working_dir:
        service_lines.append(f'WorkingDirectory={working_dir}')
    if kwargs.get('exec_start_pre'):
        service_lines.append(f'ExecStartPre={kwargs.get('exec_start_pre')}')
    service_lines.append(f'ExecStart={exec_start}')
    if kwargs.get('service_type', 'simple') == 'simple':
        service_lines.extend(['Restart=on-failure', 'RestartSec=20s', 'KillSignal=SIGINT', 'StartLimitBurst=5', 'StartLimitIntervalSec=600s'])
    service_section = '\n'.join(service_lines)
    install_section = '[Install]\nWantedBy=multi-user.target'
    service_content = f'{unit_section}\n\n{service_section}\n\n{install_section}\n'
    service_path = Path(f'/etc/systemd/system/{service_name}.service')
    try:
        service_path.write_text(service_content)
        print(f'✅ Đã tạo file dịch vụ thành công tại: {service_path}')
        return True
    except IOError as e:
        print(f'❌ Lỗi khi ghi file dịch vụ: {e}')
        return False

def cleanup_services():
    """Stop, disable and delete old service files."""
    print('\n--- BƯỚC PHỤ: Dọn dẹp các dịch vụ đã cài đặt trước đó ---')
    run_command(['systemctl', 'daemon-reload'])
    for service in reversed(ALL_SERVICES):
        print(f'Dọn dẹp dịch vụ {service}...')
        run_command(['systemctl', 'stop', service], can_fail=True)
        run_command(['systemctl', 'disable', service], can_fail=True)
        service_path = Path(f'/etc/systemd/system/{service}.service')
        if service_path.exists():
            try:
                service_path.unlink()
                print(f'   -> Đã xóa file: {service_path}')
            except OSError as e:
                print(f'   -> ❌ Lỗi khi xóa file {service_path}: {e}')
    print('✅ Hoàn tất dọn dẹp.')
    return True

def main():
    """Automates the creation and activation of systemd services."""
    print('===============================================================')
    print('  TỰ ĐỘNG CÀI ĐẶT HỆ THỐNG GIAO DỊCH BỀN BỈ v3.3 (Tối ưu Server)')
    print('===============================================================')
    if '--clean' in sys.argv:
        cleanup_services()
        print('\nTiến hành cài đặt mới...')
    print('\n--- BƯỚC 1: Kiểm tra môi trường ---')
    if os.geteuid() != 0:
        print(f'❌ Lỗi: Script cần quyền root. Vui lòng chạy lại: sudo python3 {sys.argv[0]}')
        sys.exit(1)
    try:
        username = os.environ['SUDO_USER']
        print(f"✅ Bot và Cố vấn sẽ chạy với tư cách người dùng: '{username}'")
    except KeyError:
        print('❌ Lỗi: Không thể xác định người dùng gốc (SUDO_USER).')
        sys.exit(1)
    working_directory = Path.cwd().resolve()
    print(f'✅ Thư mục làm việc: {working_directory}')
    freqtrade_executable = working_directory / '.venv/bin/freqtrade'
    automation_script = working_directory / AUTOMATION_SCRIPT_NAME
    health_monitor_script = working_directory / HEALTH_MONITOR_SCRIPT_NAME
    python_executable = working_directory / '.venv/bin/python'
    required_files = {'Freqtrade executable': freqtrade_executable, 'Automation Manager script': automation_script, 'Health Monitor script': health_monitor_script}
    has_errors = False
    for name, path in required_files.items():
        if not path.is_file():
            print(f"❌ Lỗi: Không tìm thấy file '{name}' tại: {path}")
            has_errors = True
    if has_errors:
        sys.exit(1)
    print('✅ Đã xác nhận sự tồn tại của các file cần thiết.')
    if not check_system_dependencies():
        sys.exit(1)
    print('\n--- BƯỚC 2: Tạo các file cấu hình dịch vụ ---')
    ft_after = 'After=network-online.target'
    ft_wants = 'Wants=network-online.target'
    ft_exec = f'{freqtrade_executable} trade --config {CONFIG_FILE} --strategy {STRATEGY_NAME}'
    if not create_and_write_service_file(service_name=FREQTRADE_SERVICE_NAME, description='Freqtrade Trading Bot', user=username, working_dir=working_directory, exec_start=ft_exec, after=ft_after, wants=ft_wants):
        sys.exit(1)
    am_exec = f'{python_executable} {automation_script}'
    if not create_and_write_service_file(service_name=AUTOMATION_SERVICE_NAME, description='Freqtrade Automation Manager (Advisor)', user=username, working_dir=working_directory, exec_start_pre='/bin/sleep 20', exec_start=am_exec, after=f'After={FREQTRADE_SERVICE_NAME}.service', wants=f'Wants={FREQTRADE_SERVICE_NAME}.service'):
        sys.exit(1)
    system_python_path = shutil.which('python3')
    if not system_python_path:
        print("❌ Lỗi: Không tìm thấy 'python3' trên hệ thống. Không thể cài đặt Health Monitor.")
        sys.exit(1)
    hm_exec = f'{system_python_path} {health_monitor_script}'
    if not create_and_write_service_file(service_name=HEALTH_MONITOR_SERVICE_NAME, description='Freqtrade System Health Monitor & Watchdog', user='root', working_dir=working_directory, exec_start=hm_exec, after=f'After={AUTOMATION_SERVICE_NAME}.service', wants=f'Wants={AUTOMATION_SERVICE_NAME}.service'):
        sys.exit(1)
    print('\n--- BƯỚC 3: Kích hoạt và khởi động các dịch vụ ---')
    if not run_command(['systemctl', 'daemon-reload']):
        sys.exit(1)
    for service in ALL_SERVICES:
        if not run_command(['systemctl', 'enable', service]):
            sys.exit(1)
    print('\nKhởi động lại các dịch vụ theo đúng trình tự phụ thuộc...')
    if not run_command(['systemctl', 'restart', FREQTRADE_SERVICE_NAME]):
        sys.exit(1)
    if not run_command(['systemctl', 'restart', AUTOMATION_SERVICE_NAME]):
        sys.exit(1)
    if not run_command(['systemctl', 'restart', HEALTH_MONITOR_SERVICE_NAME]):
        sys.exit(1)
    print(f'✅ Đã kích hoạt và khởi động thành công {len(ALL_SERVICES)} dịch vụ.')
    print('\n--- BƯỚC 4: HOÀN TẤT! ---')
    print('===============================================================')
    print('🎉 Hệ thống Giao dịch Bền bỉ của bạn đã được thiết lập.')
    print('   Nó sẽ tự động chạy khi khởi động và tự khởi động lại khi gặp lỗi.\n')
    print('CÁC LỆNH HỮU ÍCH ĐỂ QUẢN LÝ:')
    print('---------------------------------------------------------------')
    print(f'  BOT FREQTRADE ({FREQTRADE_SERVICE_NAME}):')
    print(f'  - Trạng thái: sudo systemctl status {FREQTRADE_SERVICE_NAME}')
    print(f'  - Log:         journalctl -u {FREQTRADE_SERVICE_NAME} -f')
    print(f'\n  CỐ VẤN ({AUTOMATION_SERVICE_NAME}):')
    print(f'  - Trạng thái: sudo systemctl status {AUTOMATION_SERVICE_NAME}')
    print(f'  - Log:         journalctl -u {AUTOMATION_SERVICE_NAME} -f')
    print(f'\n  GIÁM SÁT ({HEALTH_MONITOR_SERVICE_NAME}):')
    print(f'  - Trạng thái: sudo systemctl status {HEALTH_MONITOR_SERVICE_NAME}')
    print(f'  - Log:         journalctl -u {HEALTH_MONITOR_SERVICE_NAME} -f')
    print('---------------------------------------------------------------')
    print('Để cài đặt lại toàn bộ, chạy: sudo python3 setup_service.py --clean')
if __name__ == '__main__':
    main()