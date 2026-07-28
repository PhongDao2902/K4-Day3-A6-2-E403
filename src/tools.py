"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)
ĐỀ TÀI 5: TRỢ LÝ TRA CỨU ĐƠN HÀNG & XỬ LÝ ĐỔI TRẢ

Kiến trúc 3 tầng tool:
  Tầng 1 - READ  : get_order_status, get_shipping_info      (tra cứu dữ liệu)
  Tầng 2 - RULE  : check_return_policy, calculate_refund    (kiểm tra quy tắc nghiệp vụ)
  Tầng 3 - WRITE : create_return_request                    (hành động có hậu quả thật)

QUY ƯỚC BẮT BUỘC (Guardrail cấp Tool):
   - Mọi tool đều trả về kiểu `str` và KHÔNG BAO GIỜ raise exception,
     để vòng lặp ReAct trong app.py không bị crash giữa chừng.
   - Khi thất bại, tool trả về chuỗi bắt đầu bằng "LỖI:" hoặc "TỪ CHỐI:"
     để Agent nhận biết và tự điều chỉnh hành động tiếp theo.
"""

def get_order_status(order_id: str) -> str:
    """
    Tra cứu thông tin và trạng thái của một đơn hàng.

    Args:
        order_id (str): Mã đơn hàng, định dạng DHyyyymmdd (Ví dụ: 'DH20260715')

    Returns:
        str: Sản phẩm, ngành hàng, giá tiền, ngày đặt, ngày giao, số ngày kể từ khi giao.
             Trả về chuỗi bắt đầu bằng 'LỖI:' nếu không tìm thấy đơn.
    """
   


def get_shipping_info(order_id: str) -> str:
    """
    Tra cứu vị trí kiện hàng và thời gian giao dự kiến của đơn đang vận chuyển.

    Args:
        order_id (str): Mã đơn hàng (Ví dụ: 'DH20260801')

    Returns:
        str: Vị trí hiện tại, đơn vị vận chuyển, ngày giao dự kiến.
             Trả về 'LỖI:' nếu đơn không tồn tại hoặc đã giao xong.
    """
    


# ==========================================================================================
# TẦNG 2 — RULE (Kiểm tra quy tắc nghiệp vụ)
# ==========================================================================================

def check_return_policy(product_category: str, days_since_delivery: str) -> str:
    """
    Đối chiếu chính sách đổi trả theo ngành hàng và số ngày kể từ khi giao hàng.
    ⚠️ Đây là tool BẮT BUỘC phải gọi trước khi tạo yêu cầu đổi trả.

    Args:
        product_category (str): Ngành hàng ('giày dép', 'thời trang', 'điện tử', 'đồ lót', 'thực phẩm')
        days_since_delivery (str): Số ngày kể từ khi giao hàng (Ví dụ: '8')

    Returns:
        str: Bắt đầu bằng 'ĐỦ ĐIỀU KIỆN:' nếu được phép đổi trả,
             'TỪ CHỐI:' nếu quá hạn hoặc ngành hàng không áp dụng,
             'LỖI:' nếu tham số không hợp lệ.
    """
   

def calculate_refund(order_id: str, return_type: str) -> str:
    """
    Tính số tiền khách thực nhận khi đổi trả (đã trừ phí ship chiều về và voucher đã dùng).

    Args:
        order_id (str): Mã đơn hàng (Ví dụ: 'DH20260715')
        return_type (str): Loại yêu cầu — 'đổi size', 'hoàn tiền' hoặc 'đổi sản phẩm khác'

    Returns:
        str: Chi tiết cách tính và số tiền thực nhận, hoặc chuỗi 'LỖI:' nếu tham số sai.
    """
    

# ==========================================================================================
# TẦNG 3 — WRITE (Hành động có hậu quả thật)
# ==========================================================================================

def create_return_request(order_id: str, reason: str) -> str:
    """
    Tạo yêu cầu đổi/trả hàng và sinh mã RMA.
    🛡️ CHỈ ĐƯỢC GỌI SAU KHI check_return_policy trả về 'ĐỦ ĐIỀU KIỆN'.

    Args:
        order_id (str): Mã đơn hàng (Ví dụ: 'DH20260715')
        reason (str): Lý do đổi trả (Ví dụ: 'sai size', 'lỗi kỹ thuật', 'không đúng mô tả')

    Returns:
        str: Mã RMA và hướng dẫn tiếp theo, hoặc chuỗi 'LỖI:' nếu không thể tạo.
    """
    


# Danh sách các tool được đăng ký để Agent sử dụng
AVAILABLE_TOOLS = {
    "get_order_status": get_order_status,
    "get_shipping_info": get_shipping_info,
    "check_return_policy": check_return_policy,
    "calculate_refund": calculate_refund,
    "create_return_request": create_return_request,
}



