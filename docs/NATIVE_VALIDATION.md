# Kiểm thử trên máy Adobe

Trạng thái phát hành 0.1: **chưa kiểm thử end-to-end bằng Adobe native**. Unit tests dùng mock hoặc simulation chỉ kiểm tra phần Python.

| Bài kiểm tra | Windows | macOS |
| --- | --- | --- |
| Worker chạy Python và tạo đúng trạng thái | Chưa chạy trên máy thật | Chưa chạy trên máy thật |
| Photoshop PSD nhỏ → PNG, đúng kích thước/alpha | Chưa kiểm thử | Chưa kiểm thử |
| PSD gốc giữ nguyên hash và layer | Chưa kiểm thử | Chưa kiểm thử |
| Từ chối nguồn PSD đang mở; không đóng tài liệu người dùng | Chưa kiểm thử | Chưa kiểm thử |
| PSD không hỗ trợ mode/bit depth báo lỗi rõ | Chưa kiểm thử | Chưa kiểm thử |
| AE render comp 2 frame với template có thật | Chưa kiểm thử | Chưa kiểm thử |
| AE thiếu footage/template báo lỗi | Chưa kiểm thử | Chưa kiểm thử |
| Tên file Unicode, khoảng trắng, dấu nháy | Chưa kiểm thử | Chưa kiểm thử |
| Timeout/Ctrl+C không tự chạy tiếp job không rõ trạng thái | Chưa kiểm thử | Chưa kiểm thử |
| Cowork nhìn thấy cùng thư mục và đọc được output | Chưa kiểm thử | Chưa kiểm thử |

Ghi kết quả thực tế và phiên bản phần mềm vào bảng khi chạy. Không đổi trạng thái thành đạt chỉ dựa trên việc script khởi chạy.

PNG export là composite của PSD. Kiểm tra layer visibility, alpha, kích thước và profile màu đúng với kỳ vọng. Với video, kiểm tra frame đầu/cuối, âm thanh, font/effect và thông số file trước khi gửi thành phẩm.
