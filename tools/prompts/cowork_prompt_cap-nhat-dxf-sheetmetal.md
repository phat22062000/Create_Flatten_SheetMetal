Dùng skill-creator để cập nhật skill **dxf-sheetmetal** (skill trên app). Chỉ sửa đúng 4 chỗ dưới đây, giữ nguyên mọi phần khác. Số dòng tính theo bản hiện tại (version 2026.11.03-1, 235 dòng). Sau khi sửa, đặt bản mới nhất làm bản hiện tại (current) và báo lại số dòng mới của 3 chỗ đã sửa/chèn.

## 1. Dòng 5 (metadata)
Đổi `version: "2026.11.03-1"` thành `version: "2026.11.04-1"`.

## 2. Dòng 159 (mục 9 Kegaki), thay thế toàn bộ dòng
Dòng cũ bắt đầu bằng "- Chi tiết hàn nằm sát mép ngoài của tấm nhận...". Thay bằng:

- Chi tiết hàn chỉ được bỏ kegaki khi MỌI cạnh của vết (footprint) đều trùng mép ngoài tấm nhận (định vị được theo mép). Còn bất kỳ cạnh vết nào nằm bên trong tấm (đầu mút ống/thanh, mặt xa của ống/thanh, mép tấm hàn) thì VẼ các cạnh đó; cạnh trùng mép tấm thì bỏ. Ống/thanh vuông không cắt laser vẫn tạo vết kegaki trên tấm laser nhận hàn. Ví dụ 26-065615 (khách 851): ống 30 sát mép đầu trái tấm nhưng đầu ống nằm cách mép trên tấm 26.8, phải vẽ 2 LINE (x = 30 và y = 38.2); lần đầu bỏ kegaki là sai.

## 3. Chèn thêm 1 dòng ngay sau dòng 41 (mục 2)
Dòng 41 là "  - Kiểm bằng số đo ảnh ở ≥ 2 hình chiếu...". Chèn ngay sau nó (cùng mức thụt đầu dòng):

  - Giá trị suy từ chuỗi (vị trí đầu ống/thanh, vết kegaki, mép) phải đo pixel kiểm ở ≥ 300 dpi trên ≥ 2 hình chiếu, sai số ≤ 1 mm. Lệch > 1 mm là dấu hiệu bỏ sót ghi chú nhỏ cạnh chân dim (3.2 thành ống, 9 độ dày...): xác định kích thước tổng bắt đầu từ mặt ngoài hay mặt trong thành ống trước khi cộng/trừ. Ví dụ 26-065615: 65 + 465 − (500 + 3.2) = 26.8, không phải 30 (kích thước 500 bắt đầu từ mặt dưới thành 3.2 ở đầu ống).

## 4. Chèn thêm 1 dòng ngay sau dòng 228 (mục 12)
Dòng 228 là "- Chuỗi kích thước: mọi chuỗi không cộng đủ tổng...". Chèn ngay sau nó:

- Kegaki: lập bảng (tấm nhận × chi tiết hàn lên): vẽ/bỏ, lý do, từng cạnh vết trùng mép tấm hay nằm trong tấm, số đo pixel kiểm ≥ 2 hình (≤ 1 mm). Không tấm nào có chi tiết hàn lên mà chưa xét.

Lưu ý: giữ nguyên tiếng Việt có dấu và định dạng markdown. Chỉ cập nhật skill này, không đụng skill khác (dxf-check, nc-sheetmetal...).
