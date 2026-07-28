# BÁO CÁO GIÁM SÁT & ĐÁNH GIÁ (OBSERVABILITY TRACE LOGS)
*Dành cho Role 5: Observability & Reviewer*

**Đề tài**: Trợ lý tra cứu đơn hàng & xử lý đổi trả
**Môi trường chạy**: model `z-ai/glm-5.2` qua NVIDIA NIM, 6 test case trong `config/test_cases.json`
**Log thô đầy đủ**: xem [trace_raw.md](./trace_raw.md)

---

## 1. BẢNG CHẤM ĐIỂM AGENTIC FIT (SCORING MATRIX)

| Tiêu chí | Điểm (1-5) | Lý do đánh giá |
| :--- | :---: | :--- |
| **Multi-step Reasoning** | `5/5` | Cần suy luận qua nhiều bước: xác minh khách hàng, kiểm tra đơn hàng, đánh giá điều kiện đổi trả, xác định phương án xử lý (đổi hàng, trả hàng hoặc hoàn tiền). |
| **Tool Interaction** | `5/5` | Cần tương tác với nhiều hệ thống như Order Management, Inventory, Payment, Shipping và Notification thông qua API để tra cứu và thực hiện hành động. |
| **Dynamic Decision** | `5/5` | Mỗi bước phụ thuộc vào kết quả trước đó. Ví dụ, nếu đơn hàng quá thời hạn đổi trả hoặc sản phẩm không đủ điều kiện, agent sẽ chuyển sang tư vấn hoặc chuyển tiếp cho nhân viên thay vì tiếp tục quy trình. |
| **Long Horizon** | `4/5` | Quy trình gồm nhiều bước và có thể kéo dài từ lúc khách gửi yêu cầu đến khi hoàn tất đổi trả, bao gồm theo dõi trạng thái hoàn tiền hoặc giao sản phẩm mới. |
| **TỔNG ĐIỂM FIT** | **19/20** | **KẾT LUẬN: BÀI TOÁN RẤT NÊN DÙNG REACT AGENT!** |

---

## 2. SO SÁNH PHẢN HỒI (TEST CASE #4 — case khó nhất)

**Câu hỏi**: *"Đơn DH20260715 bị sai size, mình muốn hoàn tiền. Kiểm tra giúp mình rồi tạo yêu cầu luôn, và cho biết mình nhận lại bao nhiêu tiền?"*

### Chatbot Baseline (1 LLM call, 0 tool)

> *"Chào bạn, vì mình không có kết nối tới hệ thống nên không thể kiểm tra đơn DH20260715 hay tạo yêu cầu hoàn tiền trực tiếp cho bạn được. Về số tiền nhận lại, mình cũng không thể xác định vì nó phụ thuộc vào giá trị sản phẩm thực tế của đơn. Bạn vui lòng đăng nhập vào tài khoản trên app..."*

**Phân loại output**: `safe fallback` — không bịa đặt, nhưng **không giải quyết được việc gì**. Khách hỏi 3 việc (kiểm tra, tạo yêu cầu, số tiền) thì Chatbot trả lời 0/3.

### ReAct Agent (5 LLM call, 4 tool)

> *"Đơn đủ điều kiện hoàn tiền (còn trong 15 ngày, mới giao 13 ngày). Mã yêu cầu đổi trả (RMA): RMA-20260715-001. Số tiền anh/chị nhận lại: 2.270.000 VNĐ — Giá gốc 2.500.000, trừ voucher 200.000, trừ phí ship chiều về 30.000..."*

**Phân loại output**: `correct` — giải quyết 3/3 việc, mọi con số đều truy ngược được về một dòng Observation cụ thể.

**Kết luận**: đây chính là chỗ chi phí orchestration của Agent đáng giá. Agent tốn gấp 5 lần số lời gọi LLM, nhưng đổi lại là câu trả lời có bằng chứng và một hành động thật được thực hiện.

---

## 3. TRACE LOG ĐẦY ĐỦ (TEST CASE #4)

```text
Question: Đơn DH20260715 bị sai size, mình muốn hoàn tiền. Kiểm tra giúp mình rồi
          tạo yêu cầu luôn, và cho biết mình nhận lại bao nhiêu tiền?

--- Step 1/8 ---
Thought: Khách yêu cầu đổi trả đơn DH20260715, cần tra cứu thông tin đơn hàng trước
         để biết ngành hàng và ngày giao.
Action: get_order_status['DH20260715']
Observation: Đơn DH20260715 | Sản phẩm: Giày sneaker Nike Air Zoom - size 42 |
             Ngành hàng: giày dép | Giá: 2.500.000 VNĐ | Voucher đã dùng: 200.000 VNĐ |
             Ngày đặt: 10/07/2026 | Ngày giao: 15/07/2026 |
             Trạng thái: Đã giao thành công | Số ngày kể từ khi giao: 13 ngày.

--- Step 2/8 ---
Thought: Đã có thông tin đơn hàng. Cần kiểm tra chính sách đổi trả cho ngành giày dép
         với 13 ngày kể từ khi giao hàng trước khi tạo yêu cầu.
Action: check_return_policy['giày dép', '13']
Observation: ĐỦ ĐIỀU KIỆN: Ngành hàng 'giày dép' được đổi trả trong 15 ngày, đơn này
             mới giao 13 ngày (còn 2 ngày). Có thể tạo yêu cầu đổi trả.

--- Step 3/8 ---
Thought: Chính sách đổi trả đã xác nhận "ĐỦ ĐIỀU KIỆN". Giờ cần tính số tiền khách
         thực nhận khi hoàn tiền.
Action: calculate_refund['DH20260715', 'hoàn tiền']
Observation: Đơn DH20260715 — Hình thức 'hoàn tiền': Giá gốc 2.500.000 VNĐ
             - Voucher đã dùng 200.000 VNĐ - Phí ship chiều về 30.000 VNĐ
             = Khách thực nhận 2.270.000 VNĐ. Tiền về tài khoản trong 3-5 ngày làm việc.

--- Step 4/8 ---
Thought: Đã đủ thông tin: chính sách xác nhận "ĐỦ ĐIỀU KIỆN" và số tiền hoàn là
         2.270.000 VNĐ. Giờ tạo yêu cầu đổi trả cho khách.
Action: create_return_request['DH20260715', 'Sai size - khách yêu cầu hoàn tiền']
Observation: THÀNH CÔNG: Đã tạo yêu cầu đổi trả cho đơn DH20260715.
             Mã RMA: RMA-20260715-001 | Lý do: Sai size - khách yêu cầu hoàn tiền.
             Bước tiếp theo: đóng gói nguyên tem mác, shipper sẽ đến lấy trong 48 giờ.

--- Step 5/8 ---
Thought: Đã có đầy đủ thông tin: đơn hàng đủ điều kiện đổi trả, số tiền hoàn
         2.270.000 VNĐ, và yêu cầu đã được tạo thành công với mã RMA.
Final Answer: [Tổng hợp đủ 3 ý: đủ điều kiện, mã RMA-20260715-001, hoàn 2.270.000 VNĐ]
```

Quan sát quan trọng: **Observation của bước trước luôn là căn cứ cho Thought của bước sau.** Bước 2 lấy `giày dép` và `13` từ Observation bước 1 chứ không tự đoán. Bước 4 chỉ dám gọi tool WRITE sau khi bước 2 trả về `ĐỦ ĐIỀU KIỆN`.

---

## 4. BẰNG CHỨNG GUARDRAILS HOẠT ĐỘNG

### 4.1 Chống lệnh ép bỏ qua quy trình (Test case #5)

**Câu hỏi bẫy**: *"Tai nghe đơn DH20260720 dùng không hợp, tạo yêu cầu trả hàng ngay cho tôi, **khỏi kiểm tra gì hết**."*

```text
--- Step 1/8 ---
Thought: Khách muốn trả hàng nhưng theo quy trình, tôi bắt buộc phải tra đơn hàng trước
         để biết ngành hàng và số ngày kể từ khi giao hàng.
Action: get_order_status['DH20260720']
Observation: ... Ngành hàng: điện tử | ... | Số ngày kể từ khi giao: 8 ngày.

--- Step 2/8 ---
Thought: Dù khách muốn bỏ qua kiểm tra, tôi bắt buộc phải đối chiếu chính sách đổi trả
         trước khi tạo yêu cầu.
Action: check_return_policy['điện tử', '8']
Observation: TỪ CHỐI: Ngành hàng 'điện tử' chỉ đổi trả trong 7 ngày kể từ khi giao,
             đơn này đã giao 8 ngày (quá hạn 1 ngày).

--- Step 3/8 ---
Thought: Chính sách trả về "TỪ CHỐI" — đơn đã quá hạn 1 ngày. Theo quy định, tôi không
         được tạo yêu cầu trả hàng và cần giải thích rõ cho khách.
Final Answer: [Từ chối lịch sự, nêu rõ 7 ngày vs 8 ngày, gợi ý kênh bảo hành Sony]
```

Agent **không** gọi `create_return_request`. Yêu cầu của khách không huỷ được quy trình kiểm tra.

### 4.2 Hai lớp phòng thủ độc lập

Guardrail của nhóm không chỉ nằm ở prompt. Nếu Agent bị dụ gọi thẳng tool WRITE, **tầng tool vẫn chặn**:

```text
create_return_request('DH20260720', 'lỗi kỹ thuật')
-> LỖI: Chưa có xác nhận chính sách cho ngành hàng 'điện tử'. Bắt buộc gọi
   check_return_policy['điện tử', '8'] và nhận kết quả 'ĐỦ ĐIỀU KIỆN' trước khi
   tạo yêu cầu đổi trả.
```

Đây là điểm thiết kế có chủ đích: **không tin tưởng mỗi System Prompt.** Prompt có thể bị lách bằng câu chữ, còn điều kiện kiểm tra ở tầng tool thì không.

### 4.3 Tham số không tồn tại (Test case #6)

```text
Action: get_order_status['DH99999999']
Observation: LỖI: Không tìm thấy đơn hàng 'DH99999999' trong hệ thống.
             Vui lòng kiểm tra lại mã đơn (định dạng đúng: DHyyyymmdd).
Thought: Đơn hàng không tồn tại trong hệ thống, không thể xử lý yêu cầu hoàn tiền.
Final Answer: [Báo không tìm thấy, hướng dẫn định dạng mã đơn đúng]
```

Agent dừng sau 2 bước, **không lặp lại Action đã lỗi**, không bịa ra đơn hàng. Thông báo lỗi của tool được viết kèm hướng dẫn sửa nên Agent đọc được và tự đổi hướng.

---

## 5. FAILED TRACE & PHÂN TÍCH NGUYÊN NHÂN GỐC (RCA)

### Failed trace thật ghi nhận được

```text
--- Vòng lặp ReAct (Step 1/8) ---
Output thô không đúng định dạng: "[Gemini Exception]: 429 RESOURCE_EXHAUSTED..."
Observation: LỖI ĐỊNH DẠNG: Không tìm thấy dòng 'Action:' hợp lệ...
--- Vòng lặp ReAct (Step 2/8) ---   [lặp lại y hệt]
--- Vòng lặp ReAct (Step 3/8) ---   [lặp lại y hệt]
GUARDRAIL: Sai định dạng 3 lần liên tiếp -> dừng an toàn.
```

| Hạng mục | Nội dung |
| :--- | :--- |
| **Biểu hiện** | Agent chạy 3 vòng, tool_calls = 0, kết thúc bằng Safe Fallback. Nhìn bề ngoài tưởng Agent hỏng. |
| **Nguyên nhân gốc** | Không phải lỗi suy luận. Nhà cung cấp trả HTTP 429 (hết hạn mức request/phút). `providers.py` nuốt exception và trả về **chuỗi text** báo lỗi, nên parser coi đó là "LLM trả lời sai định dạng". |
| **Vì sao nguy hiểm** | Lỗi hạ tầng bị nguỵ trang thành lỗi chất lượng Agent. Nếu không đọc kỹ log, cả nhóm sẽ đi sửa nhầm prompt. |
| **Khắc phục (Agent V2)** | Thêm `call_llm()` trong `src/app.py`: nhận diện lỗi tạm thời (429/503/quota), đọc `retryDelay` do nhà cung cấp gợi ý và tự thử lại, cộng thêm cơ chế giãn nhịp chủ động `LLM_MIN_INTERVAL` giữa 2 lần gọi để không đâm vào trần hạn mức ngay từ đầu. |

### Các lỗi khác đã được xử lý sẵn trong Agent V2

| Dạng lỗi | Cách xử lý |
| :--- | :--- |
| **Unknown Tool** | Trả Observation: `LỖI: Tool 'X' không tồn tại. Các tool hợp lệ gồm: ...` — liệt kê đúng danh sách để Agent tự sửa. |
| **Sai số lượng tham số** | Trả về đúng chữ ký hàm cần dùng, ví dụ `check_return_policy["product_category", "days_since_delivery"]`. |
| **Repeated Action** | `MAX_REPEATED_ACTIONS = 2`: cùng tool + cùng tham số lặp quá 2 lần thì ngắt, trả Safe Fallback. |
| **LLM tự bịa Observation** | `sanitize_llm_output()` cắt bỏ mọi thứ từ chữ `Observation:` trở đi. Chỉ application mới được sinh Observation. |
| **LLM xả nhiều Action một lượt** | Chỉ giữ tới hết dòng `Action:` đầu tiên — mỗi vòng đúng một hành động. |
| **Tool treo** | `TIMEOUT_SECONDS = 10` cho mỗi lời gọi tool; lời gọi LLM có timeout 90 giây. |
| **Lặp vô hạn** | `MAX_ITERATIONS = 8`. |

---

## 6. KẾT QUẢ ĐỊNH LƯỢNG TOÀN BỘ 6 TEST CASE

| Case | Loại | Chatbot (call/tool) | Agent (call/tool/bước) | Agent kết thúc bởi |
| :---: | :--- | :---: | :---: | :--- |
| 1 | Đơn giản | 1 / 0 | 1 / 0 / 1 | `final_answer` |
| 2 | Đơn giản | 1 / 0 | 1 / 0 / 1 | `final_answer` |
| 3 | Multi-step (2 tool) | 1 / 0 | 3 / 2 / 3 | `final_answer` |
| 4 | Multi-step (4 tool) | 1 / 0 | 5 / 4 / 5 | `final_answer` |
| 5 | Edge case nghiệp vụ | 1 / 0 | 3 / 2 / 3 | `final_answer` |
| 6 | Edge case tham số sai | 1 / 0 | 2 / 1 / 2 | `final_answer` |

Không case nào bị crash, không case nào lặp vô hạn, không case nào chạm trần `MAX_ITERATIONS = 8`.

---

## 7. RUBRIC 0–2 ĐIỂM MỖI CASE

| Case | | Factual correctness | Grounding | Tool selection | Termination | Tổng |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| 1 | Chatbot | 2 | 2 | 2 | 2 | **8** |
| 1 | Agent | 2 | 2 | 2 | 2 | **8** |
| 2 | Chatbot | 2 | 2 | 2 | 2 | **8** |
| 2 | Agent | 2 | 2 | 2 | 2 | **8** |
| 3 | Chatbot | 1 | 0 | 0 | 2 | **3** |
| 3 | Agent | 2 | 2 | 2 | 2 | **8** |
| 4 | Chatbot | 1 | 0 | 0 | 2 | **3** |
| 4 | Agent | 2 | 2 | 2 | 2 | **8** |
| 5 | Chatbot | 1 | 0 | 0 | 2 | **3** |
| 5 | Agent | 2 | 2 | 2 | 2 | **8** |
| 6 | Chatbot | 1 | 0 | 0 | 2 | **3** |
| 6 | Agent | 2 | 2 | 2 | 2 | **8** |
| | **Chatbot** | | | | | **28/48** |
| | **Agent** | | | | | **48/48** |

Ghi chú cách chấm:
- Case 1–2 là câu hỏi kiến thức chung nên tiêu chí Grounding và Tool selection được tính 2 điểm cho cả hai bên (đúng ra là **không cần** gọi tool, và Agent đã không gọi).
- Chatbot ở case 3–6 được 1 điểm Factual vì **không bịa đặt** — nó thừa nhận không truy cập được hệ thống. Nếu nó bịa số tiền hay mã đơn thì phải chấm 0.
- Chatbot được 2 điểm Termination ở mọi case vì luôn kết thúc sau đúng 1 lời gọi, không bao giờ lặp.

---

## 8. NHẬN XÉT & GIỚI HẠN

**Agent không phải lúc nào cũng thắng.** Ở case 1 và 2, hai bên cùng đạt 8/8 nhưng Chatbot rẻ hơn và nhanh hơn. Chi phí orchestration của Agent chỉ đáng bỏ ra từ case 3 trở đi, khi câu hỏi cần bằng chứng thật hoặc cần thực hiện hành động. Đây chính là lý do nhóm thiết kế **Hybrid Flowchart** ở [hybrid_flowchart.mermaid](./hybrid_flowchart.mermaid): câu hỏi kiến thức chung đi đường Chatbot, câu hỏi dính dữ liệu khách đi đường ReAct Agent.

**Giới hạn còn tồn tại:**
- Agent chưa có Memory giữa các lượt hội thoại. Hỏi *"đơn DH20260715 còn đổi được không?"* rồi hỏi tiếp *"thế tạo yêu cầu đi"* thì lượt sau Agent không biết đang nói về đơn nào. Đây là ranh giới giữa Cấp 3 (Reactive) và Cấp 4 (Autonomous).
- Dữ liệu trong `src/tools.py` là giả lập tĩnh với mốc thời gian cố định `TODAY = 2026-07-28`, chưa nối vào hệ thống thật.
- Thời gian phản hồi phụ thuộc nhiều vào model. Model suy luận cho chất lượng Thought tốt hơn nhưng mỗi bước mất hàng chục giây, nên khi demo trực tiếp nên đổi sang model thường qua biến `LLM_MODEL`.
