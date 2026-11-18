"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN  # noqa: F401


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems = set(image_stems)
    threshold = cfg["gate"]["warn_ratio_hold"]

    # lỗi bắt buộc: luôn tính, kể cả ở ảnh đã duyệt
    n_errors = sum(1 for i in issues if i.severity == ERROR)

    # cảnh báo: đếm ẢNH (không đếm issue), chỉ ảnh thuộc lô và chưa được người duyệt
    warn_images = {i.image for i in issues
                   if i.severity == WARN and i.image in stems and i.image not in reviewed}

    n_images = len(stems)
    n_warn_images = len(warn_images)
    ratio = round(n_warn_images / n_images, 4) if n_images else 0
    ratio_exact = n_warn_images / n_images if n_images else 0   # so với ngưỡng bằng giá trị chưa làm tròn

    if n_errors > 0:
        decision = "Rework"
        reasons = [f"còn {n_errors} lỗi bắt buộc (ERROR): phải sửa trước khi phát hành"]
    elif ratio_exact >= threshold:
        decision = "Hold"
        reasons = [f"không còn lỗi bắt buộc, nhưng {n_warn_images}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo, "
                   f"đạt hoặc vượt ngưỡng {threshold:.0%}: giữ lại cho người xem"]
    else:
        decision = "Release"
        reasons = [f"không còn lỗi bắt buộc; {n_warn_images}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo, "
                   f"dưới ngưỡng {threshold:.0%}"]

    return {
        "decision": decision,
        "n_errors": n_errors,
        "n_warn_images": n_warn_images,
        "n_images": n_images,
        "warn_ratio": ratio,
        "reasons": reasons,
    }
