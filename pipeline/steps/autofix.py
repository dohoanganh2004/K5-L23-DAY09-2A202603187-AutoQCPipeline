"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}   # cộng thêm mọi mã bắt đầu bằng DUP_IMAGE_


def _is_remove(code):
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE_")


def _clip(line):
    """Cắt box về trong [0,1]. Trả về dòng mới, hoặc None nếu box không còn diện tích (hoặc dòng không đọc được)."""
    try:
        c, x, y, w, h = parse_yolo_line(line)
    except ValueError:
        return None
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)
    nw, nh = x2 - x1, y2 - y1
    if nw <= 0 or nh <= 0:
        return None
    return f"{c} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {nw:.6f} {nh:.6f}"


def fix(ds, issues, cfg):
    fixes = []
    errors = [i for i in issues if i.severity == ERROR]       # cảnh báo (WARN) là việc của người: không đụng tới

    # 1) Xoá ảnh (+ nhãn) trước; các issue còn lại của ảnh đã xoá sẽ bị bỏ qua êm
    removed = set()
    for stem in sorted({i.image for i in errors if _is_remove(i.code)}):
        img = ds.image_path(stem)
        lab = ds.label_path(stem)
        if img is not None:
            img.unlink()
        if lab.exists():
            lab.unlink()
        removed.add(stem)
        fixes.append(dict(image=stem, line=None, action="remove_image",
                          before=img.name if img is not None else "(không có ảnh)", after="(đã xoá ảnh và nhãn)"))

    # 2) Ghi lại tên lớp trong data.yaml (nhiều issue BAD_CLASS_NAME vẫn chỉ sửa 1 lần)
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) if ds.yaml_path.exists() else None
        data = data or {}
        before = data.get("names")
        data["names"] = {k: n for k, n in enumerate(cfg["classes"])}
        ds.yaml_path.write_bytes(yaml.safe_dump(data, allow_unicode=True, sort_keys=False).encode("utf-8"))
        fixes.append(dict(image="data.yaml", line=None, action="rename_classes", before=str(before), after=str(cfg["classes"])))

    # 3) Ảnh thiếu file nhãn: không bịa nhãn, chuyển cho người
    for stem in sorted({i.image for i in errors if i.code == "MISSING_LABEL_FILE"} - removed):
        fixes.append(dict(image=stem, line=None, action="needs_label", before="(không có file)", after="chuyển người gán"))

    # 4) Sửa dòng nhãn: gom theo ảnh, dùng số dòng GỐC, ghi file một lần
    drops, clips = defaultdict(set), defaultdict(set)
    for i in errors:
        if i.image in removed or i.line is None:
            continue
        if i.code in DROP_CODES:
            drops[i.image].add(i.line)
        elif i.code == "BOX_OUT_OF_IMAGE":
            clips[i.image].add(i.line)

    for stem in sorted(set(drops) | set(clips)):
        path = ds.label_path(stem)
        if not path.exists():
            continue
        old = path.read_text(encoding="utf-8", errors="replace").splitlines()   # giữ nguyên vị trí dòng trống
        new, changed = [], False
        for no, text in enumerate(old, 1):
            if no in drops[stem]:                       # dòng thắng: xoá (kể cả khi còn lỗi tràn ảnh)
                fixes.append(dict(image=stem, line=no, action="drop_line", before=text, after="(đã xoá)"))
                changed = True
            elif no in clips[stem]:
                clipped = _clip(text)
                if clipped is None:                     # cắt xong không còn diện tích: xoá
                    fixes.append(dict(image=stem, line=no, action="drop_line", before=text, after="(đã xoá)"))
                else:
                    new.append(clipped)
                    fixes.append(dict(image=stem, line=no, action="clip_box", before=text, after=clipped))
                changed = True
            else:
                new.append(text)
        if changed:
            path.write_bytes(("\n".join(new) + "\n" if new else "").encode("utf-8"))
    return fixes
