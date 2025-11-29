# file: obscure_logic.py
import ast
import os

# --- CẤU HÌNH ---
# Dictionary chứa các file và danh sách các hàm cần ẩn logic trong mỗi file.
# Key: Đường dẫn đến file gốc (chứa logic bí mật).
# Value: Một list các tên hàm (dạng string) cần được ẩn đi.
FILES_TO_OBSCURE = {
    "ichimoku_scanner.py": [
        "analyze_and_score",
        "calculate_trade_parameters",
        "calculate_success_probability",
        "assess_short_term_health",
        "score_long_term_squeeze",
        "score_trending_pullback_setup",
        "analyze_breakout_structure",
        "generate_plan_for_unmanaged_trade"
        # Thêm bất kỳ hàm nào khác bạn muốn ẩn ở đây
    ],
    "automation_manager.py": [
        "analyze_market_state"
        # Bạn có thể thêm các hàm từ các file khác nếu muốn
    ]
}

# Đoạn văn bản sẽ được chèn vào các hàm đã bị ẩn
OBSCURED_DOCSTRING = """
[PHIÊN BẢN CÔNG KHAI]
Logic tính toán độc quyền của hàm này đã được gỡ bỏ để bảo vệ tài sản trí tuệ.
Mã nguồn trong repository này chỉ nhằm mục đích trưng bày cấu trúc và luồng hoạt động của hệ thống.
"""

class FunctionObscurer(ast.NodeTransformer):
    """
    Một NodeTransformer đi qua cây cú pháp trừu tượng (AST)
    và thay thế phần thân của các hàm được chỉ định.
    """
    def __init__(self, functions_to_hide):
        self.functions_to_hide = set(functions_to_hide)
        super().__init__()

    def visit_FunctionDef(self, node):
        # Kiểm tra xem tên của hàm có nằm trong danh sách cần ẩn không
        if node.name in self.functions_to_hide:
            print(f"    -> Đang ẩn logic của hàm: {node.name}()")
            # Tạo một phần thân (body) mới cho hàm
            new_body = [
                # Thêm docstring giải thích
                ast.Expr(value=ast.Constant(value=OBSCURED_DOCSTRING)),
                # Thêm lệnh 'pass' để hàm vẫn hợp lệ về mặt cú pháp
                ast.Pass()
            ]
            node.body = new_body
        return node

def process_file(filepath):
    """
    Đọc một file, ẩn logic của các hàm được chỉ định và ghi đè lại file đó.
    """
    if not os.path.exists(filepath):
        # Bỏ qua nếu file không tồn tại (ví dụ: file không nằm trong commit hiện tại)
        return
        
    functions_to_hide = FILES_TO_OBSCURE.get(os.path.basename(filepath))
    if not functions_to_hide:
        print(f"Không có cấu hình ẩn logic cho file: {filepath}. Bỏ qua.")
        return

    print(f"[*] Bắt đầu xử lý file: {filepath}")
    with open(filepath, 'r', encoding='utf-8') as f:
        source_code = f.read()

    # Phân tích mã nguồn thành cây AST
    tree = ast.parse(source_code)

    # Áp dụng bộ biến đổi để ẩn các hàm
    transformer = FunctionObscurer(functions_to_hide)
    new_tree = transformer.visit(tree)
    ast.fix_missing_locations(new_tree)

    # Chuyển cây AST đã sửa đổi ngược lại thành mã nguồn Python
    new_code = ast.unparse(new_tree)

    # Ghi đè file gốc với phiên bản đã được ẩn logic
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_code)
    print(f"[*] Hoàn tất xử lý file: {filepath}")


if __name__ == "__main__":
    # Phần này để bạn có thể chạy script thủ công để kiểm tra
    # Ví dụ: python obscure_logic.py ichimoku_scanner.py
    import sys
    if len(sys.argv) > 1:
        for filename in sys.argv[1:]:
            # Tạo file backup trước khi chạy thủ công
            backup_path = f"{filename}.bak"
            if not os.path.exists(backup_path):
                 os.rename(filename, backup_path)
                 print(f"Đã tạo file backup: {backup_path}")
            
            # Copy từ backup để xử lý
            import shutil
            shutil.copy(backup_path, filename)

            process_file(filename)
    else:
        print("Sử dụng: python obscure_logic.py <tên_file_1> <tên_file_2> ...")