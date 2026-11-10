# Adobe Background Skills — BinhTH

Plugin dành cho **Claude Desktop / Cowork**, đi kèm worker chạy trên máy có After Effects và Photoshop. Claude nhận yêu cầu, tạo job trong thư mục được chia sẻ, rồi đọc tiến độ và kết quả.

**v0.1 / bản nền mới:** chưa lấy lại được các script chạy nền trước đây của BinhTH. Đây là khung đóng gói và hai tác vụ mẫu, **chưa phải bản di chuyển đầy đủ bộ cũ**. Các kiểm tra Python không thay thế việc chạy thử bằng Adobe thật.

## Có gì trong bản này?

| Thành phần | Chức năng |
| --- | --- |
| Plugin marketplace | Cài skill vào Cowork bằng URL GitHub |
| `ae-render` | Render một comp đã có trong AEP qua `aerender` |
| `ps-export-png` | Mở PSD, xuất bản hiển thị tổng hợp thành PNG; không lưu đè PSD |
| Local worker | Xử lý tuần tự, ghi trạng thái và log, kiểm tra file đầu ra |
| Simulation | Kiểm tra luồng job mà không gọi Adobe; kết quả luôn ghi `simulated` |
| Hướng dẫn port | Bổ sung lại từng script cũ sau khi có nguồn và job mẫu |

Chưa có tác vụ sửa nội dung comp, relink footage, thay smart object, export từng layer, hoặc đọc/chỉnh cấu trúc AEP/PSD tùy ý. Không nhận câu lệnh shell hay JSX tự do từ file job.

Photoshop hỗ trợ PSD/PSB ở RGB hoặc grayscale, 8/16-bit; giữ alpha đang có và không tự đổi mode/bit depth. Lưu rồi đóng **tất cả** tài liệu Photoshop trước khi chạy. AE hỗ trợ AEP/AEPX và output movie hoặc image sequence theo template có trên máy.

## Cách hoạt động

Cowork đọc/ghi thư mục `AdobeJobs` được người dùng cấp quyền. Một worker Python được mở riêng trên máy Windows/macOS đọc job, gọi Adobe cục bộ và ghi kết quả vào cùng thư mục. Cài plugin không tự cài Python, Adobe hoặc tự khởi động worker.

Không giả định terminal của một phiên Cowork là terminal trên máy có Adobe. Cấu hình này dùng thư mục chung để tránh phụ thuộc vị trí thực thi của phiên Cowork. Hãy kiểm tra một file đánh dấu xuất hiện ở cả hai phía trước khi gửi job.

After Effects có renderer dòng lệnh. Photoshop vẫn là ứng dụng desktop được điều khiển bằng scripting; cửa sổ có thể xuất hiện. Đây không phải Photoshop chạy headless trong cloud. Máy cần bật, đăng nhập và không sleep trong khi xử lý.

## 1. Setup

- Windows hoặc macOS; Python **3.10+**; Adobe được cài và kích hoạt hợp lệ.
- Với AE: xác định đúng đường dẫn `aerender`, comp và output module template. Font, effect, plugin và footage phải có trên máy chạy.
- Với Photoshop: mở ứng dụng một lần để hoàn tất các hộp thoại khởi động; lưu và đóng các tài liệu đang làm trước khi chạy batch.
- Tải/clone repository về máy. Không đặt kho mã và file công việc vào cùng một thư mục.

Windows PowerShell, tại thư mục repo:

```powershell
Copy-Item config.example.json config.local.json
py -3 worker/queue_worker.py --root C:/AdobeJobs --init
```

Sửa `config.local.json` theo phiên bản Adobe trên máy. Đường dẫn `aerender` trong ví dụ chỉ là mẫu, không tự dò hoặc tải Adobe. Không cần `aerender` nếu chỉ dùng Photoshop.

macOS Terminal:

```bash
cp config.example.json config.local.json
python3 worker/queue_worker.py --root "$HOME/AdobeJobs" --init
```

Trên macOS, sửa `aerender` thành đường dẫn thực tế, chẳng hạn `/Applications/Adobe After Effects 2026/aerender`, và `photoshop_app_name` thành đúng tên Photoshop đã cài. Hệ điều hành có thể hỏi quyền Automation khi worker gọi Photoshop lần đầu.

## 2. Cài plugin vào Cowork

1. Claude Desktop → **Customize → Plugins → Add → Add marketplace**.
2. Nhập URL GitHub của repository này.
3. Cài plugin **adobe-background** từ marketplace **binhth-adobe**.
4. Với repo private, mỗi đồng nghiệp cần quyền đọc repo và kết nối GitHub tương ứng trong Claude.
5. Trong phiên Cowork, cấp quyền truy cập thư mục `AdobeJobs`. Kiểm tra Cowork nhìn thấy `inputs`, `queue`, `status`, `outputs` và `logs`.

Tên menu có thể khác theo phiên bản hoặc chính sách workspace. Tài liệu: [Cowork plugins](https://claude.com/docs/cowork/guide/plugins).

## 3. Mở worker và giao việc

Đặt **bản sao** tài liệu vào `AdobeJobs/inputs`. Với AE, dùng bản project đã Collect Files hoặc bảo đảm đường dẫn footage vẫn hợp lệ; copy riêng AEP không tự mang theo footage.

**Chuẩn bị AEP:** mở bản sao, làm trống Render Queue rồi lưu bản sao trước khi gửi job. Worker dùng `-comp` để tạo mục render mới. Nếu giữ các output module cũ trong queue, AE có thể ghi thêm output theo đường dẫn đã lưu trong project; worker không phân tích AEP để tự kiểm tra điều này. Không dùng bản đang làm việc làm input batch.

Mở terminal riêng trên máy có Adobe và để cửa sổ này chạy:

```powershell
py -3 worker/queue_worker.py --root C:/AdobeJobs --config config.local.json
```

macOS:

```bash
python3 worker/queue_worker.py --root "$HOME/AdobeJobs" --config config.local.json
```

Trong Cowork, dùng các prompt mẫu:

> Dùng adobe-background. Thư mục công việc là AdobeJobs vừa được cấp quyền. Xuất các file PSD trong inputs thành PNG, mỗi file một job. Theo dõi trạng thái, kiểm tra kết quả và báo file nào lỗi. Giữ nguyên file gốc.

> Dùng adobe-background. Render comp Main của inputs/sample.aep, frame 0 đến 29, thành preview.mov. Output module template đã kiểm tra trên máy là [tên template]. Tạo job mới và theo dõi kết quả.

Với việc chưa được hỗ trợ, Claude phải báo thiếu action tương ứng. Xem [cách bổ sung workflow cũ](docs/PORTING_EXISTING_WORKFLOWS.md).

## Job và kết quả

- `queue/<id>.json`: yêu cầu; ghi file tạm rồi rename sau khi ghi xong.
- `status/<id>.json`: trạng thái do worker ghi.
- `outputs/<id>/`: file kết quả riêng cho từng job.
- `logs/`: log chẩn đoán của worker/Adobe.
- Các thư mục claim/archive nội bộ do worker quản lý; không sửa khi worker đang chạy.

Xem [schema và ví dụ](plugins/adobe-background/skills/adobe-background/references/jobs.md). Mỗi job phải có ID mới. Một ID đã xử lý không được chạy lại; sửa lỗi rồi tạo job mới. Không dùng lại ID của simulation cho job thật.

Nếu công cụ file của Cowork không hỗ trợ rename an toàn, lưu job ngoài `queue` rồi gửi từ terminal trên máy:

```powershell
py -3 worker/submit_job.py --root C:/AdobeJobs --job examples/ps-export-png.json
```

Chỉnh file ví dụ thành input/ID thực tế trước khi gửi. macOS dùng `python3` thay `py -3`. Helper chỉ gửi job; worker vẫn phải đang chạy.

Worker kiểm tra tiến trình và file đầu ra. `succeeded` không thay thế visual QA: vẫn xem PNG hoặc một vài frame/video để kiểm tra đúng nội dung, font, màu và alpha. Đuôi `.mp4` không tự chọn codec H.264; định dạng thực tế phụ thuộc output module template của AE.

## Kiểm tra cài đặt

Chạy kiểm tra gói và unit tests tại repo:

```bash
python -m unittest discover -s tests -v
python scripts/check_package.py
```

Để kiểm tra hàng đợi mà không gọi Adobe, dùng thư mục test riêng, đặt một input phù hợp cùng job mẫu trong `queue`, rồi chạy:

```powershell
py -3 worker/queue_worker.py --root C:/AdobeJobs-Test --once --simulate
```

Simulation chỉ kiểm tra luồng và schema. Tiếp theo chạy một PSD nhỏ hoặc comp 1–2 frame bằng Adobe thật trước khi giao batch lớn. Xem [checklist kiểm thử native](docs/NATIVE_VALIDATION.md).

## Dừng và xử lý lỗi

Dùng `Ctrl+C` để dừng worker. Nếu một thao tác Adobe đang chạy hoặc timeout, kiểm tra ứng dụng và log trước khi khởi động lại; tiến trình con/ứng dụng có thể vẫn đang xử lý. Worker không tự đóng hay force-kill các phiên Adobe đang làm việc của người dùng và không tự retry job bị gián đoạn.

Lock giữ một worker cho mỗi thư mục. Nếu máy tắt đột ngột, chỉ xóa lock cũ sau khi xác nhận không còn worker hay Adobe job tương ứng. Không xóa trạng thái để ép chạy lại một ID. Khi có tình trạng không xác định, xử lý thủ công rồi tạo ID mới; xem thông báo cụ thể từ worker.

Worker sử dụng thêm `processing`, `archive`, `rejected`, `.worker.lock` và `blocked.json`. Khi có `blocked.json`, xác nhận Adobe đã dừng, xem log/output, giữ nguyên trạng thái `unknown`; sau đó mới gỡ marker để tiếp tục. Không dọn các thư mục nội bộ trong lúc worker hoạt động.

## Chia sẻ qua GitHub

Repo nên để **private** cho nhóm trước khi đã kiểm thử Adobe trên các máy thực tế. Không commit file dự án, credential, cấu hình máy, font/plugin thương mại hay output.

Nếu chưa có remote, chủ repo có thể dùng GitHub CLI đã đăng nhập, tại thư mục repo:

```bash
gh repo create adobe-background-skills --private --source=. --remote=origin --push
```

Sau đó cấp quyền repo cho đồng nghiệp trên GitHub và gửi URL. Cài plugin và tải worker là hai bước riêng. Đã cấu hình CI cho Python trên Windows/macOS/Linux; CI không chạy Adobe.

## Nguồn tham chiếu

- [Claude plugin structure](https://claude.com/docs/plugins/build)
- [Claude marketplace](https://code.claude.com/docs/en/plugin-marketplaces)
- [Adobe aerender](https://helpx.adobe.com/after-effects/desktop/render-and-export/automate-rendering/automated-rendering-network-rendering.html)
- [Photoshop scripting](https://helpx.adobe.com/ie/photoshop/using/scripting.html)

Owner: **BinhTH — MnD [VNGGAMES]**. Không kèm tài sản dự án nội bộ hoặc thành phần Adobe độc quyền.
