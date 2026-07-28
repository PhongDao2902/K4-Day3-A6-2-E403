"""
TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)
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

import unicodedata
from datetime import date

# ==========================================================================================
# DỮ LIỆU GIẢ LẬP (Deterministic — cùng input luôn cho cùng output)
# ==========================================================================================

# Mốc thời gian cố định để bài test không đổi kết quả theo ngày chạy thật.
TODAY = date(2026, 7, 28)

# Phí ship chiều về khách phải chịu khi trả hàng (VNĐ)
RETURN_SHIPPING_FEE = 30_000

# Số ngày được phép đổi trả theo ngành hàng. Giá trị 0 = ngành hàng KHÔNG áp dụng đổi trả.
RETURN_POLICY_DAYS = {
    "giày dép": 15,
    "thời trang": 15,
    "điện tử": 7,
    "đồ gia dụng": 15,
    "đồ lót": 0,      # Không đổi trả vì lý do vệ sinh
    "thực phẩm": 0,   # Không đổi trả vì lý do an toàn thực phẩm
}

ORDERS = {
    "DH20260715": {
        "product": "Giày sneaker Nike Air Zoom - size 42",
        "category": "giày dép",
        "price": 2_500_000,
        "voucher": 200_000,
        "order_date": date(2026, 7, 10),
        "delivery_date": date(2026, 7, 15),
        "status": "Đã giao thành công",
    },
    "DH20260720": {
        "product": "Tai nghe Sony WH-1000XM5",
        "category": "điện tử",
        "price": 6_990_000,
        "voucher": 0,
        "order_date": date(2026, 7, 17),
        "delivery_date": date(2026, 7, 20),
        "status": "Đã giao thành công",
    },
    "DH20260726": {
        "product": "Bộ đồ mặc nhà cotton",
        "category": "đồ lót",
        "price": 350_000,
        "voucher": 0,
        "order_date": date(2026, 7, 23),
        "delivery_date": date(2026, 7, 26),
        "status": "Đã giao thành công",
    },
    "DH20260601": {
        "product": "Áo khoác dù unisex",
        "category": "thời trang",
        "price": 480_000,
        "voucher": 50_000,
        "order_date": date(2026, 6, 1),
        "delivery_date": date(2026, 6, 5),
        "status": "Đã giao thành công",
    },
    "DH20260801": {
        "product": 'Máy lọc không khí Xiaomi 4 Lite',
        "category": "đồ gia dụng",
        "price": 2_190_000,
        "voucher": 0,
        "order_date": date(2026, 7, 27),
        "delivery_date": None,           # Chưa giao — đang vận chuyển
        "status": "Đang vận chuyển",
        "carrier": "Giao Hàng Nhanh (GHN)",
        "location": "Kho phân loại Sóng Thần, Bình Dương",
        "eta": date(2026, 7, 30),
    },
}

# State cấp Tool: ghi nhận ngành hàng nào đã được check_return_policy xác nhận ĐỦ ĐIỀU KIỆN.
# Dùng để chặn Agent gọi thẳng tool WRITE mà bỏ qua bước kiểm tra chính sách.
_POLICY_APPROVED = set()

# Bộ đếm sinh mã RMA
_RMA_COUNTER = {"n": 0}


def reset_tool_state() -> None:
    """Xoá state giữa 2 lần chạy test case để các case không ảnh hưởng lẫn nhau."""
    _POLICY_APPROVED.clear()
    _RMA_COUNTER["n"] = 0


def _norm(text: str) -> str:
    """Chuẩn hoá chuỗi: bỏ dấu, bỏ nháy, lowercase — để khớp cả khi LLM gõ không dấu."""
    text = str(text).strip().strip("'\"").lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _find_order(order_id: str):
    """Tra đơn theo mã, chấp nhận cả chữ thường và có khoảng trắng thừa."""
    key = str(order_id).strip().strip("'\"").upper()
    return key, ORDERS.get(key)


def _money(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + " VNĐ"


def _days_since_delivery(order: dict):
    if order["delivery_date"] is None:
        return None
    return (TODAY - order["delivery_date"]).days


# ==========================================================================================
# TẦNG 1 — READ (Tra cứu dữ liệu)
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
        key, order = _find_order(order_id)
        if order is None:
            return (
                f"LỖI: Không tìm thấy đơn hàng '{order_id}' trong hệ thống. "
                f"Vui lòng kiểm tra lại mã đơn (định dạng đúng: DHyyyymmdd)."
            )

        days = _days_since_delivery(order)
        if days is None:
            return (
                f"Đơn {key} | Sản phẩm: {order['product']} | Ngành hàng: {order['category']} | "
                f"Giá: {_money(order['price'])} | Ngày đặt: {order['order_date']:%d/%m/%Y} | "
                f"Trạng thái: {order['status']} (CHƯA GIAO — chưa tính được thời hạn đổi trả). "
                f"Dùng get_shipping_info để xem vị trí kiện hàng."
            )

        return (
            f"Đơn {key} | Sản phẩm: {order['product']} | Ngành hàng: {order['category']} | "
            f"Giá: {_money(order['price'])} | Voucher đã dùng: {_money(order['voucher'])} | "
            f"Ngày đặt: {order['order_date']:%d/%m/%Y} | Ngày giao: {order['delivery_date']:%d/%m/%Y} | "
            f"Trạng thái: {order['status']} | Số ngày kể từ khi giao: {days} ngày."
        )
    except Exception as e:  # Guardrail: tuyệt đối không để tool làm crash vòng lặp ReAct
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
        key, order = _find_order(order_id)
        if order is None:
            return f"LỖI: Không tìm thấy đơn hàng '{order_id}' trong hệ thống."

        if order["delivery_date"] is not None:
            return (
                f"LỖI: Đơn {key} đã giao xong ngày {order['delivery_date']:%d/%m/%Y}, "
                f"không còn thông tin vận chuyển. Dùng get_order_status để xem chi tiết đơn."
            )

        return (
            f"Đơn {key} | Đơn vị vận chuyển: {order['carrier']} | "
            f"Vị trí hiện tại: {order['location']} | "
            f"Dự kiến giao: {order['eta']:%d/%m/%Y}."
        )
    except Exception as e:
        return f"LỖI: Sự cố khi tra cứu vận chuyển ({e})."


# ==========================================================================================
# TẦNG 2 — RULE (Kiểm tra quy tắc nghiệp vụ)
# ==========================================================================================

def check_return_policy(product_category: str, days_since_delivery: str) -> str:
    """
    Đối chiếu chính sách đổi trả theo ngành hàng và số ngày kể từ khi giao hàng.
    Đây là tool BẮT BUỘC phải gọi trước khi tạo yêu cầu đổi trả.

    Args:
        product_category (str): Ngành hàng ('giày dép', 'thời trang', 'điện tử', 'đồ lót', 'thực phẩm')
        days_since_delivery (str): Số ngày kể từ khi giao hàng (Ví dụ: '8')

    Returns:
        str: Bắt đầu bằng 'ĐỦ ĐIỀU KIỆN:' nếu được phép đổi trả,
             'TỪ CHỐI:' nếu quá hạn hoặc ngành hàng không áp dụng,
             'LỖI:' nếu tham số không hợp lệ.
    """
    try:
        # --- Xác thực tham số 1: ngành hàng ---
        wanted = _norm(product_category)
        matched = None
        for name in RETURN_POLICY_DAYS:
            if _norm(name) == wanted:
                matched = name
                break
        if matched is None:
            hop_le = ", ".join(f"'{k}'" for k in RETURN_POLICY_DAYS)
            return (
                f"LỖI: Ngành hàng '{product_category}' không có trong bảng chính sách. "
                f"Các ngành hàng hợp lệ: {hop_le}."
            )

        # --- Xác thực tham số 2: số ngày ---
        raw_days = str(days_since_delivery).strip().strip("'\"")
        try:
            days = int(float(raw_days))
        except ValueError:
            return (
                f"LỖI: Tham số days_since_delivery='{days_since_delivery}' không phải số. "
                f"Hãy lấy số ngày từ kết quả của get_order_status (Ví dụ: '8')."
            )
        if days < 0:
            return f"LỖI: Số ngày không thể âm (nhận được {days})."

        # --- Áp dụng chính sách ---
        limit = RETURN_POLICY_DAYS[matched]
        if limit == 0:
            return (
                f"TỪ CHỐI: Ngành hàng '{matched}' không áp dụng đổi trả vì lý do vệ sinh/an toàn, "
                f"bất kể đã giao bao nhiêu ngày. Đề nghị chuyển khách sang kênh CSKH để được hỗ trợ khác."
            )
        if days > limit:
            return (
                f"TỪ CHỐI: Ngành hàng '{matched}' chỉ đổi trả trong {limit} ngày kể từ khi giao, "
                f"đơn này đã giao {days} ngày (quá hạn {days - limit} ngày)."
            )

        _POLICY_APPROVED.add(matched)
        return (
            f"ĐỦ ĐIỀU KIỆN: Ngành hàng '{matched}' được đổi trả trong {limit} ngày, "
            f"đơn này mới giao {days} ngày (còn {limit - days} ngày). Có thể tạo yêu cầu đổi trả."
        )
    except Exception as e:
        return f"LỖI: Sự cố khi đối chiếu chính sách ({e})."


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
        key, order = _find_order(order_id)
        if order is None:
            return f"LỖI: Không tìm thấy đơn hàng '{order_id}' để tính hoàn tiền."

        kind = _norm(return_type)
        if kind in ("doi size", "doi san pham khac"):
            return (
                f"Đơn {key} — Hình thức '{return_type}': không hoàn tiền mặt, "
                f"shop đổi sản phẩm tương đương giá {_money(order['price'])}. "
                f"Khách chỉ chịu phí ship chiều về {_money(RETURN_SHIPPING_FEE)}."
            )
        if kind != "hoan tien":
            return (
                f"LỖI: return_type='{return_type}' không hợp lệ. "
                f"Chỉ chấp nhận: 'đổi size', 'hoàn tiền', 'đổi sản phẩm khác'."
            )

        actual = order["price"] - order["voucher"] - RETURN_SHIPPING_FEE
        return (
            f"Đơn {key} — Hình thức 'hoàn tiền': "
            f"Giá gốc {_money(order['price'])} "
            f"- Voucher đã dùng {_money(order['voucher'])} "
            f"- Phí ship chiều về {_money(RETURN_SHIPPING_FEE)} "
            f"= Khách thực nhận {_money(actual)}. Tiền về tài khoản trong 3-5 ngày làm việc."
        )
    except Exception as e:
        return f"LỖI: Sự cố khi tính hoàn tiền ({e})."


# ==========================================================================================
# TẦNG 3 — WRITE (Hành động có hậu quả thật)
# ==========================================================================================

def create_return_request(order_id: str, reason: str) -> str:
    """
    Tạo yêu cầu đổi/trả hàng và sinh mã RMA.
    CHỈ ĐƯỢC GỌI SAU KHI check_return_policy trả về 'ĐỦ ĐIỀU KIỆN'.

    Args:
        order_id (str): Mã đơn hàng (Ví dụ: 'DH20260715')
        reason (str): Lý do đổi trả (Ví dụ: 'sai size', 'lỗi kỹ thuật', 'không đúng mô tả')

    Returns:
        str: Mã RMA và hướng dẫn tiếp theo, hoặc chuỗi 'LỖI:' nếu không thể tạo.
    """
    try:
        key, order = _find_order(order_id)
        if order is None:
            return f"LỖI: Không tìm thấy đơn hàng '{order_id}', không thể tạo yêu cầu đổi trả."

        if not str(reason).strip().strip("'\""):
            return "LỖI: Thiếu lý do đổi trả (tham số reason không được để trống)."

        if order["delivery_date"] is None:
            return (
                f"TỪ CHỐI: Đơn {key} đang ở trạng thái '{order['status']}', chưa giao đến khách "
                f"nên chưa thể tạo yêu cầu đổi trả. Khách có thể yêu cầu huỷ đơn thay thế."
            )

        # GUARDRAIL THỨ TỰ: chặn Agent bỏ qua bước kiểm tra chính sách
        if order["category"] not in _POLICY_APPROVED:
            return (
                f"LỖI: Chưa có xác nhận chính sách cho ngành hàng '{order['category']}'. "
                f"Bắt buộc gọi check_return_policy['{order['category']}', "
                f"'{_days_since_delivery(order)}'] và nhận kết quả 'ĐỦ ĐIỀU KIỆN' trước "
                f"khi tạo yêu cầu đổi trả."
            )

        # GUARDRAIL NGHIỆP VỤ: kiểm tra lại hạn ngay tại tool WRITE (không tin mỗi prompt)
        days = _days_since_delivery(order)
        limit = RETURN_POLICY_DAYS.get(order["category"], 0)
        if limit == 0 or days > limit:
            return (
                f"TỪ CHỐI: Đơn {key} không đủ điều kiện đổi trả "
                f"(ngành hàng '{order['category']}', giới hạn {limit} ngày, đã giao {days} ngày). "
                f"Không tạo được yêu cầu."
            )

        _RMA_COUNTER["n"] += 1
        rma = f"RMA-{key[2:]}-{_RMA_COUNTER['n']:03d}"
        return (
            f"THÀNH CÔNG: Đã tạo yêu cầu đổi trả cho đơn {key}. "
            f"Mã RMA: {rma} | Lý do: {reason}. "
            f"Bước tiếp theo: đóng gói nguyên tem mác, shipper sẽ đến lấy trong 48 giờ. "
            f"Khách theo dõi tiến độ bằng mã RMA này."
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


if __name__ == "__main__":
    # Test độc lập từng tool trước khi gắn vào Agent (theo yêu cầu CODELAB mục 3)
    import sys
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("=== TEST ĐỘC LẬP CÁC TOOL ===\n")
    cases = [
        ("get_order_status", ("DH20260715",)),
        ("get_order_status", ("DH99999999",)),          # đơn không tồn tại
        ("get_shipping_info", ("DH20260801",)),
        ("get_shipping_info", ("DH20260715",)),         # đơn đã giao
        ("check_return_policy", ("giày dép", "13")),
        ("check_return_policy", ("điện tử", "8")),      # quá hạn
        ("check_return_policy", ("đồ lót", "2")),       # ngành hàng không áp dụng
        ("check_return_policy", ("giày dép", "ba ngày")),  # tham số sai kiểu
        ("calculate_refund", ("DH20260715", "hoàn tiền")),
        ("create_return_request", ("DH20260715", "sai size")),
        ("create_return_request", ("DH20260720", "lỗi kỹ thuật")),  # chưa check policy
    ]
    for name, args in cases:
        print(f"{name}{args}")
        print(f"  {AVAILABLE_TOOLS[name](*args)}\n")
