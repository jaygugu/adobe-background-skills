# Bổ sung các workflow đã dùng trước đây

Bản v0.1 chưa có nguồn script cũ. Không coi hai action mẫu là bằng chứng rằng các tác vụ cũ đã được đóng gói xong.

## Bộ đầu vào cần có cho từng workflow

1. Script `.jsx`, `.ps1`, `.py` hoặc lệnh thực tế từng chạy; nếu chỉ có cuộc chat, trích phần code và quy trình đúng phiên bản cuối.
2. Một file input tối giản có thể chia sẻ và một kết quả đúng để đối chiếu. Tách asset nội bộ khỏi repo mã nguồn.
3. OS, phiên bản AE/Photoshop, các plugin/font/template cần thiết.
4. Những thao tác đã xác nhận: ví dụ đổi text, thay footage, resize comp, export layer hoặc thay smart object. Không suy ra các chức năng này từ tên skill.

## Quy trình port

- Rà đường dẫn cứng và credential; đưa cấu hình máy vào `config.local.json`.
- Tách tham số input/output khỏi logic JSX; thao tác trên bản sao và kiểm tra dữ liệu nguồn đang mở.
- Đặt tên action rõ ràng; thêm validator có danh sách tham số hữu hạn trong worker.
- Thêm adapter gọi code đã review; không cho file job chứa shell hoặc code tự do.
- Ghi trạng thái riêng của ứng dụng khi dispatch bất đồng bộ. Exit code của launcher không đủ chứng minh Adobe đã xong.
- Kiểm thử input/đường dẫn có dấu, khoảng trắng; file lỗi; thiếu font/footage; output đã có; timeout; tài liệu đang mở và nguồn không được ghi đè.
- Chạy thử bằng đúng Adobe native rồi ghi OS, phiên bản app, ngày kiểm tra và kết quả. Chỉ sau đó cập nhật bảng hỗ trợ và skill.

Sau mỗi action mới, cập nhật cùng lúc README, skill, job reference, tests và version plugin. Không lưu credentials hoặc mẫu dự án nội bộ vào lịch sử Git.
