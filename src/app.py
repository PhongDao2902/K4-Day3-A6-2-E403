"""
CORE AGENT APP (Dành cho Role 4: Core Agent Developer)
File chính ghép nối tất cả các thành phần: Tools + Prompts + Test Cases + Multi-Provider.

ĐỀ TÀI 5: TRỢ LÝ TRA CỨU ĐƠN HÀNG & XỬ LÝ ĐỔI TRẢ

Cách chạy:
    python src/app.py                 # chạy cả 6 test case trên Chatbot lẫn ReAct Agent
    python src/app.py --case 4        # chỉ chạy test case số 4
    python src/app.py --mode agent    # chỉ chạy ReAct Agent
    python src/app.py --ask "Đơn DH20260715 còn đổi trả được không?"
    python src/app.py --trace-out docs/trace_raw.md    # xuất toàn bộ log trace ra file
"""

import argparse
import ast
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from dotenv import load_dotenv

# Đảm bảo import các module cùng thư mục src/ hoạt động mượt mà
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Import các thành phần từ file của Role 2, Role 3 & Multi-Provider Adapter
from tools import AVAILABLE_TOOLS, reset_tool_state
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    MAX_ITERATIONS,
    MAX_PARSE_ERRORS,
    MAX_REPEATED_ACTIONS,
    SAFE_FALLBACK_MESSAGE,
    TIMEOUT_SECONDS,
    build_react_system_prompt,
)
from providers import get_llm_provider

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Bộ nhớ log để Role 5 trích xuất trace ra báo cáo
RUN_LOG = []


def log(line: str = "") -> None:
    """In ra màn hình đồng thời giữ lại trong RUN_LOG để xuất file trace."""
    print(line)
    RUN_LOG.append(line)


# ==========================================================================================
# LLM CALL WRAPPER — Tự thử lại khi nhà cung cấp trả lỗi tạm thời (rate limit / quá tải)
# ==========================================================================================

# Provider trong src/providers.py nuốt exception và trả về chuỗi "[... Exception]: ...",
# nên phải nhận diện lỗi tạm thời bằng nội dung chuỗi trả về.
MAX_LLM_RETRIES = 4
DEFAULT_RETRY_WAIT = 20  # giây, dùng khi không đọc được retryDelay từ thông báo lỗi

# Giãn nhịp chủ động: gói free tier của Gemini giới hạn số request mỗi phút, nên chạy
# một mạch 6 test case sẽ đâm thẳng vào 429. Chờ sẵn vài giây giữa 2 lần gọi rẻ hơn
# nhiều so với bị phạt rồi mới retry.
MIN_SECONDS_BETWEEN_CALLS = float(os.getenv("LLM_MIN_INTERVAL", "4"))
_last_call_at = [0.0]

_RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "rate limit", "quota", "503", "UNAVAILABLE",
              "overloaded", "500", "INTERNAL")
_RETRY_DELAY_RE = re.compile(r"'retryDelay':\s*'(\d+)", re.IGNORECASE)
_RETRY_IN_RE = re.compile(r"retry in ([\d.]+)s", re.IGNORECASE)


def _is_transient_error(text: str) -> bool:
    if not text or "Exception]" not in text and "Error]" not in text:
        return False
    return any(marker.lower() in text.lower() for marker in _RETRYABLE)


def _retry_wait_seconds(text: str) -> int:
    """Đọc thời gian chờ nhà cung cấp gợi ý, nếu không có thì dùng mặc định."""
    m = _RETRY_DELAY_RE.search(text) or _RETRY_IN_RE.search(text)
    if m:
        return min(int(float(m.group(1))) + 2, 90)
    return DEFAULT_RETRY_WAIT


def call_llm(provider, prompt: str, system_prompt: str = "") -> str:
    """
    Gọi LLM có cơ chế thử lại. Đây là guardrail ở tầng hạ tầng: lỗi rate limit của nhà
    cung cấp KHÔNG được phép biến thành 'Agent trả lời sai' trong báo cáo đánh giá.
    """
    last = ""
    for attempt in range(1, MAX_LLM_RETRIES + 1):
        gap = time.monotonic() - _last_call_at[0]
        if gap < MIN_SECONDS_BETWEEN_CALLS:
            time.sleep(MIN_SECONDS_BETWEEN_CALLS - gap)

        last = provider.generate(prompt, system_prompt=system_prompt)
        _last_call_at[0] = time.monotonic()
        if not _is_transient_error(last):
            return last
        if attempt == MAX_LLM_RETRIES:
            break
        wait = _retry_wait_seconds(last)
        log(f"Nhà cung cấp báo lỗi tạm thời (lần {attempt}/{MAX_LLM_RETRIES}), "
            f"chờ {wait}s rồi thử lại...")
        time.sleep(wait)
    return last


def load_test_cases():
    """Đọc bộ test cases từ config/test_cases.json của Role 1"""
    config_path = os.path.join(BASE_DIR, "config", "test_cases.json")

    # Fallback kiểm tra nếu file ở thư mục hiện tại
    if not os.path.exists(config_path):
        config_path = "test_cases.json"

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==========================================================================================
# PARSER — Bóc Thought / Action / Final Answer từ text thô của LLM
# ==========================================================================================

# Cắt bỏ mọi thứ từ "Observation:" trở đi: LLM hay tự bịa kết quả tool,
# chỉ có application mới được quyền sinh Observation (nguyên tắc bất biến #2 của CODELAB).
_OBSERVATION_CUT = re.compile(r"^\s*Observation\s*:", re.IGNORECASE | re.MULTILINE)

_ACTION_RE = re.compile(
    r"^\s*Action\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*[\[\(](.*?)[\]\)]\s*$",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_THOUGHT_RE = re.compile(r"^\s*Thought\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_FINAL_RE = re.compile(r"^\s*Final\s*Answer\s*:\s*(.+)", re.IGNORECASE | re.MULTILINE | re.DOTALL)


def sanitize_llm_output(raw: str) -> str:
    """Chặn LLM tự viết Observation hoặc xả một lúc nhiều bước."""
    text = (raw or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()  # gỡ code fence nếu có

    cut = _OBSERVATION_CUT.search(text)
    if cut:
        text = text[:cut.start()].strip()

    # Chỉ giữ tới hết dòng Action đầu tiên — mỗi lượt đúng 1 hành động
    action = _ACTION_RE.search(text)
    if action:
        text = text[:action.end()].strip()
    return text


def parse_args_string(arg_str: str):
    """
    Bóc danh sách tham số từ chuỗi trong ngoặc.
    Ưu tiên literal_eval (chuẩn Python), nếu hỏng thì tách thủ công theo dấu phẩy.
    """
    arg_str = (arg_str or "").strip()
    if not arg_str:
        return []
    try:
        value = ast.literal_eval(f"[{arg_str}]")
        return [str(v) for v in value]
    except (ValueError, SyntaxError):
        parts, buf, quote = [], "", None
        for ch in arg_str:
            if quote:
                if ch == quote:
                    quote = None
                else:
                    buf += ch
            elif ch in "'\"":
                quote = ch
            elif ch == ",":
                parts.append(buf.strip())
                buf = ""
            else:
                buf += ch
        parts.append(buf.strip())
        return [p.strip().strip("'\"") for p in parts if p.strip()]


def parse_step(text: str):
    """Trả về dict {thought, action, args, final_answer} từ output đã sanitize."""
    thought = _THOUGHT_RE.search(text)
    final = _FINAL_RE.search(text)
    action = _ACTION_RE.search(text)

    return {
        "thought": thought.group(1).strip() if thought else None,
        "action": action.group(1).strip() if action else None,
        "args": parse_args_string(action.group(2)) if action else None,
        "final_answer": final.group(1).strip() if final else None,
    }


# ==========================================================================================
# EXECUTOR — Gọi tool thật, có timeout và thông báo lỗi hữu ích cho Agent
# ==========================================================================================

def execute_tool(name: str, args: list) -> str:
    """Chạy tool và LUÔN trả về str. Mọi sự cố đều biến thành Observation dạng 'LỖI:'."""
    func = AVAILABLE_TOOLS.get(name)
    if func is None:
        hop_le = ", ".join(AVAILABLE_TOOLS)
        return f"LỖI: Tool '{name}' không tồn tại. Các tool hợp lệ gồm: {hop_le}."

    import inspect
    expected = list(inspect.signature(func).parameters)
    if len(args) != len(expected):
        return (
            f"LỖI: Tool '{name}' cần đúng {len(expected)} tham số ({', '.join(expected)}), "
            f"nhưng nhận được {len(args)}. Cú pháp đúng: {name}"
            f"[{', '.join(chr(34) + p + chr(34) for p in expected)}]."
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return str(pool.submit(func, *args).result(timeout=TIMEOUT_SECONDS))
    except FutureTimeout:
        return f"LỖI: Tool '{name}' chạy quá {TIMEOUT_SECONDS} giây và đã bị ngắt."
    except Exception as e:
        return f"LỖI: Tool '{name}' gặp sự cố khi chạy ({e})."


# ==========================================================================================
# CẤP 2 — CHATBOT BASELINE (đúng 1 lần gọi LLM, 0 tool)
# ==========================================================================================

def run_baseline_chatbot(user_query: str, provider) -> dict:
    """
    Dựng Chatbot gốc (Baseline) không có công cụ.
    Đúng 1 LLM call, tool_calls = 0 — làm đường cơ sở so sánh công bằng với Agent.
    """
    log(f"\n[CHATBOT BASELINE] Câu hỏi: {user_query}")

    response = call_llm(provider, user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    log(f"Chatbot trả lời:\n{response}")

    return {
        "mode": "chatbot",
        "question": user_query,
        "answer": response,
        "llm_calls": 1,
        "tool_calls": 0,
        "termination": "single_call",
    }


# ==========================================================================================
# CẤP 3 — REACT AGENT LOOP (Thought -> Action -> Observation) + Guardrails
# ==========================================================================================

def run_react_agent(user_query: str, provider) -> dict:
    """
    Vòng lặp ReAct thật: LLM sinh Thought/Action -> application chạy tool -> chèn Observation
    thật vào transcript -> lặp lại cho tới khi có Final Answer hoặc chạm phanh an toàn.
    """
    log(f"\n[REACT AGENT] Câu hỏi: {user_query}")

    reset_tool_state()  # mỗi test case chạy trên state sạch
    system_prompt = build_react_system_prompt()
    transcript = f"Question: {user_query}\n"

    trace = []
    action_history = []
    llm_calls = tool_calls = parse_errors = 0
    step = 0

    while step < MAX_ITERATIONS:
        step += 1
        log(f"\n--- Vòng lặp ReAct (Step {step}/{MAX_ITERATIONS}) ---")

        raw = call_llm(provider, transcript, system_prompt=system_prompt)
        llm_calls += 1
        chunk = sanitize_llm_output(raw)
        parsed = parse_step(chunk)

        if parsed["thought"]:
            log(f"Thought: {parsed['thought']}")

        # --- Nhánh 1: Agent chốt câu trả lời ---
        if parsed["final_answer"]:
            log(f"Final Answer: {parsed['final_answer']}")
            trace.append({"step": step, "thought": parsed["thought"],
                          "final_answer": parsed["final_answer"]})
            return {
                "mode": "agent", "question": user_query,
                "answer": parsed["final_answer"], "trace": trace,
                "llm_calls": llm_calls, "tool_calls": tool_calls,
                "steps": step, "termination": "final_answer",
            }

        # --- Nhánh 2: Sai định dạng, không bóc được Action ---
        if not parsed["action"]:
            parse_errors += 1
            observation = (
                "LỖI ĐỊNH DẠNG: Không tìm thấy dòng 'Action:' hợp lệ. Hãy trả lời lại theo đúng "
                "mẫu — Action: tên_tool[\"tham_số\"] — hoặc chốt bằng 'Final Answer: ...'."
            )
            log(f"Output thô không đúng định dạng: {chunk[:160]!r}")
            log(f"Observation: {observation}")
            transcript += f"{chunk}\nObservation: {observation}\n"
            trace.append({"step": step, "error": "parse_error", "observation": observation})

            if parse_errors >= MAX_PARSE_ERRORS:
                log(f"GUARDRAIL TRIGGERED: LLM trả sai định dạng {parse_errors} lần "
                    f"liên tiếp -> dừng an toàn, không đoán bừa.")
                log(f"Safe Fallback: {SAFE_FALLBACK_MESSAGE}")
                return {
                    "mode": "agent", "question": user_query,
                    "answer": SAFE_FALLBACK_MESSAGE, "trace": trace,
                    "llm_calls": llm_calls, "tool_calls": tool_calls,
                    "steps": step, "termination": "guardrail_parse_errors",
                }
            continue

        parse_errors = 0
        signature = (parsed["action"], tuple(parsed["args"]))
        log(f"Action: {parsed['action']}{parsed['args']}")

        # --- Guardrail chống lặp: cùng tool + cùng tham số ---
        repeated = action_history.count(signature)
        if repeated >= MAX_REPEATED_ACTIONS:
            log(f"GUARDRAIL TRIGGERED: Action '{parsed['action']}' bị lặp lại "
                f"{repeated + 1} lần với cùng tham số -> ngắt vòng lặp.")
            trace.append({"step": step, "action": parsed["action"], "args": parsed["args"],
                          "error": "repeated_action"})
            return {
                "mode": "agent", "question": user_query,
                "answer": SAFE_FALLBACK_MESSAGE, "trace": trace,
                "llm_calls": llm_calls, "tool_calls": tool_calls,
                "steps": step, "termination": "guardrail_repeated_action",
            }
        action_history.append(signature)

        # --- Nhánh 3: Chạy tool thật và chèn Observation thật ---
        observation = execute_tool(parsed["action"], parsed["args"])
        tool_calls += 1
        log(f"Observation: {observation}")

        transcript += f"{chunk}\nObservation: {observation}\n"
        trace.append({"step": step, "thought": parsed["thought"], "action": parsed["action"],
                      "args": parsed["args"], "observation": observation})

    # --- Chạm phanh MAX_ITERATIONS: trả lời an toàn, không bịa ---
    log(f"\nGUARDRAIL TRIGGERED: Đã đạt giới hạn {MAX_ITERATIONS} bước. Ngắt lặp an toàn!")
    log(f"Safe Fallback: {SAFE_FALLBACK_MESSAGE}")
    return {
        "mode": "agent", "question": user_query,
        "answer": SAFE_FALLBACK_MESSAGE, "trace": trace,
        "llm_calls": llm_calls, "tool_calls": tool_calls,
        "steps": step, "termination": "guardrail_max_iterations",
    }


# ==========================================================================================
# RUNNER & BÁO CÁO
# ==========================================================================================

def print_summary(results):
    """Bảng tổng kết để Role 5 dán thẳng vào docs/trace_eval.md."""
    log("\n" + "=" * 92)
    log("BẢNG TỔNG KẾT SO SÁNH")
    log("=" * 92)
    log(f"{'Case':<5}{'Chế độ':<10}{'LLM calls':<11}{'Tool calls':<12}{'Bước':<7}{'Kết thúc bởi'}")
    log("-" * 92)
    for case_id, res in results:
        log(f"{case_id:<5}{res['mode']:<10}{res['llm_calls']:<11}{res['tool_calls']:<12}"
            f"{res.get('steps', 1):<7}{res['termination']}")
    log("=" * 92)


def main():
    parser = argparse.ArgumentParser(description="Lab 03 — Chatbot vs ReAct Agent")
    parser.add_argument("--case", type=int, help="Chỉ chạy 1 test case theo id")
    parser.add_argument("--mode", choices=["chatbot", "agent", "both"], default="both")
    parser.add_argument("--ask", type=str, help="Chạy trên một câu hỏi tự nhập")
    parser.add_argument("--trace-out", type=str, help="Xuất toàn bộ log trace ra file markdown")
    args = parser.parse_args()

    log("=" * 92)
    log("ĐẠI HỌC VINUNI - BÀI LAB 3: CHATBOT VS REACT AGENT")
    log("Đề tài: Trợ lý tra cứu đơn hàng & xử lý đổi trả")
    log("=" * 92)

    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    log(f"LLM Provider: {provider.__class__.__name__} (Model: {model_name})")
    log(f"Tool đã đăng ký ({len(AVAILABLE_TOOLS)}): {', '.join(AVAILABLE_TOOLS)}")
    log(f"Guardrails: MAX_ITERATIONS={MAX_ITERATIONS}, "
        f"MAX_REPEATED_ACTIONS={MAX_REPEATED_ACTIONS}, TIMEOUT={TIMEOUT_SECONDS}s")

    if args.ask:
        cases = [{"id": 0, "category": "Câu hỏi tự nhập", "question": args.ask}]
    else:
        cases = load_test_cases()
        log(f"Đã tải {len(cases)} Test Cases từ config/test_cases.json")
        if args.case:
            cases = [c for c in cases if c["id"] == args.case]
            if not cases:
                log(f"Không có test case id={args.case}")
                return

    results = []
    for case in cases:
        log("\n" + "#" * 92)
        log(f"# TEST CASE {case['id']} — {case.get('category', '')}")
        log(f"# {case['question']}")
        if case.get("expected_behavior"):
            log(f"# Kỳ vọng: {case['expected_behavior']}")
        log("#" * 92)

        if args.mode in ("chatbot", "both"):
            log("\n--- CHATBOT BASELINE ---")
            results.append((case["id"], run_baseline_chatbot(case["question"], provider)))

        if args.mode in ("agent", "both"):
            log("\n--- REACT AGENT ---")
            results.append((case["id"], run_react_agent(case["question"], provider)))

    print_summary(results)

    if args.trace_out:
        out_path = args.trace_out if os.path.isabs(args.trace_out) \
            else os.path.join(BASE_DIR, args.trace_out)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("# RAW TRACE LOG (sinh tự động bởi src/app.py)\n\n```text\n")
            f.write("\n".join(RUN_LOG))
            f.write("\n```\n")
        print(f"\nĐã ghi log trace vào: {out_path}")


if __name__ == "__main__":
    main()
