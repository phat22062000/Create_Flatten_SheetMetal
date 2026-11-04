# Báo tiến độ lên trang "Giám sát DXF Sheetmetal"

Trang: https://claude.ai/artifact/7ZAaeJxLEvtt5rZKUSoA8s (riêng tư, chủ trang chia sẻ cho nhóm qua menu Share).
Agent ghi bằng công cụ `ArtifactData` của Claude Code (nạp bằng ToolSearch `select:ArtifactData`), luôn truyền `url` của trang ở trên.
Báo tiến độ dừng ở bước gộp file ALL (`merge_all.py`). dxf-check tạm thời không chạy và không báo.

## Quy tắc chung
- Thời gian: chuỗi UTC dạng ISO, lấy bằng `date -u +%Y-%m-%dT%H:%M:%SZ`. Không tự đoán giờ.
- Mã bản vẽ: 6 số (`060100`, không ghi `26-`). Số đơn ghi đúng như trên CAD依頼書 (`521104`, `521102-16`).
- Id tài liệu: đơn `<đơn>`, mã `<đơn>_<mã>`, agent `<đơn>_main` (agent chính) và `<đơn>_S1`, `<đơn>_S2`... (subagent).
- Mỗi tài liệu chỉ có một người ghi (xem bảng dưới), để không ghi đè lẫn nhau.
- Ghi vào tài liệu đã có thì PHẢI truyền `if_version` bằng `version` của lần ghi hoặc đọc gần nhất. Kết quả mỗi lần ghi trả về version mới; giữ lại số đó cho lần ghi sau. Tài liệu mới tạo có version 1.
- Ghi lỗi do lệch version thì `get` lại tài liệu đó rồi ghi lại. Không bỏ `if_version`.
- Nhiều tài liệu cùng lúc thì dùng `action: "batch"` (một lần duyệt, tối đa 50 lệnh).
- Báo tiến độ không được chặn công việc chính. Ghi thất bại 2 lần thì bỏ qua, ghi vào note và báo agent chính.

## Ai ghi gì
| Tài liệu | Người ghi | Trường |
|---|---|---|
| `orders/<đơn>` | Agent chính | `order`, `customer`, `material`, `receivedAt`, `partOrder` (mã theo thứ tự Excel), `mergedAt`, `allFile` |
| `agents/<đơn>_main` | Agent chính | `order`, `kind: "main"`, `name`, `phase`, `state` (`running`/`done`/`failed`), `startedAt`, `heartbeatAt`, `finishedAt` |
| `agents/<đơn>_S<n>` | Agent chính tạo, subagent đó cập nhật | `order`, `kind: "sub"`, `name` ("Subagent n"), `codes`, `done`, `current`, `state`, `startedAt`, `heartbeatAt`, `finishedAt`, `note` |
| `parts/<đơn>_<mã>` | Agent chính tạo, subagent phụ trách cập nhật | `order`, `code`, `kind` (`phang`/`uon`/`hop`, thêm `+dxf`), `agent` (id agent), `status` (`queued`/`running`/`built`), `blank` ("W x H"), `flags`, `startedAt`, `finishedAt`, `rev` |
| `reviews/...` | Người kiểm trên trang | Agent KHÔNG ghi |

Trạng thái trang tự suy ra:
- Mã `built` không Flag là Đã Xong. Mã `built` có Flag là Chờ.
- Đơn đang ở trạng thái Đang tạo cho tới khi có `mergedAt`. Sau đó đơn là Đã Xong nếu mọi mã Đã Xong, còn lại là Chờ.
- Subagent `running` quá 10 phút không cập nhật `heartbeatAt` thì hiện "Mất tín hiệu".

## Các mốc báo
1. **Agent chính, sau khi lập `order_context.json` và chia nhóm** (một batch, tạo mới nên không cần `if_version`):
   - `orders/<đơn>`;
   - `agents/<đơn>_main` với `phase: "Chia nhóm xong, giao subagent"`;
   - mỗi `agents/<đơn>_S<n>` với `state: "running"`, `codes`, `done: []`, `current: null`, `startedAt`;
   - mỗi `parts/<đơn>_<mã>` với `status: "queued"`, `agent`, `kind`, `flags: []`, `rev: 1`.

   Agent chính đưa vào prompt của từng subagent: `url`, id agent của nó, danh sách id mã, và version hiện tại (đều là 1).
2. **Subagent bắt đầu một mã** (batch 2 lệnh `update`):
   - `parts/<đơn>_<mã>`: `{status: "running", startedAt}`;
   - `agents/<đơn>_S<n>`: `{current: "<mã>", heartbeatAt}`.
3. **Subagent xong một mã** (sau khi ghi `spec_<mã>.json` và `note_<mã>.md`, batch 2 lệnh `update`):
   - `parts/<đơn>_<mã>`: `{status: "built", blank, flags, finishedAt}`. `flags` là đúng các dòng Flag trong spec (dạng mục 11.4, ví dụ `"1. Thiếu kích thước (...)"`); không có Flag thì `[]`;
   - `agents/<đơn>_S<n>`: `{done: [...các mã đã xong], current: null, heartbeatAt}`.
4. **Subagent làm lâu (> 5 phút cho một mã):** cập nhật `heartbeatAt` của agent mình giữa các bước (render, dựng spec, overlay) để trang không báo mất tín hiệu.
5. **Subagent xong nhóm:** `agents/<đơn>_S<n>`: `{state: "done", current: null, finishedAt, heartbeatAt}`. Dừng giữa chừng thì `state: "failed"` và ghi lý do vào `note`.
6. **Agent chính đổi bước:** `agents/<đơn>_main`: `{phase, heartbeatAt}`, ví dụ `"Chờ subagent dựng spec"`, `"Kiểm mặt vẽ và hướng"`, `"Gộp file ALL"`.
7. **Agent chính gộp xong ALL (mốc cuối):**
   - `orders/<đơn>`: `{mergedAt, allFile: "<đơn>_ALL.dxf"}`;
   - `agents/<đơn>_main`: `{phase: "Đã gộp file ALL", state: "done", finishedAt}`.

   Nếu khi kiểm lại agent chính sửa Flag của mã nào thì cập nhật `flags` của mã đó (`get` trước để có version).

## Đơn ≤ 3 chi tiết (làm tuần tự)
Agent chính tạo thêm `agents/<đơn>_S0` với `name: "Agent chính (tuần tự)"`, `kind: "sub"`, rồi tự báo theo mốc 2, 3 và 5 cho agent này.

## Vẽ lại mã đang Chờ
Sau khi người dùng bổ sung dữ kiện:
1. `get` tài liệu `parts/<đơn>_<mã>`.
2. Cập nhật `{status: "running", startedAt, rev: rev + 1}`.
3. Vẽ xong thì cập nhật `{status: "built", flags (mới, có thể []), finishedAt}`.
4. Gộp lại ALL thì cập nhật `mergedAt` của đơn.

## Ví dụ (subagent 1 của đơn 521104 xong mã 060100)
```json
{"action": "batch", "url": "https://claude.ai/artifact/7ZAaeJxLEvtt5rZKUSoA8s", "writes": [
  {"op": "update", "collection": "parts", "doc_id": "521104_060100", "if_version": 2,
   "data": {"status": "built", "blank": "320 x 145", "flags": [], "finishedAt": "2026-11-04T13:05:12Z"}},
  {"op": "update", "collection": "agents", "doc_id": "521104_S1", "if_version": 3,
   "data": {"done": ["060100"], "current": null, "heartbeatAt": "2026-11-04T13:05:12Z"}}
]}
```
