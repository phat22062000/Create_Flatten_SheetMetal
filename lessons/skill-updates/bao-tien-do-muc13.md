# Đoạn bổ sung cho mục 13 của skill dxf-sheetmetal

Dán vào cuối mục 13 của skill trên app (skill trên app là bản gốc), sau dòng "Agent chính gộp bằng `merge_all.py`...".
Nếu muốn, sửa dòng đó: bỏ phần "rồi chạy dxf-check (bước 3a)" trong thời gian tạm không chạy dxf-check.

---
- Báo tiến độ lên trang giám sát theo `tools/sheetmetal_kit/progress_reporting.md` (công cụ ArtifactData, url trong file đó), áp cho mọi đơn, kể cả đơn ≤ 3 chi tiết (agent `<đơn>_S0`).
  - Agent chính: tạo đơn, agent và mã sau khi chia nhóm; cập nhật `phase` khi đổi bước. Mốc cuối là gộp xong file ALL (`mergedAt`). Không báo dxf-check.
  - Subagent: báo khi bắt đầu và khi xong từng mã (kèm `blank`, `flags` đúng dòng Flag mục 11.4), và khi xong nhóm. Agent chính đưa url, id và version vào prompt subagent.
  - Mã có Flag là "Chờ" trên trang; vẽ lại xong mà hết Flag thì tự thành "Đã Xong".
  - Báo tiến độ không được chặn công việc: ghi thất bại 2 lần thì bỏ qua và nêu trong báo cáo.
---
