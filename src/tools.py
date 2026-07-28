"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)📦 ĐỀ TÀI 5: TRỢ LÝ TRA CỨU ĐƠN HÀNG & XỬ LÝ ĐỔI TRẢ

Kiến trúc 3 tầng tool:
  🔍 Tầng 1 - READ  : get_order_status, get_shipping_info      (tra cứu dữ liệu)
  📐 Tầng 2 - RULE  : check_return_policy, calculate_refund    (kiểm tra quy tắc nghiệp vụ)
  ✍️ Tầng 3 - WRITE : create_return_request                    (hành động có hậu quả thật)

⚠️ QUY ƯỚC BẮT BUỘC (Guardrail cấp Tool):
   - Mọi tool đều trả về kiểu `str` và KHÔNG BAO GIỜ raise exception,
     để vòng lặp ReAct trong app.py không bị crash giữa chừng.
   - Khi thất bại, tool trả về chuỗi bắt đầu bằng "LỖI:" hoặc "TỪ CHỐI:"
     để Agent nhận biết và tự điều chỉnh hành động tiếp theo.
"""

from datetime import datetime

# ==========================================================================================
# 📅 MỐC THỜI GIAN CỐ ĐỊNH
# Cố định ngày "hôm nay" để kết quả demo luôn tái lập được (không đổi theo ngày chạy máy).
# ==========================================================================================
TODAY = datetime(2026, 7, 28)


# ==========================================================================================
# 🗄️ DỮ LIỆU GIẢ LẬP (MOCK DATABASE)
# ==========================================================================================
ORDER_DB = {
    "DH20260715": {
        "product": "Giày sneaker Nike Air size 42",
        "category": "giày dép",
        "price": 1_290_000,
        "voucher_used": 100_000,
        "return_ship_fee": 30_000,
        "order_date": "15/07/2026",
        "delivered_date": "20/07/2026",
        "status": "Đã giao thành công",
        "carrier": "GHTK",
        "current_location": None,
        "eta": None,
        "existing_rma": None,
    },
    "DH20260801": {
        "product": "Tai nghe Bluetooth Sony WF-1000XM5",
        "category": "điện tử",
        "price": 890_000,
        "voucher_used": 0,
        "return_ship_fee": 30_000,
        "order_date": "26/07/2026",
        "delivered_date": None,
        "status": "Đang vận chuyển",
        "carrier": "GHTK",
        "current_location": "Kho phân loại Bình Dương",
        "eta": "30/07/2026",
        "existing_rma": None,
    },
    "DH20260101": {
        "product": "Áo khoác dạ nữ size M",
        "category": "thời trang",
        "price": 750_000,
        "voucher_used": 0,
        "return_ship_fee": 30_000,
        "order_date": "05/01/2026",
        "delivered_date": "10/01/2026",
        "status": "Đã giao thành công",
        "carrier": "GHN",
        "current_location": None,
        "eta": None,
        "existing_rma": None,
    },
    "DH20260710": {
        "product": "Bộ đồ lót cotton nam",
        "category": "đồ lót",
        "price": 250_000,
        "voucher_used": 0,
        "return_ship_fee": 30_000,
        "order_date": "14/07/2026",
        "delivered_date": "18/07/2026",
        "status": "Đã giao thành công",
        "carrier": "GHTK",
        "current_location": None,
        "eta": None,
        "existing_rma": None,
    },
    "DH20260720": {
        "product": "Nồi chiên không dầu Lock&Lock 5.5L",
        "category": "điện tử",
        "price": 1_890_000,
        "voucher_used": 0,
        "return_ship_fee": 50_000,
        "order_date": "20/07/2026",
        "delivered_date": "24/07/2026",
        "status": "Đã giao thành công",
        "carrier": "GHN",
        "current_location": None,
        "eta": None,
        "existing_rma": "RMA-8830",  # ⚠️ Đơn này đã có yêu cầu đang xử lý (bẫy trùng lặp)
    },
}

# 📐 Chính sách đổi trả theo ngành hàng: số ngày tối đa kể từ khi giao (0 = không áp dụng)
RETURN_POLICY_DAYS = {
    "giày dép": 30,
    "thời trang": 15,
    "điện tử": 7,
    "đồ lót": 0,
    "thực phẩm": 0,
}

RETURN_POLICY_NOTE = {
    "giày dép": "còn tem mác, chưa qua sử dụng, đủ hộp phụ kiện",
    "thời trang": "còn nguyên tag, chưa giặt",
    "điện tử": "còn nguyên seal hộp, đủ phụ kiện, có video mở hộp",
}

# Các loại yêu cầu đổi trả hợp lệ
VALID_RETURN_TYPES = ["đổi size", "hoàn tiền", "đổi sản phẩm khác"]

# Bộ nhớ tạm lưu các yêu cầu RMA đã tạo trong phiên chạy
RETURN_REQUESTS = {}
_RMA_COUNTER = [8841]


def _days_since_delivery(order: dict):
    """Helper nội bộ: tính số ngày kể từ ngày giao hàng. Trả về None nếu chưa giao."""
    if not order.get("delivered_date"):
        return None
    delivered = datetime.strptime(order["delivered_date"], "%d/%m/%Y")
    return (TODAY - delivered).days


# ==========================================================================================
# 🔍 TẦNG 1 — READ (Tra cứu dữ liệu)
# ==========================================================================================

def get_order_status(order_id: str) -> str:
    """
    Tra cứu thông tin và trạng thái của một đơn hàng.

    Args:
        order_id (str): Mã đơn hàng, định dạng DHyyyymmdd (Ví dụ: 'DH20260715')

    Returns:
        str: Sản phẩm, ngành hàng, giá tiền, ngày đặt, ngày giao, số ngày kể từ khi giao.
             Trả về chuỗi bắt đầu bằng 'LỖI:' nếu không tìm thấy đơn.
    """
    try:
        key = (order_id or "").strip().upper().strip("'\"")
        if not key:
            return "LỖI: Thiếu mã đơn hàng. Vui lòng cung cấp mã đơn dạng DHyyyymmdd."

        order = ORDER_DB.get(key)
        if not order:
            return (
                f"LỖI: Không tìm thấy đơn hàng '{order_id}'. "
                f"Vui lòng kiểm tra lại mã đơn (định dạng đúng: DH20260715)."
            )

        days = _days_since_delivery(order)
        days_text = f"{days} ngày" if days is not None else "Chưa giao"
        return (
            f"Đơn {key} | {order['product']} | Ngành hàng: {order['category']} | "
            f"Giá: {order['price']:,}đ | Đặt ngày {order['order_date']} | "
            f"Trạng thái: {order['status']} | "
            f"Ngày giao: {order['delivered_date'] or 'chưa giao'} | "
            f"Số ngày kể từ khi giao: {days_text}"
        )
    except Exception as e:
        return f"LỖI: Sự cố khi tra cứu đơn hàng ({e})."


def get_shipping_info(order_id: str) -> str:
    """
    Tra cứu vị trí kiện hàng và thời gian giao dự kiến của đơn đang vận chuyển.

    Args:
        order_id (str): Mã đơn hàng (Ví dụ: 'DH20260801')

    Returns:
        str: Vị trí hiện tại, đơn vị vận chuyển, ngày giao dự kiến.
             Trả về 'LỖI:' nếu đơn không tồn tại hoặc đã giao xong.
    """
    try:
        key = (order_id or "").strip().upper().strip("'\"")
        order = ORDER_DB.get(key)
        if not order:
            return f"LỖI: Không tìm thấy đơn hàng '{order_id}' trong hệ thống vận chuyển."

        if order["delivered_date"]:
            return (
                f"Đơn {key} đã giao thành công ngày {order['delivered_date']} qua {order['carrier']}. "
                f"Không còn thông tin vận chuyển đang cập nhật."
            )

        return (
            f"Đơn {key} ({order['product']}) đang ở {order['current_location']}, "
            f"vận chuyển bởi {order['carrier']}, dự kiến giao ngày {order['eta']}."
        )
    except Exception as e:
        return f"LỖI: Sự cố khi tra cứu vận chuyển ({e})."


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
    try:
        category = (product_category or "").strip().lower().strip("'\"")
        raw_days = str(days_since_delivery or "").strip().strip("'\"")

        if not raw_days.lstrip("-").isdigit():
            return (
                f"LỖI: Tham số days_since_delivery='{days_since_delivery}' không hợp lệ. "
                f"Cần truyền vào một số nguyên (Ví dụ: '8')."
            )
        days = int(raw_days)
        if days < 0:
            return "LỖI: Số ngày kể từ khi giao không thể là số âm."

        if category not in RETURN_POLICY_DAYS:
            return (
                f"LỖI: Không có chính sách cho ngành hàng '{product_category}'. "
                f"Các ngành hàng hợp lệ: {', '.join(RETURN_POLICY_DAYS.keys())}."
            )

        limit = RETURN_POLICY_DAYS[category]
        if limit == 0:
            return (
                f"TỪ CHỐI: Ngành hàng '{category}' thuộc nhóm không áp dụng đổi trả "
                f"vì lý do vệ sinh / an toàn thực phẩm."
            )
        if days > limit:
            return (
                f"TỪ CHỐI: Đã quá hạn đổi trả. Ngành hàng '{category}' chỉ được đổi trả "
                f"trong {limit} ngày, đơn này đã giao {days} ngày."
            )

        note = RETURN_POLICY_NOTE.get(category, "sản phẩm còn nguyên trạng")
        return (
            f"ĐỦ ĐIỀU KIỆN: Ngành hàng '{category}' được đổi trả trong {limit} ngày "
            f"(hiện {days} ngày). Yêu cầu: {note}."
        )
    except Exception as e:
        return f"LỖI: Sự cố khi kiểm tra chính sách ({e})."


def calculate_refund(order_id: str, return_type: str) -> str:
    """
    Tính số tiền khách thực nhận khi đổi trả (đã trừ phí ship chiều về và voucher đã dùng).

    Args:
        order_id (str): Mã đơn hàng (Ví dụ: 'DH20260715')
        return_type (str): Loại yêu cầu — 'đổi size', 'hoàn tiền' hoặc 'đổi sản phẩm khác'

    Returns:
        str: Chi tiết cách tính và số tiền thực nhận, hoặc chuỗi 'LỖI:' nếu tham số sai.
    """
    try:
        key = (order_id or "").strip().upper().strip("'\"")
        rtype = (return_type or "").strip().lower().strip("'\"")

        order = ORDER_DB.get(key)
        if not order:
            return f"LỖI: Không tìm thấy đơn hàng '{order_id}' để tính tiền hoàn."

        if rtype not in VALID_RETURN_TYPES:
            return (
                f"LỖI: return_type='{return_type}' không hợp lệ. "
                f"Chỉ chấp nhận: {', '.join(VALID_RETURN_TYPES)}."
            )

        price = order["price"]
        ship = order["return_ship_fee"]
        voucher = order["voucher_used"]

        if rtype == "đổi size":
            return (
                f"Đổi size đơn {key}: MIỄN PHÍ cho lần đổi đầu tiên "
                f"(phí ship chiều về 0đ, không hoàn tiền mặt). "
                f"Sản phẩm mới sẽ được giao trong 3-5 ngày làm việc."
            )
        if rtype == "đổi sản phẩm khác":
            return (
                f"Đổi sản phẩm khác cho đơn {key}: khách chịu phí ship chiều về {ship:,}đ. "
                f"Giá trị được quy đổi: {price:,}đ − {ship:,}đ = {price - ship:,}đ "
                f"(bù thêm nếu sản phẩm mới đắt hơn)."
            )

        refund = price - ship - voucher
        return (
            f"Hoàn tiền đơn {key}: {price:,}đ (giá gốc) − {ship:,}đ (ship chiều về) "
            f"− {voucher:,}đ (voucher đã dùng) = {refund:,}đ. "
            f"Tiền về ví trong 3-5 ngày làm việc."
        )
    except Exception as e:
        return f"LỖI: Sự cố khi tính tiền hoàn ({e})."


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
    try:
        key = (order_id or "").strip().upper().strip("'\"")
        why = (reason or "").strip().strip("'\"")

        order = ORDER_DB.get(key)
        if not order:
            return f"LỖI: Không tìm thấy đơn hàng '{order_id}' để tạo yêu cầu đổi trả."

        if not why:
            return "LỖI: Thiếu lý do đổi trả. Vui lòng hỏi khách hàng lý do cụ thể trước khi tạo yêu cầu."

        if not order["delivered_date"]:
            return (
                f"LỖI: Đơn {key} chưa được giao (đang {order['status'].lower()}). "
                f"Chỉ có thể tạo yêu cầu đổi trả sau khi nhận hàng."
            )

        if order["existing_rma"]:
            return (
                f"LỖI: Đơn {key} đã có yêu cầu {order['existing_rma']} đang xử lý. "
                f"Không thể tạo yêu cầu trùng lặp."
            )

        rma = f"RMA-{_RMA_COUNTER[0]}"
        _RMA_COUNTER[0] += 1
        order["existing_rma"] = rma
        RETURN_REQUESTS[rma] = {"order_id": key, "reason": why}

        return (
            f"Đã tạo yêu cầu {rma} cho đơn {key} ({order['product']}). Lý do: {why}. "
            f"Vui lòng đóng gói nguyên trạng kèm hóa đơn, shipper sẽ đến lấy hàng trong 2 ngày làm việc."
        )
    except Exception as e:
        return f"LỖI: Sự cố khi tạo yêu cầu đổi trả ({e})."


# Danh sách các tool được đăng ký để Agent sử dụng
AVAILABLE_TOOLS = {
    "get_order_status": get_order_status,
    "get_shipping_info": get_shipping_info,
    "check_return_policy": check_return_policy,
    "calculate_refund": calculate_refund,
    "create_return_request": create_return_request,
}
