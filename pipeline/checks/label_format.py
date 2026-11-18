"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    c = cfg["label_format"]
    tol, min_px = c["overflow_tol"], c["min_box_px"]
    max_frac, dup_iou = c["max_box_frac"], c["dup_box_iou"]
    n_classes = len(ds.classes)
    issues = []

    def add(severity, code, stem, msg, line, **extra):
        issues.append(Issue("label_format", severity, code, stem, msg, line=line, extra=extra))

    for path in ds.label_files():                      # mỗi file nhãn
        stem = path.stem
        seen = []                                      # các box hợp lệ đã đọc: (id, cx, cy, w, h)
        size = ds.image_size(stem)                     # (rộng, cao) px hoặc None nếu ảnh hỏng/không có

        for no, text in ds.read_label_lines(stem) or []:      # mỗi dòng (số dòng gốc, nội dung)
            try:
                cid, x, y, w, h = parse_yolo_line(text)
            except ValueError as e:
                add(ERROR, "BAD_FORMAT", stem, f"sai định dạng: {e}", no)
                continue
            if not 0 <= cid < n_classes:
                add(ERROR, "BAD_CLASS_ID", stem, f"id lớp {cid} ngoài 0..{n_classes - 1}", no)
                continue
            if w <= 0 or h <= 0:
                add(ERROR, "BOX_ZERO", stem, f"box có w={w}, h={h}", no)
                continue

            # box tràn ảnh: mức tràn lớn nhất trong 4 mép
            overflow = max(-(x - w / 2), -(y - h / 2), (x + w / 2) - 1, (y + h / 2) - 1)
            if overflow > tol:
                add(ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ảnh {overflow:.4f}", no, overflow=round(overflow, 4))

            # box lặp: cùng lớp với một dòng trước đó, IoU cao
            if any(p[0] == cid and iou_xywh(p[1:], (x, y, w, h)) > dup_iou for p in seen):
                add(ERROR, "DUP_BOX", stem, "box trùng với một dòng trước đó", no)
            seen.append((cid, x, y, w, h))

            # cảnh báo kích thước
            if size and min(w * size[0], h * size[1]) < min_px:
                add(WARN, "BOX_TINY", stem, f"cạnh ngắn < {min_px}px", no)
            if w * h > max_frac:
                add(WARN, "BOX_HUGE", stem, f"box chiếm {w * h:.0%} ảnh", no)
    return issues
