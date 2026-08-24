#!/usr/bin/env python3
"""export_onnx.main() の infer 手書き複製 再導入を block する gate。

背景 (2026-08-25 v11 事故): main() は歴史的に SynthesizerTrn.infer の手書き
複製で ONNX graph を組んでおり、v10 M3/E2 までは手同期されていたが v11 P2
(enc_p の g_spk/AdaLN 条件付け) の変更に追従できず、**ONNX だけ話者条件が
断線して担体の調波が崩壊**した (comb-HNR 測定不能 → 一本化修正後 14.4dB)。
export 経路は build_infer_forward (models.infer の薄い wrapper) の一本に固定
する。同型の pytest (tests/test_f0_export_onnx.py の
test_production_export_path_uses_build_infer_forward) は torch 必須のため、
本 gate は text-only で commit 時点の fail-fast を担う。

意図的にこの構造を変える場合は、pytest 側の構造テストと本 script を同一
commit で更新すること。
"""

from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path("src/python/piper_train/export_onnx.py")

REQUIRED = "build_infer_forward(model_g"
# main() 内での infer 内部ヘルパー直呼びは「手書き複製が戻ってきた」シグナル
FORBIDDEN = (
    "model_g._predict_f0(",
    "model_g._apply_f0_prior_residual(",
    "model_g.enc_p(",
    "model_g.flow(",
    "model_g.dec(",
)


def main() -> int:
    src = TARGET.read_text(encoding="utf-8")
    idx = src.find("\ndef main(")
    if idx < 0:
        print(f"NG: {TARGET} に def main() が見つからない (構造変更なら本 gate を更新)")
        return 1
    main_src = src[idx:]

    errors: list[str] = []
    if REQUIRED not in main_src:
        errors.append(
            f"main() が {REQUIRED!r} を呼んでいない — export graph が "
            "models.infer と乖離する経路は禁止 (v11 AdaLN 断線事故の再発防止)"
        )
    for pat in FORBIDDEN:
        if pat in main_src:
            errors.append(
                f"main() に infer の手書き複製が再導入されている: {pat!r} — "
                "export 経路は build_infer_forward (models.infer) 一本に固定する"
            )

    if errors:
        print("export 経路一本化 gate 違反:")
        for e in errors:
            print(f"  - {e}")
        print(
            "背景: docs/design/zero-shot-v11-roadmap.md §5 / "
            "tests/test_f0_export_onnx.py::test_production_export_path_uses_build_infer_forward"
        )
        return 1
    print("OK: export_onnx.main() は build_infer_forward に一本化されている")
    return 0


if __name__ == "__main__":
    sys.exit(main())
