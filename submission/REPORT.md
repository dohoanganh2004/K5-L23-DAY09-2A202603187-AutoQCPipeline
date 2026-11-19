# Báo cáo Day 09 — Đỗ Hoành Anh, 2A202603187

## 1. Kết luận trước
Pipeline kết luận **Hold**. Lô có 224 ảnh, sau khi loại ảnh hỏng, trùng và rò rỉ từ tập test còn 202 ảnh được xuất ra dataset.

Hold vì không còn lỗi bắt buộc nào, nhưng 38/202 ảnh (18,8%) vẫn còn cảnh báo, vượt ngưỡng 10% của cổng. Hàng đợi người duyệt có 125 ảnh trong khi ngân sách chỉ 80 ảnh, nên một phần cảnh báo chưa ai xem. Phần lớn cảnh báo còn lại là `POSSIBLE_FALSE_POS` và `POSSIBLE_LOOSE_BOX`, hai loại không phụ thuộc ngưỡng `conf` nên calibrate không làm giảm được.

## 2. Lỗi và phân việc
Nguyên tắc chia việc: lỗi cú pháp chỉ có một cách sửa an toàn thì để máy (autofix) làm, còn lỗi liên quan đến ý nghĩa thì máy chỉ nghi ngờ và chuyển cho người.

| Mã lỗi | Số lượng | Ai xử lý | Vì sao |
|---|---:|---|---|
| `BAD_FORMAT`, `BAD_CLASS_ID`, `BOX_ZERO`, `DUP_BOX` | 20 dòng | Máy: xoá dòng | Lỗi cú pháp, không có cách sửa nào khác |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy: cắt box về trong ảnh | Cắt lại; nếu không còn diện tích thì xoá |
| `BAD_CLASS_NAME` | 1 file | Máy: ghi lại `names` trong `data.yaml` | Tên lớp sai so với cấu hình |
| `DUP_IMAGE_*`, `LEAK_TEST`, `CORRUPT_IMAGE`, `BAD_SIZE` | 22 ảnh | Máy: loại khỏi lô | Ảnh trùng, trùng tập test, hỏng hoặc quá nhỏ |
| `MISSING_LABEL_FILE` | 6 ảnh | Người | Máy không được tự bịa nhãn |
| `POSSIBLE_MISSING` | 52 ảnh | Người | Model thấy vật mà nhãn không có, cần nhìn ảnh để xác nhận |
| `POSSIBLE_FALSE_POS` | 27 ảnh | Người | Box nhãn có thể thừa, máy chỉ nghi ngờ |
| `POSSIBLE_LOOSE_BOX` | 24 ảnh | Người | Box lỏng hay lệch, phải chỉnh bằng mắt |
| `POSSIBLE_WRONG_CLASS` | 18 ảnh | Người | Nhầm car/truck/bus là lỗi ý nghĩa, model cũng có thể nhầm |
| `EMPTY_LABEL` | 12 ảnh | Người | Không biết là ảnh nền thật hay quên gán nhãn |
| `BOX_TINY`, `BOX_HUGE`, `CLASS_RARE` | 4 + 3 + 1 ảnh | Người | Chỉ là cảnh báo về kích thước và phân bố |

`05_review_queue.csv` xếp ảnh theo điểm ưu tiên, tính từ trọng số của từng loại cảnh báo trong `configs/pipeline.yaml`. Ảnh chưa có nhãn (`NEEDS_LABEL`) có trọng số cao nhất nên nằm ngay đầu hàng, sau đó là ảnh có nhiều cảnh báo nặng như nhầm lớp hoặc thiếu box. Ngân sách 80 ảnh nghĩa là người chỉ xem 80 ảnh đầu hàng đợi, 45 ảnh cuối không được xem.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **12** | `DUP_IMAGE_NEAR`: P 1,00 → 1,00; R 0,50 → 0,67 | Ngưỡng này dẫn tới xoá ảnh nên ưu tiên precision, mà precision vẫn 1,00 ở mọi mức thử. 12 nằm trong khoảng ổn định và bắt thêm ảnh gần trùng so với 2. Không chọn 16 vì sát mức 20, nơi kết quả sụp. |
| `second_opinion.conf` | 0,25 | **0,6** | `WRONG_CLASS`: P 0,56 → 0,62; R giữ 0,83. `MISSING`: P 0,50 → 0,57; R giữ 1,00. `LOOSE_BOX`: P 0,29 → 0,20; R 0,40 → 0,20 | Đây là cảnh báo cho người xem nên ưu tiên recall: 0,6 là mức cuối cùng mà `MISSING` còn bắt đủ, từ 0,7 trở lên bắt đầu bỏ sót. Hàng đợi nhờ đó giảm từ 145 xuống 125 ảnh. Cái giá là `LOOSE_BOX` kém đi. |

**Chỗ calibration có thể đánh lừa:** bộ calib chỉ có 39 ảnh nên nhiều ô chỉ có vài lỗi chèn, số liệu nhảy theo từng ca. Ví dụ `WRONG_CLASS` chỉ có 6 ca, nên việc precision lên 1,00 ở `conf` 0,8 chưa đủ để kết luận 0,8 tốt hơn. Với `phash_dist`, tôi không chỉ tin bảng calib mà mở xem các cặp ảnh bị cho là trùng trong `raw`: số ảnh bị loại ở bước 1 tăng từ 19 lên 22, và cả các cặp có phash cao nhất (6 và 10) đều là ảnh trùng thật, nên ngưỡng 12 không xoá nhầm ảnh tốt.

## 4. Cửa chặn và điều pipeline không bắt được
**Gate chặn đúng.** Chạy pipeline với `--budget 0` (không có người duyệt nên 6 ảnh thiếu file nhãn không ai gán) cho kết quả **Rework**: còn 6 lỗi bắt buộc, mã thoát 20, và dataset không được xuất. Khi có người duyệt thì các ảnh đó được gán nhãn, hết lỗi bắt buộc và kết luận chuyển sang Hold. Như vậy cổng phân biệt được lỗi bắt buộc (Rework) với cảnh báo còn nhiều (Hold).

**Điểm mù.** Theo bảng calibration trên bộ calib:
1. **Box lỏng:** `POSSIBLE_LOOSE_BOX` chỉ đạt precision và recall 0,20 ở `conf` 0,6, tức chỉ bắt được 1 trong 5 ca đã chèn, nên phần lớn box lỏng lọt qua.
2. **Ảnh trùng bị biến đổi mạnh:** ở `phash_dist` 12, recall `DUP_IMAGE_NEAR` chỉ 0,67 (4 trong 6 ca). Tăng ngưỡng lên 20 còn tệ hơn vì ảnh trùng từng byte cũng bị bỏ sót, nên không ngưỡng nào bắt hết.
3. **Nhầm lớp:** `POSSIBLE_WRONG_CLASS` luôn lọt 1 trong 6 ca ở mọi `conf`. Máy chỉ nghi ngờ qua model, nên nếu model cũng nhầm giống nhãn thì không ai báo.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Train trên Colab (T4), mô hình `yolo26n`, 20 epoch, 2 seed (0 và 1), đánh giá trên tập test 100 ảnh. Bản `clean` là bản nháp vì kết luận pipeline là Hold.

| Biến thể | Số ảnh train | Số seed | mAP50 (TB ± độ lệch) | mAP50-95 (TB ± độ lệch) |
|---|---:|---:|---|---|
| raw | 224 | 2 | 0,726 ± 0,000 | 0,512 ± 0,004 |
| clean | 202 | 2 | 0,701 ± 0,025 | 0,487 ± 0,008 |

mAP50 của clean thấp hơn raw 0,025, gần bằng độ lệch giữa hai seed của chính clean (0,718 và 0,683). Chỉ có 2 seed và 100 ảnh test nên chênh lệch này nằm trong nhiễu, chưa thể nói dữ liệu sau pipeline tốt hơn hay kém hơn dữ liệu gốc. Chỗ giảm rõ nhất là lớp `truck` (AP50 trung bình 0,65 ở raw, 0,54 ở clean), nhưng hai seed của clean cũng lệch nhau nhiều ở lớp này (0,59 và 0,49).

Vài giả thuyết vì sao clean không hơn raw:
1. **Rò rỉ test trong raw:** raw còn 5 ảnh trùng tập test nên có thể được lợi khi đánh giá. Cách kiểm: bỏ 5 ảnh này khỏi raw rồi train lại.
2. **Clean ít ảnh hơn và còn cảnh báo:** clean ít hơn 22 ảnh và vẫn còn 38 ảnh có cảnh báo chưa xử lý. Cách kiểm: so số box từng lớp (nhất là `truck`) giữa hai bản trong `class_stats.csv`, hoặc train bản clean sau khi người duyệt hết hàng đợi.
3. **Test nhỏ, ít seed:** độ lệch tính từ 2 seed không đáng tin. Cách kiểm: chạy thêm seed, ví dụ 5 seed, rồi so lại.

## 6. Quyết định và ghi chú AI
**Quyết định cuối: Hold.** Chưa phát hành dataset, bản `clean_v1` chỉ là bản nháp để thử nghiệm. Không còn lỗi bắt buộc nào, nhưng vẫn còn 38/202 ảnh (18,8%) có cảnh báo chưa được xử lý. Để lên Release cần:
- Người duyệt xem hết 125 ảnh trong hàng đợi (hiện chỉ có 80), ưu tiên các ảnh nhầm lớp và thiếu box.
- Gán nhãn cho 6 ảnh thiếu file nhãn.
- Xử lý phần lớn các cảnh báo box thừa và box lỏng.
- Chạy lại pipeline và kiểm tra tỉ lệ ảnh còn cảnh báo đã xuống dưới 10%.

**Dùng AI:** Có. Tôi nhờ Claude Code viết 4 module `label_format`, `gate`, `autofix`, `second_opinion` và giúp soạn báo cáo.
- **Prompt chính:** tôi yêu cầu từng module một, theo kiểu:
  - `label_format`: "Viết hàm `run` trong `pipeline/checks/label_format.py`: mở lần lượt từng file nhãn, đọc từng dòng, kiểm tra lỗi và ghi mọi lỗi tìm thấy vào một danh sách."
  - `gate`: "Viết hàm nhận danh sách lỗi đã có rồi đưa ra quyết định cuối (Release, Hold hoặc Rework)."
  - `autofix`: prompt dài theo 4 ý trong `docs/PROMPTING.md` (đầu vào, quy tắc sửa, kiểu kết quả, giới hạn an toàn như chỉ sửa trong thư mục dữ liệu đang chạy, không đụng `data/raw`).
  - `second_opinion`: "Viết hoàn chỉnh `second_opinion.py`."
- **Cách kiểm:** chạy test từng module rồi cả bộ (79 test đều qua), chạy pipeline thật, đối chiếu danh sách ảnh bị cho là trùng, và chạy `--budget 0` để xem cổng chặn có ra Rework không.
- **Một lần AI sai:** 
