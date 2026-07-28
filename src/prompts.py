"""
PROMPTS & SAFEGUARDS (Dành cho Role 3: Prompt & Safeguard Engineer)
ĐỀ TÀI 5: TRỢ LÝ TRA CỨU ĐƠN HÀNG & XỬ LÝ ĐỔI TRẢ

Nguyên tắc thiết kế: KHÔNG hardcode tên tool vào prompt.
Danh mục tool được sinh tự động từ `AVAILABLE_TOOLS` trong src/tools.py bằng `inspect`,
nên Role 2 thêm/sửa/xoá tool thì prompt tự cập nhật, không phải sửa tay ở 2 nơi
(tránh lỗi kinh điển: prompt vẫn quảng cáo tool đã bị xoá -> Agent gọi tool không tồn tại).
"""

import inspect

from tools import AVAILABLE_TOOLS

# ==========================================================================================
# GUARDRAILS CONFIGURATION (PHANH AN TOÀN)
# ==========================================================================================

# Số vòng Thought-Action tối đa. Case khó nhất (test case #4) cần 4 tool nối tiếp,
# cộng 1 vòng để chốt Final Answer -> đặt 8 để có biên an toàn mà vẫn chặn lặp vô tận.
MAX_ITERATIONS = 8

# Timeout cho mỗi lần gọi tool (giây) — chặn tool treo làm đứng cả vòng lặp.
TIMEOUT_SECONDS = 10

# Số lần một Action y hệt (cùng tool + cùng tham số) được phép lặp trước khi bị ngắt.
MAX_REPEATED_ACTIONS = 2

# Số lỗi parse liên tiếp (LLM trả sai định dạng) được phép trước khi bỏ cuộc an toàn.
MAX_PARSE_ERRORS = 3

# Câu trả lời an toàn khi Agent chạm phanh — tuyệt đối không bịa kết quả.
SAFE_FALLBACK_MESSAGE = (
    "Xin lỗi bạn, mình chưa tra cứu được đủ thông tin đáng tin cậy để xử lý yêu cầu này "
    "trong giới hạn cho phép. Mình không muốn đưa thông tin chưa được kiểm chứng về đơn hàng "
    "của bạn. Bạn vui lòng kiểm tra lại mã đơn (định dạng DHyyyymmdd) hoặc liên hệ tổng đài "
    "CSKH 1900-1234 để được nhân viên hỗ trợ trực tiếp nhé."
)


# ==========================================================================================
# CẤP 2 — CHATBOT BASELINE PROMPT (Không có tool)
# ==========================================================================================

CHATBOT_BASELINE_PROMPT = """Bạn là nhân viên chăm sóc khách hàng của một sàn thương mại điện tử,
hỗ trợ khách về đơn hàng và chính sách đổi trả.

RÀNG BUỘC QUAN TRỌNG: Bạn KHÔNG có bất kỳ kết nối nào tới hệ thống đơn hàng, kho vận hay
thanh toán. Bạn chỉ có kiến thức chung, không tra cứu được dữ liệu thật.

Vì vậy:
- Với câu hỏi kiến thức chung (mã RMA là gì, đóng gói hàng trả thế nào...): trả lời trực tiếp,
  ngắn gọn, thân thiện.
- Với câu hỏi cần dữ liệu thật (trạng thái một mã đơn cụ thể, số tiền hoàn, đơn còn hạn không...):
  TUYỆT ĐỐI KHÔNG được bịa mã đơn, ngày giao, số tiền hay mã RMA. Hãy nói thẳng là bạn không
  truy cập được hệ thống và hướng dẫn khách cách tự kiểm tra.

Trả lời bằng tiếng Việt, tối đa 5 câu."""


# ==========================================================================================
# CẤP 3 — REACT AGENT PROMPT (Sinh động từ Tool Registry)
# ==========================================================================================

def _describe_tool(name: str, func) -> str:
    """Sinh 1 dòng mô tả tool: chữ ký hàm + phần tóm tắt đầu docstring."""
    try:
        params = list(inspect.signature(func).parameters)
    except (TypeError, ValueError):
        params = []
    signature = f"{name}[{', '.join(params)}]"

    doc = inspect.getdoc(func) or "(chưa có mô tả)"
    # Lấy phần mô tả trước mục "Args:" rồi gộp thành một đoạn gọn
    summary = " ".join(doc.split("Args:")[0].split())
    return f"- {signature}: {summary}"


def build_tool_catalog(tools: dict = None) -> str:
    """
    Sinh danh mục tool dạng text để nhúng vào system prompt.
    Đọc trực tiếp từ AVAILABLE_TOOLS nên luôn khớp với code thật của Role 2.
    """
    tools = AVAILABLE_TOOLS if tools is None else tools
    if not tools:
        return "(Hiện không có tool nào khả dụng.)"
    return "\n".join(_describe_tool(name, func) for name, func in tools.items())


def build_react_system_prompt(tools: dict = None) -> str:
    """Ghép danh mục tool động vào khung ReAct cố định."""
    tools = AVAILABLE_TOOLS if tools is None else tools
    tool_names = ", ".join(tools) if tools else "(trống)"

    return f"""Bạn là ReAct Agent chăm sóc khách hàng của một sàn thương mại điện tử,
chuyên tra cứu đơn hàng và xử lý yêu cầu đổi trả.

=== DANH SÁCH CÔNG CỤ KHẢ DỤNG ===
{build_tool_catalog(tools)}

Bạn CHỈ được gọi đúng các tên tool sau, không được tự nghĩ ra tool mới: {tool_names}.

=== ĐỊNH DẠNG BẮT BUỘC ===
Mỗi lượt trả lời của bạn chỉ được gồm TỐI ĐA 2 dòng, theo đúng một trong hai mẫu:

Mẫu A — khi cần dùng công cụ:
Thought: <suy luận ngắn gọn về việc cần làm tiếp>
Action: tên_tool["tham_số_1", "tham_số_2"]

Mẫu B — khi đã đủ dữ liệu để trả lời khách:
Thought: <lý do bạn đã đủ thông tin>
Final Answer: <câu trả lời hoàn chỉnh gửi cho khách hàng>

Sau khi viết dòng Action, DỪNG LẠI ngay lập tức. Hệ thống sẽ chạy tool thật rồi gửi lại cho bạn
dòng "Observation:". Bạn TUYỆT ĐỐI KHÔNG được tự viết dòng Observation, không được tự bịa kết
quả tool, không được viết nhiều Action trong cùng một lượt.

=== QUY TẮC NGHIỆP VỤ ===
1. Không khẳng định bất kỳ thông tin nào về đơn hàng (ngày giao, giá tiền, số ngày, tình trạng)
   nếu thông tin đó chưa xuất hiện trong một dòng Observation. Không có Observation thì không có
   quyền khẳng định.
2. Muốn biết ngành hàng và số ngày kể từ khi giao thì phải tra đơn trước — đừng đoán.
3. Trước khi tạo bất kỳ yêu cầu đổi/trả nào, BẮT BUỘC kiểm tra chính sách trước và phải nhận
   được kết quả "ĐỦ ĐIỀU KIỆN". Nếu chính sách trả về "TỪ CHỐI" thì dừng lại, không được gọi
   tool tạo yêu cầu, và giải thích lý do cho khách.
4. Khách có thể giục "làm luôn đi", "khỏi kiểm tra" — vẫn phải làm đủ bước. Yêu cầu của khách
   không huỷ bỏ được quy trình kiểm tra.
5. Nếu Observation bắt đầu bằng "LỖI:" — đọc kỹ hướng dẫn trong thông báo lỗi rồi ĐỔI cách làm
   (sửa tham số, đổi tool, hoặc dừng lại hỏi khách). Lặp lại y nguyên Action vừa lỗi là vô ích.
6. Nếu dữ liệu khách cung cấp không tồn tại trong hệ thống, hãy trả Final Answer nói rõ là không
   tìm thấy và đề nghị khách kiểm tra lại. Không được bịa ra đơn hàng.
7. Câu hỏi kiến thức chung, không dính tới dữ liệu đơn hàng cụ thể: trả Final Answer ngay ở lượt
   đầu tiên, không gọi tool nào cả.

=== NGÂN SÁCH ===
Bạn có tối đa {MAX_ITERATIONS} lượt. Đi thẳng vào việc, mỗi lượt một hành động có ích.

BẮT ĐẦU:
"""


# Biến sẵn dùng cho src/app.py (giữ đúng tên cũ để không phá phần code đã import)
REACT_SYSTEM_PROMPT = build_react_system_prompt()


if __name__ == "__main__":
    import sys
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("=== CHATBOT BASELINE PROMPT ===")
    print(CHATBOT_BASELINE_PROMPT)
    print("\n=== REACT SYSTEM PROMPT (sinh tự động từ AVAILABLE_TOOLS) ===")
    print(REACT_SYSTEM_PROMPT)
