"""
🚀 CORE AGENT APP (Dành cho Role 4: Core Agent Developer)
File chính ghép nối tất cả các thành phần: Tools + Prompts + Test Cases + Multi-Provider.
ĐỀ TÀI 5: Trợ lý tra cứu đơn hàng & xử lý đổi trả.
"""

import json
import os
import re
import sys
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
from tools import AVAILABLE_TOOLS
from prompts import CHATBOT_BASELINE_PROMPT, REACT_SYSTEM_PROMPT, MAX_ITERATIONS
from providers import get_llm_provider

load_dotenv()


def load_test_cases():
    """Đọc bộ test cases từ config/test_cases.json của Role 1"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")

    # Fallback kiểm tra nếu file ở thư mục hiện tại
    if not os.path.exists(config_path):
        config_path = "test_cases.json"

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_baseline_chatbot(user_query: str, provider):
    """
    Dựng Chatbot gốc (Baseline) không có công cụ.
    """
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")

    # Gọi LLM Provider thực hiện sinh câu trả lời
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot trả lời:\n{response}")
    return response


def run_react_agent(user_query: str, provider):
    """
    Dựng vòng lặp ReAct Agent (Thought -> Action -> Observation) có Guardrails.

    Mỗi vòng: gửi (System Prompt + câu hỏi + scratchpad) cho LLM -> LLM sinh Action
    -> hệ thống chạy tool thật -> nối Observation vào scratchpad -> lặp lại.
    """
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")
    scratchpad = ""
    policy_approved = False  # Đã có tool nào xác nhận "ĐỦ ĐIỀU KIỆN" chưa?

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- 🔄 Vòng lặp ReAct (Step {step}/{MAX_ITERATIONS}) ---")

        # 1️⃣ Hỏi LLM bước tiếp theo
        prompt = f"Câu hỏi của người dùng: {user_query}\n\n{scratchpad}"
        output = provider.generate(prompt, system_prompt=REACT_SYSTEM_PROMPT)

        # 🛡️ Cắt bỏ phần LLM tự bịa Observation — Observation phải do hệ thống sinh ra
        output = re.split(r"\n\s*Observation\s*:", output or "")[0].strip()

        thought = re.search(r"Thought\s*:\s*(.+)", output)
        final = re.search(r"Final\s*Answer\s*:\s*(.+)", output, re.DOTALL)
        action = re.search(r"Action\s*:\s*(\w+)\s*\[(.*?)\]", output, re.DOTALL)

        if thought:
            print(f"🧠 Thought: {thought.group(1).strip()}")

        # 2️⃣ LLM đã đủ thông tin -> chốt câu trả lời
        if final and (not action or final.start() < action.start()):
            print(f"🏁 Final Answer: {final.group(1).strip()}")
            return final.group(1).strip()

        # 3️⃣ LLM không tuân thủ định dạng ReAct -> nhắc lại mẫu
        if not action:
            print(f"⚠️ Không parse được định dạng ReAct. Output thô:\n{output[:300]}")
            scratchpad += ("\nObservation: LỖI ĐỊNH DẠNG — hãy trả lời đúng mẫu "
                           "'Thought: ...' rồi 'Action: tên_công_cụ[tham_số]', "
                           "hoặc 'Thought: ...' rồi 'Final Answer: ...'.\n")
            continue

        tool_name = action.group(1).strip()
        args = [a.strip().strip("'\"") for a in action.group(2).split(",")] if action.group(2).strip() else []
        print(f"🛠️ Action: {tool_name}[{', '.join(args)}]")

        # 4️⃣ Thực thi tool + Guardrails
        if tool_name not in AVAILABLE_TOOLS:
            # 🛡️ Guardrail: gọi tool không tồn tại
            obs = (f"LỖI: Không tồn tại công cụ '{tool_name}'. "
                   f"Các công cụ hợp lệ: {', '.join(AVAILABLE_TOOLS.keys())}.")
        elif tool_name == "create_return_request" and not policy_approved:
            # 🛡️ Guardrail phụ thuộc: cấm tạo yêu cầu khi chưa xác minh chính sách
            obs = ("TỪ CHỐI: Bạn phải gọi check_return_policy và nhận kết quả "
                   "'ĐỦ ĐIỀU KIỆN' trước khi tạo yêu cầu đổi trả.")
        else:
            try:
                obs = str(AVAILABLE_TOOLS[tool_name](*args))
            except TypeError:
                # 🛡️ Guardrail: sai số lượng tham số
                obs = f"LỖI: Sai số lượng tham số khi gọi '{tool_name}' (bạn truyền {len(args)} tham số)."
            except Exception as e:
                obs = f"LỖI: Công cụ '{tool_name}' gặp sự cố ({e})."

        if "ĐỦ ĐIỀU KIỆN" in obs:
            policy_approved = True

        print(f"👁️ Observation: {obs}")

        # 5️⃣ Nối kết quả vào scratchpad để LLM nhìn thấy ở vòng lặp sau
        scratchpad += (f"\nThought: {thought.group(1).strip() if thought else ''}\n"
                       f"Action: {tool_name}[{', '.join(args)}]\n"
                       f"Observation: {obs}\n")

    # 🛡️ Guardrail: chạm trần số vòng lặp mà vẫn chưa có Final Answer
    print(f"\n🛡️ GUARDRAIL TRIGGERED: Đã đạt giới hạn tối đa {MAX_ITERATIONS} bước. Ngắt lặp an toàn!")
    fallback = (f"Xin lỗi, tôi chưa xử lý xong yêu cầu sau {MAX_ITERATIONS} bước. "
                f"Tôi sẽ chuyển bạn sang nhân viên hỗ trợ.")
    print(f"🏁 Fallback Answer: {fallback}")
    return fallback


if __name__ == "__main__":
    print("==================================================")
    print("🏫 BÀI LAB 3: CHATBOT VS REACT AGENT (ĐỀ TÀI 5)")
    print("==================================================")

    # Khởi tạo Multi-Provider LLM Adapter (Đọc từ biến môi trường LLM_PROVIDER)
    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(f"🔌 LLM Provider đang hoạt động: {provider.__class__.__name__} (Model: {model_name})")
    print(f"🧰 Tools: {', '.join(AVAILABLE_TOOLS.keys())}")

    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases từ config/test_cases.json")

    # Chạy tuần tự toàn bộ test cases
    for tc in tests:
        print("\n" + "=" * 60)
        print(f"🧪 TEST CASE #{tc['id']} — {tc.get('category', '')}")
        print(f"❓ {tc['question']}")
        print(f"🎯 Kỳ vọng: {tc.get('expected_behavior', 'N/A')}")
        print("=" * 60)

        print("\n--- DEMO 1: CHẠY TRÊN CHATBOT BASELINE ---")
        run_baseline_chatbot(tc["question"], provider)

        print("\n--- DEMO 2: CHẠY TRÊN REACT AGENT ---")
        run_react_agent(tc["question"], provider)
