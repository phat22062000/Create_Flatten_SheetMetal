# Skills - đồng bộ từ app Claude

Bản gốc của skill là bản trên app/tài khoản Claude. Thư mục này chỉ là bản lưu trên máy (dxf-sheetmetal, dxf-check).

CÁCH CẬP NHẬT (sau khi sửa skill trên app):
1. Trên app, bấm Save skill (làm cho từng skill vừa đổi). File tải vào Downloads, tên SKILL.md hoặc *.skill.
2. Bấm đúp Dong-bo-skill.bat trong thư mục này.
3. Đọc kết quả: version cũ -> mới, danh sách dòng thay đổi (số dòng của bản mới). Chi tiết đầy đủ ở last_import.txt.

Script tự: giải nén đúng (kể cả file .md thực chất là zip), kiểm tra version ở dòng 5, chọn bản version cao nhất, sao lưu bản cũ vào backup\<tên>\, ghi UTF-8 không BOM, chuyển file đã xử lý sang imported\.
Không bao giờ ghi đè bằng bản cũ hơn (trừ khi chạy với -Force). Thêm -DryRun để xem trước mà không ghi gì.

Kiểm tra script: bấm Kiem-tra-dong-bo-skill.bat (chạy trên dữ liệu giả trong thư mục tạm, không đụng file thật).

skill-sync.ps1 và dist\ là quy trình cũ (đẩy bản máy lên tài khoản), không dùng nữa.
