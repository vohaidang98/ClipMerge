# ClipMerge 2.0.1

Giao diện 5 tab được làm lại theo các ảnh MMerge v2.0.7, đối chiếu tên hàm, cấu hình và chuỗi mô tả còn đọc được trong EXE v2.0.7/v3.0.0. File gốc là bản Nuitka đã biên dịch, không phải nguồn Python có thể khôi phục nguyên vẹn.

Chạy `ClipMerge-Setup-2.0.1.exe` hoặc `ClipMerge-Setup.exe` để cài/cập nhật. Bản chạy trực tiếp: `ClipMerge.exe`, giữ nguyên `_internal` và `bin` bên cạnh. Không cần cài Python hoặc FFmpeg trên máy sử dụng.

Nút Đảo ngẫu nhiên trong TASK BUILDER và MERGE LITE đảo các cột có video mỗi lần bấm, không cần chọn cột trước. Mỗi lượt bảo đảm đổi thứ tự nếu cột có ít nhất hai video khác nhau.

## Sử dụng

- **MERGE HUB:** nhấp đúp vào Tasklist, kéo thả TXT hoặc dùng Tệp → Thêm Task. Nút Ghép chạy tất cả; Ghép Tasklist chạy các Task đã chọn. Mỗi TXT tạo một MP4 cùng tên. Bảng hiển thị rõ Kiểm tra → Mã hóa n/N → Nối cuối → Kiểm tra kết quả → Hoàn tất.
- **TASK BUILDER:** thêm file bằng nút `+`, thư mục bằng `…`, kéo thả hoặc menu chuột phải. Đặt số clip từ mỗi nhóm V0–V3. Random áp dụng riêng từng nhóm; Mixed V2 + V3 xen kẽ hai nhóm cuối. Đặt tên, số bắt đầu và số Task rồi Xuất TXT.
- **MERGE LITE:** mỗi cột có nội dung được ghép thành một video riêng, lần lượt đánh số từ chỉ số đã đặt. Có cấu hình riêng và tùy chọn sao chép nguồn vào thư mục tạm của hệ thống trước khi xử lý; tốc độ phụ thuộc ổ lưu thư mục tạm.
- **AUDIO REPLACE:** thêm video/nhạc, chọn Match theo Tên hoặc Ghép theo Thứ tự. Tên được so khớp không gồm đuôi file. Nhạc ngắn được bù im lặng, nhạc dài được cắt theo video.
- **VIDEO SELECTOR:** nhập số clip cố định hoặc khoảng, thời lượng/sai số với đơn vị giây/phút/giờ, số danh sách và giới hạn thử. Không dùng lại loại các clip đã dùng trong các lần tạo trước; Có dùng lại cho phép sử dụng clip ở nhiều kết quả trong một lần tạo. Có thể xuất TXT chung hoặc từng Task.

## Cấu hình MERGE HUB

Start/Length **chỉ áp dụng Preview trên dòng thời gian của Task**; không cắt nội dung khi ghép chính. Preview tạo đoạn MP4 ngắn rồi mở bằng trình phát mặc định.

WxH, FPS, V_bitrate, A_bitrate, A_sample, tỷ lệ/preset, Scale có thể thay đổi. Letterbox giữ tỉ lệ và thêm viền; Crop lấp đầy rồi cắt mép; Stretch kéo giãn; Default ở MERGE LITE dùng Letterbox.

Zoom nhận `113` hoặc `113%` (phóng 113%), cũng nhận hệ số `1.13`. Gamma nhận giá trị như `1.2`. Noise nhận `3`, `3,allf=ut`, `alls=3:allf=t+u`, hoặc `c0=2,c1=2`.

Zoom/Gamma/Noise có thể thêm `|` và quy tắc bỏ qua: `113 | +1,3,-3`. H_flip và Skip nhận quy tắc trực tiếp. `+n`: bỏ n clip đầu; `-n`: bỏ n clip cuối; `3`: bỏ clip thứ 3; `2-4`: bỏ các clip 2 đến 4. Skip chung bỏ cả Zoom, H_flip, Gamma, Noise. Chỉ số ngoài độ dài Task được bỏ qua.

Normalize Audio đo peak sau khi chuyển về stereo/tần số đích, rồi điều chỉnh gain tới Target dBFS. Chuột phải vào Target để đổi mức. Đây là chuẩn hóa đỉnh, không phải cân LUFS. Thao tác đo cần đọc thêm một lượt âm thanh.

GPU Mode: cuda/nvdec dùng NVIDIA, qsv dùng Intel, dxva2 dùng AMD. Các chế độ CPU + GPU giải mã bằng CPU và mã hóa bằng GPU tương ứng. Cần phần cứng/driver phù hợp. Các luồng xử lý đã kiểm tra bằng CPU; chưa kiểm tra trực tiếp tất cả phần cứng GPU.

Xuất Timeline tạo `<tên>_timeline.txt` chứa thời gian bắt đầu/kết thúc từng clip. Xuất tại Thư Mục Task dùng thư mục chứa TXT. Tạo Thư mục con tạo thư mục theo tên Task.

## File và tiến độ

File nguồn được giữ nguyên. Nạp TXT giữ thứ tự và mọi lần xuất hiện của clip. File xuất trùng tên bị chặn. Tác vụ không báo hoàn tất nếu có lỗi đọc hoặc clip bị thiếu nội dung. Clip nguồn bị hỏng cần được thay thế; ứng dụng không tự khôi phục dữ liệu hỏng.

Tự động dọn Temp xóa trung gian sau khi xử lý. Bỏ chọn để giữ Temp; Dọn thư mục Temp chỉ xóa các thư mục có dấu sở hữu do ClipMerge tạo trong phiên hiện tại. File trung gian không phải video ghép hoàn chỉnh.

Loại trừ/Làm trống chỉ thay đổi danh sách trong giao diện. Xóa Task và Tự động xóa Task đưa **TXT** vào Thùng rác, có xác nhận; không xóa video nguồn. Di chuyển Task không ghi đè file đã có ở đích.

Các cấu hình được nhớ tại `%LOCALAPPDATA%\ClipMerge\settings.json`. Tệp → Nhật ký mở `%LOCALAPPDATA%\ClipMerge\logs`. Log chỉ lưu trên máy; không gửi tự động.

## Nguồn và đóng gói

`app.py`: điểm khởi chạy. `classic_ui.py`: giao diện và điều phối 5 tab. `engine.py`: FFmpeg/kiểm tra đầu ra. `hub_utils.py`: thời gian, Skip, Noise, thao tác Task. `support_ui.py`: các thao tác danh sách và worker dùng lại từ phiên bản trước.

Chạy mã nguồn: `python app.py`. Đóng gói với PyInstaller, thêm `ClipMerge.ico`, `ClipMerge.png` và thư mục `tkdnd` vào tài nguyên. Dùng `version.txt` cho thông tin phiên bản; sau khi dựng, chép EXE và `_internal` về cạnh `installer.iss`, giữ `bin`, rồi biên dịch `ISCC installer.iss` bằng Inno Setup 6.

Cập nhật tự động (từ 2.1.0): app đọc `version.json` trong thư mục cập nhật trên mạng LAN (chọn ở lần đầu bấm Trợ giúp > Kiểm tra cập nhật; lưu ở `%APPDATA%\ClipMerge\update.json`), kiểm tra SHA-256 trước khi cài. Chỉ bản đã kích hoạt mới cập nhật được. Kích hoạt: Trợ giúp > Kích hoạt, mã nhập hiện dấu `*`; trong code chỉ có mã băm (`licensing.py`, tạo bằng `python tools\make_hash.py`). Chưa kích hoạt thì khoá Ghép của MERGE HUB. Tạo thư mục phát hành: `python tools\make_release.py <file cài đặt> <phiên bản> D:\Code\CAP_NHAT\ClipMerge "ghi chú"`; chỉ cho tài khoản quản trị quyền ghi vào thư mục chia sẻ.

FFmpeg GPLv3 và các thư viện đi kèm: xem `licenses`. TkDND có bản thông báo bản quyền/điều khoản gốc trong `licenses/TkDND-license-and-notices.tcl`. Không phân phối EXE của MMerge, không dùng dịch vụ kích hoạt/cập nhật của MMerge.
