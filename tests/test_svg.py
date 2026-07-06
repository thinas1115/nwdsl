"""自前SVGレンダラの不変条件テスト (ADR-0008)。

全サンプル・全ビューに対して:
  I1: ノード同士が重ならない
  ラベル帯: 空域ラベル同士が重ならない
  出力: SVGとして成立している
を機械検査する。美しさは対象外 (目視レビューで担保)。
"""

from pathlib import Path

import pytest

from nwdsl.loader import load_document
from nwdsl.graph import resolve_view
from nwdsl.render_svg import render_svg
from nwdsl.svg_layout import layout_view

EXAMPLES = Path(__file__).parent.parent / "examples"
TARGETS = [
    EXAMPLES / "sample-corp" / "network.yaml",
    EXAMPLES / "complex-lan" / "network.yaml",
    EXAMPLES / "scale-50" / "network.yaml",
    EXAMPLES / "two-site-ipsec" / "network.yaml",
    EXAMPLES / "hq-dc-cloud" / "network.yaml",
    EXAMPLES / "branch-20" / "network.yaml",
    EXAMPLES / "stress" / "leafspine.yaml",
    EXAMPLES / "stress" / "ring.yaml",
    EXAMPLES / "stress" / "multisite.yaml",
    EXAMPLES / "stress" / "lag.yaml",
]


@pytest.mark.parametrize("path", TARGETS, ids=lambda p: p.parent.name + "-" + p.stem)
def test_all_examples_validate_clean(path):
    from nwdsl.validate import validate_document, has_errors
    issues = validate_document(load_document(path))
    assert not has_errors(issues), [str(i) for i in issues]


def _views():
    for path in TARGETS:
        doc = load_document(path)
        for view in doc.views:
            yield pytest.param(doc, view, id=f"{path.parent.name}-{view.id}")


def _overlap(a, b, tol=1.0):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx + tol or bx + bw <= ax + tol
                or ay + ah <= by + tol or by + bh <= ay + tol)


@pytest.mark.parametrize("doc,view", list(_views()))
def test_invariants(doc, view):
    graph = resolve_view(doc, view)
    layout = layout_view(graph)

    # I1: ノード同士の重なりゼロ
    rects = [(p.node.id, (p.x, p.y, p.w, p.h)) for p in layout.placed.values()]
    for i, (ida, ra) in enumerate(rects):
        for idb, rb in rects[i + 1:]:
            assert not _overlap(ra, rb), f"ノード重なり: {ida} と {idb} ({view.id})"

    # 空域ラベル同士の重なりゼロ (領域内ラベルは逃がし配置のためここでは対象外)
    boxes = [r.label_box for r in layout.routed if r.label_box is not None]
    # ノードとラベルの重なりもゼロ
    for lb in boxes:
        for ida, ra in rects:
            assert not _overlap(lb, ra), f"ラベルとノード {ida} が重なり ({view.id})"

    # キャンバス内に収まっている
    for _, (x, y, w, h) in rects:
        assert x >= -1 and y >= -1
        assert x + w <= layout.width + 1, f"canvas幅不足 ({view.id})"
        assert y + h <= layout.height + 1, f"canvas高さ不足 ({view.id})"


@pytest.mark.parametrize("doc,view", list(_views()))
def test_svg_emits(doc, view):
    svg = render_svg(resolve_view(doc, view))
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "<polyline" in svg


def test_order_declared_matches_across_views():
    """order: declared なら、layers が異なるビュー間でも拠点の左右順序が
    sites 宣言順で揃うこと(内蔵SVGエンジンのみ対象)。"""
    doc = load_document(EXAMPLES / "sample-corp" / "network.yaml")
    physical = next(v for v in doc.views if v.id == "physical-all")
    logical = next(v for v in doc.views if v.id == "logical-all")
    assert physical.order == logical.order == "declared"
    declared_site_ids = [s.id for s in doc.sites]

    for view in (physical, logical):
        layout = layout_view(resolve_view(doc, view))
        by_x = sorted(layout.site_boxes, key=lambda b: b.x)
        assert [b.site_id for b in by_x] == declared_site_ids, (
            f"{view.id}: 拠点順序が宣言順と不一致")


def test_order_auto_is_default():
    doc = load_document(EXAMPLES / "sample-corp" / "network.yaml")
    view = next(v for v in doc.views if v.id == "wan-overview")
    assert view.order == "auto"


def test_ring_detected():
    doc = load_document(EXAMPLES / "stress" / "ring.yaml")
    view = next(v for v in doc.views if v.id == "ring-collapsed")
    layout = layout_view(resolve_view(doc, view))
    # 円環配置: 全ノードのy座標が一列 (層状) ではなく分散している
    ys = sorted({round(p.y) for p in layout.placed.values()})
    assert len(ys) >= 4, "リングが層状に潰れている"
