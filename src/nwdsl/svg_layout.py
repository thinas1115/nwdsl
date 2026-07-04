"""不変条件保証型レイアウトエンジン (ADR-0008)。

保証する不変条件:
  I1: ノード同士が重ならない (スロット割当)
  I2: ラベルが何とも重ならない (ポートスロット + 区間スケジューリングの帯)
  I3: 線がノード箱を貫通しない (Sugiyama ダミー頂点により全セグメントを
      行間チャネルに閉じ込める。大域配線は空域レーン + コリドーのみ通す)

美しさ (交差数) は重心法による順序付けで最小化を試みるが、保証対象ではない。
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from math import cos, pi, sin
from typing import Optional

from .graph import RenderEdge, RenderGraph, RenderNode

NODE_H = 46
DUMMY_W = 10
X_GAP = 30
CHANNEL_BASE = 56
LANE_H = 16
PORT_MIN = 52
SITE_PAD = 26
SITE_TITLE_H = 30
SITE_GAP = 56
SKY_LANE_H = 18
LABEL_ROW_H = 36
CLOUD_H = 76


def text_w(text: str, size: float = 13.0) -> float:
    """概算テキスト幅 (CJK=1.05em / ASCII=0.62em)。"""
    w = 0.0
    for ch in text:
        w += size * (1.05 if ord(ch) > 0x2E80 else 0.62)
    return w


def node_size(node: RenderNode) -> tuple[float, float]:
    lines = node.label.split("\n")
    w = max(90.0, max(text_w(s, 13) for s in lines) + 28)
    if node.kind == "cloud":
        return max(w + 40, 150), CLOUD_H
    h = 30 + 16 * max(0, len(lines) - 1)
    return w, max(h, 40)


@dataclass
class Placed:
    node: RenderNode
    x: float = 0.0  # 左上
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2


@dataclass
class RoutedEdge:
    edge: RenderEdge
    points: list[tuple[float, float]] = field(default_factory=list)
    label_box: Optional[tuple[float, float, float, float]] = None  # x,y,w,h (中央配置済み)
    src_port_label: Optional[tuple[float, float, str]] = None
    dst_port_label: Optional[tuple[float, float, str]] = None


@dataclass
class SiteBox:
    site_id: str
    label: str
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0


@dataclass
class SvgLayout:
    title: str
    width: float = 0.0
    height: float = 0.0
    placed: dict[str, Placed] = field(default_factory=dict)
    site_boxes: list[SiteBox] = field(default_factory=list)
    routed: list[RoutedEdge] = field(default_factory=list)


class _Sub:
    """1領域 (拠点内部 or 非グループ全体) の Sugiyama レイアウト。座標は領域ローカル。"""

    def __init__(self, nodes: list[RenderNode], edges: list[RenderEdge]):
        self.nodes = {n.id: n for n in nodes}
        self.edges = edges
        self.placed: dict[str, Placed] = {}
        self.routed: list[RoutedEdge] = []
        self.w = 0.0
        self.h = 0.0
        self._layout()

    # ---- ランク割当 (最長路。向きは graph 側で WAN→LAN に揃っている) ----
    def _ranks(self) -> dict[str, int]:
        rank = {nid: 0 for nid in self.nodes}
        for _ in range(len(self.nodes) + 1):
            changed = False
            for e in self.edges:
                if e.src in rank and e.dst in rank and rank[e.dst] < rank[e.src] + 1:
                    rank[e.dst] = rank[e.src] + 1
                    changed = True
            if not changed:
                break
        # 閉路 (向き付けの同点タイ等) ではランクが不連続になりうるため正規化する
        remap = {v: i for i, v in enumerate(sorted(set(rank.values())))}
        return {k: remap[v] for k, v in rank.items()}

    def _layout(self) -> None:
        if not self.nodes:
            return
        rank = self._ranks()
        max_rank = max(rank.values())

        # ---- ダミー頂点挿入: 全エッジを隣接ランク間セグメントに分解 (I3) ----
        rows: dict[int, list[str]] = defaultdict(list)
        for nid in self.nodes:
            rows[rank[nid]].append(nid)
        chains: list[tuple[RenderEdge, list[str]]] = []  # (edge, [src, d1, .., dst])
        same_rank: list[RenderEdge] = []
        dummy_no = 0
        for e in self.edges:
            if e.src not in self.nodes or e.dst not in self.nodes:
                continue
            r1, r2 = rank[e.src], rank[e.dst]
            if r1 == r2:
                same_rank.append(e)
                continue
            lo, hi = (e.src, e.dst) if r1 < r2 else (e.dst, e.src)
            chain = [lo]
            for r in range(min(r1, r2) + 1, max(r1, r2)):
                dummy_no += 1
                did = f"__d{dummy_no}"
                rank[did] = r
                rows[r].append(did)
                chain.append(did)
            chain.append(hi)
            if r1 > r2:  # 経路点列は常に src 起点で持つ
                chain = list(reversed(chain))
            chains.append((e, chain))

        # ---- 順序付け: 重心法スイープ ----
        adj_up: dict[str, list[str]] = defaultdict(list)
        adj_dn: dict[str, list[str]] = defaultdict(list)
        for _, chain in chains:
            seq = chain if rank[chain[0]] < rank[chain[-1]] else list(reversed(chain))
            for a, b in zip(seq, seq[1:]):
                adj_dn[a].append(b)
                adj_up[b].append(a)
        order: dict[int, list[str]] = {r: list(rows[r]) for r in rows}

        def sweep(direction_down: bool) -> None:
            rng = range(1, max_rank + 1) if direction_down else range(max_rank - 1, -1, -1)
            ref = adj_up if direction_down else adj_dn
            for r in rng:
                if r not in order:
                    continue
                pos = {nid: i for rr in order for i, nid in enumerate(order[rr])}
                order[r].sort(key=lambda nid: (
                    sum(pos.get(p, 0) for p in ref[nid]) / len(ref[nid]) if ref[nid]
                    else pos.get(nid, 0)))

        for _ in range(4):
            sweep(True)
            sweep(False)

        # ---- 座標: スロット割当 (I1) + 親子の重心整列 ----
        widths: dict[str, float] = {}
        for r in rows:
            for nid in order[r]:
                if nid.startswith("__d"):
                    widths[nid] = DUMMY_W
                else:
                    node = self.nodes[nid]
                    w, _ = node_size(node)
                    n_out = sum(1 for e in self.edges if e.src == nid)
                    n_in = sum(1 for e in self.edges if e.dst == nid)
                    widths[nid] = max(w, PORT_MIN * max(n_out, n_in, 1))
        xs: dict[str, float] = {}
        for r in rows:
            row_w = sum(widths[n] for n in order[r]) + X_GAP * (len(order[r]) - 1)
            x = -row_w / 2
            for nid in order[r]:
                xs[nid] = x
                x += widths[nid] + X_GAP

        def _cx(nid: str) -> float:
            return xs[nid] + widths[nid] / 2

        def _reposition(r: int, ref: dict[str, list[str]]) -> None:
            """隣接ランクの重心へ寄せる。順序と最小間隔は保つ (I1)。"""
            desired = [(sum(_cx(p) for p in ref[nid]) / len(ref[nid])
                        if ref[nid] else _cx(nid)) for nid in order[r]]
            pos: list[float] = []
            prev = -1e18
            for nid, d in zip(order[r], desired):
                x = max(prev + X_GAP, d - widths[nid] / 2)
                pos.append(x)
                prev = x + widths[nid]
            nxt = 1e18
            for k in range(len(order[r]) - 1, -1, -1):
                nid, d = order[r][k], desired[k]
                pos[k] = min(nxt - X_GAP - widths[nid],
                             max(pos[k], d - widths[nid] / 2))
                nxt = pos[k]
            for nid, x in zip(order[r], pos):
                xs[nid] = x

        for _ in range(3):
            for r in range(1, max_rank + 1):
                if r in order:
                    _reposition(r, adj_up)
            for r in range(max_rank - 1, -1, -1):
                if r in order:
                    _reposition(r, adj_dn)
        min_x = min(xs[n] for n in xs)
        for nid in xs:
            xs[nid] -= min_x
        total_w = max(xs[n] + widths[n] for n in xs)

        # ---- ポート割当 (I2: ポート間隔 >= PORT_MIN をノード幅で保証済み) ----
        out_edges: dict[str, list[tuple[float, RenderEdge, list[str]]]] = defaultdict(list)
        in_edges: dict[str, list[tuple[float, RenderEdge, list[str]]]] = defaultdict(list)
        for e, chain in chains:
            tgt_x = xs[chain[1]] + widths[chain[1]] / 2
            src_x = xs[chain[-2]] + widths[chain[-2]] / 2
            out_edges[chain[0]].append((tgt_x, e, chain))
            in_edges[chain[-1]].append((src_x, e, chain))

        def port_x(nid: str, index: int, count: int) -> float:
            return xs[nid] + widths[nid] * (index + 1) / (count + 1)

        port_of: dict[tuple[int, str], float] = {}  # (chain id, "src"|"dst") -> x
        for nid, items in out_edges.items():
            items.sort(key=lambda t: t[0])
            for i, (_, e, chain) in enumerate(items):
                port_of[(id(chain), "src")] = port_x(nid, i, len(items))
        for nid, items in in_edges.items():
            items.sort(key=lambda t: t[0])
            for i, (_, e, chain) in enumerate(items):
                port_of[(id(chain), "dst")] = port_x(nid, i, len(items))

        # ---- 直交配線: チャネルごとの水平レーンを区間スケジューリングで予約 (I2/I3) ----
        channel_lanes: dict[int, list[list[tuple[float, float]]]] = defaultdict(list)

        def alloc_lane(ch: int, x1: float, x2: float) -> int:
            lo, hi = min(x1, x2) - 8, max(x1, x2) + 8
            for li, intervals in enumerate(channel_lanes[ch]):
                if all(hi < a or lo > b for a, b in intervals):
                    intervals.append((lo, hi))
                    return li
            channel_lanes[ch].append([(lo, hi)])
            return len(channel_lanes[ch]) - 1

        def chain_seq(chain: list[str]) -> list[str]:
            return chain if rank[chain[0]] < rank[chain[-1]] else list(reversed(chain))

        def seg_x(chain: list[str], seq: list[str], k: int) -> tuple[float, float]:
            """seq[k] → seq[k+1] セグメントの上端x・下端x。"""
            flipped = rank[chain[0]] > rank[chain[-1]]
            top_key, bot_key = ("dst", "src") if flipped else ("src", "dst")
            xa = (port_of[(id(chain), top_key)] if k == 0
                  else xs[seq[k]] + widths[seq[k]] / 2)
            xb = (port_of[(id(chain), bot_key)] if k == len(seq) - 2
                  else xs[seq[k + 1]] + widths[seq[k + 1]] / 2)
            return xa, xb

        seg_lane: dict[tuple[int, int], int] = {}  # (chain id, seg idx) -> lane
        for e, chain in chains:
            seq = chain_seq(chain)
            for k in range(len(seq) - 1):
                xa, xb = seg_x(chain, seq, k)
                if abs(xa - xb) > 1:
                    seg_lane[(id(chain), k)] = alloc_lane(rank[seq[k]], xa, xb)
        sr_lane: dict[int, int] = {}  # same-rank edge index -> lane
        for si, e in enumerate(same_rank):
            sr_lane[si] = alloc_lane(rank[e.src], _cx(e.src), _cx(e.dst))

        # ---- y座標: チャネル高さはレーン数に応じて確保 ----
        row_h = {r: max([max(node_size(self.nodes[n])[1], NODE_H)
                         for n in order[r] if not n.startswith("__d")] or [NODE_H])
                 for r in rows}
        row_y: dict[int, float] = {}
        y = 0.0
        for r in range(max_rank + 1):
            row_y[r] = y
            lanes = len(channel_lanes.get(r, []))
            y += row_h.get(r, NODE_H) + max(CHANNEL_BASE, 30 + lanes * LANE_H + 16)
        ys = {nid: row_y[rank[nid]] for nid in list(self.nodes) + [n for r in rows
              for n in order[r] if n.startswith("__d")]}
        self.w = total_w
        self.h = row_y[max_rank] + row_h.get(max_rank, NODE_H)

        def lane_y(ch: int, lane: int) -> float:
            return row_y[ch] + row_h.get(ch, NODE_H) + 22 + lane * LANE_H

        for nid, node in self.nodes.items():
            _, h = node_size(node)
            self.placed[nid] = Placed(node, xs[nid], ys[nid], widths[nid], max(h, NODE_H))

        # ---- 経路点列: 全セグメントがチャネル内 (I3) ----
        label_rects: list[tuple[float, float, float, float]] = []
        node_rects = [(p.x, p.y, p.w, p.h) for p in self.placed.values()]

        def _clear(rect: tuple[float, float, float, float]) -> bool:
            return all(rect[0] + rect[2] < r[0] or rect[0] > r[0] + r[2]
                       or rect[1] + rect[3] < r[1] or rect[1] > r[1] + r[3]
                       for r in label_rects + node_rects)

        def place_label(routed: RoutedEdge) -> None:
            """エッジ中点付近にラベルを置き、ノード・他ラベルと重なるなら逃がす (I2)。"""
            if not routed.edge.label:
                return
            pts = routed.points
            m = len(pts) // 2
            mx = (pts[m - 1][0] + pts[m][0]) / 2
            my = (pts[m - 1][1] + pts[m][1]) / 2
            lines = routed.edge.label.split("\n")
            w = max(text_w(s, 12.5) for s in lines) + 12
            h = 18 * len(lines) + 4
            for dy in (0, -18, 18, -34, 34, -52, 52, 70, -70, 88):
                rect = (mx - w / 2, my + dy - h / 2, w, h)
                if _clear(rect):
                    my += dy
                    break
            label_rects.append((mx - w / 2, my - h / 2, w, h))
            routed.label_box = (mx - w / 2, my - h / 2, w, h)

        for e, chain in chains:
            seq = chain_seq(chain)
            pts: list[tuple[float, float]] = []
            for k in range(len(seq) - 1):
                a, b = seq[k], seq[k + 1]
                ch = rank[a]
                xa, xb = seg_x(chain, seq, k)
                ya = (self.placed[a].y + self.placed[a].h if a in self.placed
                      else ys[a] + row_h.get(rank[a], NODE_H) / 2)
                yb = (self.placed[b].y if b in self.placed
                      else ys[b] + row_h.get(rank[b], NODE_H) / 2)
                if k == 0:
                    pts.append((xa, ya))
                if abs(xa - xb) > 1:
                    ly = lane_y(ch, seg_lane[(id(chain), k)])
                    pts.append((xa, ly))
                    pts.append((xb, ly))
                pts.append((xb, yb))
            if rank[chain[0]] > rank[chain[-1]]:
                pts = list(reversed(pts))  # 点列は常に e.src 起点で持つ
            routed = RoutedEdge(e, pts)
            if e.src_label:
                routed.src_port_label = (pts[0][0], pts[0][1], e.src_label)
            if e.dst_label:
                routed.dst_port_label = (pts[-1][0], pts[-1][1], e.dst_label)
            place_label(routed)
            self.routed.append(routed)

        # ---- 同ランク辺: 直下チャネルの予約レーンをU字経由 (I3) ----
        for si, e in enumerate(same_rank):
            sp, dp = self.placed[e.src], self.placed[e.dst]
            ly = lane_y(rank[e.src], sr_lane[si])
            pts = [(sp.cx, sp.y + sp.h), (sp.cx, ly),
                   (dp.cx, ly), (dp.cx, dp.y + dp.h)]
            routed = RoutedEdge(e, pts)
            place_label(routed)
            self.routed.append(routed)


def _shift(sub: _Sub, dx: float, dy: float, out: SvgLayout) -> None:
    for nid, p in sub.placed.items():
        out.placed[nid] = Placed(p.node, p.x + dx, p.y + dy, p.w, p.h)
    for r in sub.routed:
        out.routed.append(RoutedEdge(
            r.edge, [(x + dx, y + dy) for x, y in r.points],
            label_box=(r.label_box[0] + dx, r.label_box[1] + dy,
                       r.label_box[2], r.label_box[3]) if r.label_box else None,
            src_port_label=(r.src_port_label[0] + dx, r.src_port_label[1] + dy,
                            r.src_port_label[2]) if r.src_port_label else None,
            dst_port_label=(r.dst_port_label[0] + dx, r.dst_port_label[1] + dy,
                            r.dst_port_label[2]) if r.dst_port_label else None))


def _clip_to_rect(cx: float, cy: float, tx: float, ty: float,
                  x: float, y: float, w: float, h: float) -> tuple[float, float]:
    """矩形中心(cx,cy)から(tx,ty)への線分と矩形境界の交点。"""
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    ts = []
    if dx:
        ts += [(x - cx) / dx, (x + w - cx) / dx]
    if dy:
        ts += [(y - cy) / dy, (y + h - cy) / dy]
    t = min(t for t in ts if t > 0)
    return cx + dx * t, cy + dy * t


def layout_view(graph: RenderGraph) -> SvgLayout:
    out = SvgLayout(title=graph.title)
    clouds = [n for n in graph.nodes if n.kind == "cloud"]
    cloud_ids = {n.id for n in clouds}
    site_members: dict[str, list[RenderNode]] = defaultdict(list)
    floor_nodes: list[RenderNode] = []
    for n in graph.nodes:
        if n.kind == "cloud":
            continue
        (site_members[n.site] if n.site else floor_nodes).append(n)

    def internal(members: list[RenderNode]) -> list[RenderEdge]:
        ids = {m.id for m in members}
        return [e for e in graph.edges if e.src in ids and e.dst in ids]

    # ---- 領域 (拠点 or 非グループ集合) をサブレイアウト ----
    units: list[tuple[Optional[str], Optional[str], _Sub]] = []  # (site_id, label, sub)
    for sid, label in graph.groups:
        members = site_members.get(sid, [])
        if members:
            units.append((sid, label, _Sub(members, internal(members))))
    if floor_nodes:
        units.append((None, None, _Sub(floor_nodes, internal(floor_nodes))))

    cross = [e for e in graph.edges
             if e not in [r.edge for _, _, s in units for r in s.routed]]

    # ---- リング検出: 拠点サブ + 非グループの各ノードを個別ユニットとした
    #      メタグラフが単一閉路なら円環配置 (collapsed でも機器レベルでも効く) ----
    ring_units: list[tuple[Optional[str], Optional[str], _Sub]] = [
        (sid, label, sub) for sid, label, sub in units if sid is not None]
    ring_units += [(None, None, _Sub([n], [])) for n in floor_nodes]
    unit_of: dict[str, int] = {}
    for i, (_, _, sub) in enumerate(ring_units):
        for nid in sub.placed:
            unit_of[nid] = i
    meta: dict[int, set[int]] = defaultdict(set)
    meta_edges = 0
    ring_cross: list[RenderEdge] = []
    for e in graph.edges:
        ui, uj = unit_of.get(e.src), unit_of.get(e.dst)
        if ui is not None and uj is not None and ui != uj:
            meta[ui].add(uj)
            meta[uj].add(ui)
            meta_edges += 1
            ring_cross.append(e)
    is_ring = (not clouds and len(ring_units) >= 4 and meta_edges == len(ring_units)
               and all(len(meta[i]) == 2 for i in range(len(ring_units))))

    if is_ring:
        return _compose_ring(graph, out, ring_units, ring_cross)
    return _compose_generic(graph, out, units, cross, clouds, cloud_ids)


def _unit_box(sid: Optional[str], sub: _Sub) -> tuple[float, float]:
    if sid is None:
        return sub.w, sub.h
    return sub.w + SITE_PAD * 2, sub.h + SITE_PAD * 2 + SITE_TITLE_H


def _compose_generic(graph: RenderGraph, out: SvgLayout, units, cross,
                     clouds: list[RenderNode], cloud_ids: set[str]) -> SvgLayout:
    top = 46.0  # タイトル帯
    # 空域の必要高さは後で決まるため、まず仮に領域行を組んでX座標を確定する
    x = 40.0
    unit_pos: list[tuple[float, str | None, str | None, _Sub, float, float]] = []
    row_h = 0.0
    for sid, label, sub in units:
        bw, bh = _unit_box(sid, sub)
        unit_pos.append((x, sid, label, sub, bw, bh))
        x += bw + SITE_GAP
        row_h = max(row_h, bh)
    row_w = x - SITE_GAP + 40

    # ---- 空域: 雲の並び / レーン / ラベル帯 ----
    gp: dict[str, tuple[float, float, float, float]] = {}  # 仮のグローバル座標 (領域行 y=0)
    for ux, sid, _, sub, bw, bh in unit_pos:
        ox = ux + (SITE_PAD if sid else 0)
        oy = SITE_TITLE_H + SITE_PAD if sid else 0
        for nid, p in sub.placed.items():
            gp[nid] = (p.x + ox, p.y + oy, p.w, p.h)

    cloud_pref: dict[str, list[float]] = defaultdict(list)
    for e in cross:
        for c, other in ((e.src, e.dst), (e.dst, e.src)):
            if c in cloud_ids and other in gp:
                cloud_pref[c].append(gp[other][0] + gp[other][2] / 2)
    placed_clouds: list[tuple[RenderNode, float, float]] = []
    order = sorted(clouds, key=lambda c: sum(cloud_pref[c.id]) / len(cloud_pref[c.id])
                   if cloud_pref[c.id] else 0)
    cx_cursor = 40.0
    for c in order:
        w, h = node_size(c)
        want = (sum(cloud_pref[c.id]) / len(cloud_pref[c.id]) - w / 2
                if cloud_pref[c.id] else cx_cursor)
        cx = max(cx_cursor, want)
        placed_clouds.append((c, cx, w))
        cx_cursor = cx + w + 60
    cloud_y = top

    # ---- 空域配線: 雲↔機器 と 拠点をまたぐ機器↔機器 (トンネル等) の両方 ----
    #      各端点の接続x座標を先に集め、対向のx順でポートを割り振る
    def _want_x(nid: str) -> float:
        if nid in gp:
            return gp[nid][0] + gp[nid][2] / 2
        rec = next((p for p in placed_clouds if p[0].id == nid), None)
        return rec[1] + rec[2] / 2 if rec else 0.0

    attach: dict[str, list[tuple[float, int, str]]] = defaultdict(list)
    routable: list[int] = []
    for i, e in enumerate(cross):
        if not ((e.src in gp or e.src in cloud_ids) and (e.dst in gp or e.dst in cloud_ids)):
            continue
        routable.append(i)
        attach[e.src].append((_want_x(e.dst), i, "src"))
        attach[e.dst].append((_want_x(e.src), i, "dst"))
    end_x: dict[tuple[int, str], float] = {}
    for nid, items in attach.items():
        items.sort()
        if nid in cloud_ids:
            rec = next((p for p in placed_clouds if p[0].id == nid), None)
            if rec is None:
                continue
            x0, w0 = rec[1], rec[2]
        else:
            x0, _, w0, _ = gp[nid]
        for k, (_, i, end) in enumerate(items):
            end_x[(i, end)] = x0 + w0 * (k + 1) / (len(items) + 1)

    lanes: list[list[tuple[float, float]]] = []
    lane_of: dict[int, int] = {}
    label_rows: list[list[tuple[float, float]]] = []
    label_row_of: dict[int, int] = {}
    label_anchor: dict[int, float] = {}
    sky: list[tuple[int, RenderEdge]] = []
    all_vx = sorted(x for (_, _), x in end_x.items())
    for i in routable:
        e = cross[i]
        if (i, "src") not in end_x or (i, "dst") not in end_x:
            continue
        xa, xb = end_x[(i, "src")], end_x[(i, "dst")]
        lo, hi = min(xa, xb) - 6, max(xa, xb) + 6
        for li, intervals in enumerate(lanes):
            if all(hi < a or lo > b for a, b in intervals):
                intervals.append((lo, hi))
                lane_of[i] = li
                break
        else:
            lanes.append([(lo, hi)])
            lane_of[i] = len(lanes) - 1
        sky.append((i, e))
        if e.label:
            # ラベルは機器側端点の縦線上に置く。機器同士のエッジなら中間点
            if e.src in cloud_ids:
                anchor = xb
            elif e.dst in cloud_ids:
                anchor = xa
            else:
                anchor = (xa + xb) / 2
            label_anchor[i] = anchor
            w = max(text_w(s, 12.5) for s in e.label.split("\n")) + 12
            llo, lhi = anchor - w / 2 - 6, anchor + w / 2 + 6
            blockers = [vx for vx in all_vx if abs(vx - anchor) > 1]
            for ri, intervals in enumerate(label_rows):
                if all(lhi < a or llo > b for a, b in intervals) and \
                        all(not (llo < vx < lhi) for vx in blockers):
                    intervals.append((llo, lhi))
                    label_row_of[i] = ri
                    break
            else:
                label_rows.append([(llo, lhi)])
                label_row_of[i] = len(label_rows) - 1

    sky_top = cloud_y + (CLOUD_H + 18 if clouds else 0)
    label_top = sky_top + len(lanes) * SKY_LANE_H + 10
    # 空域 (雲・拠点間配線・回線ラベル帯) を使う場合はそのぶん拠点行を下げる
    if clouds or lanes or label_rows:
        units_y = label_top + len(label_rows) * LABEL_ROW_H + 24
    else:
        units_y = top + 10

    # ---- 確定座標で出力を組み立て ----
    for c, cx0, cw in placed_clouds:
        out.placed[c.id] = Placed(c, cx0, cloud_y, cw, CLOUD_H)
    for ux, sid, label, sub, bw, bh in unit_pos:
        if sid is not None:
            out.site_boxes.append(SiteBox(sid, label or sid, ux, units_y, bw, bh))
            _shift(sub, ux + SITE_PAD, units_y + SITE_TITLE_H + SITE_PAD, out)
        else:
            _shift(sub, ux, units_y, out)
    box_of_site = {b.site_id: b for b in out.site_boxes}
    for i, e in sky:
        xa, xb = end_x[(i, "src")], end_x[(i, "dst")]
        lane_y = sky_top + lane_of[i] * SKY_LANE_H

        def _end_leg(nid: str, x: float) -> list[tuple[float, float]]:
            """端点からレーンまでの脚。深い段の機器は拠点余白コリドー経由 (I3)。"""
            if nid in cloud_ids:
                return [(x, cloud_y + CLOUD_H)]
            p = out.placed[nid]
            box = box_of_site.get(p.node.site or "")
            first_row_y = (box.y + SITE_TITLE_H + SITE_PAD + 4) if box else None
            if box is None or p.y <= first_row_y:
                return [(x, p.y)]  # 最上段: 真上に抜けて良い
            corr_x = (box.x + 10 if (x - box.x) < (box.x + box.w - x)
                      else box.x + box.w - 10)
            jog_y = p.y - 14  # ノード直上のチャネル帯
            return [(x, p.y), (x, jog_y), (corr_x, jog_y)]

        src_leg = _end_leg(e.src, xa)
        dst_leg = _end_leg(e.dst, xb)
        xa_eff = src_leg[-1][0]
        xb_eff = dst_leg[-1][0]
        pts = src_leg + [(xa_eff, lane_y), (xb_eff, lane_y)] + list(reversed(dst_leg))
        r = RoutedEdge(e, pts)
        if i in label_row_of and e.label:
            w = max(text_w(s, 12.5) for s in e.label.split("\n")) + 12
            h = 18 * len(e.label.split("\n")) + 6
            r.label_box = (label_anchor[i] - w / 2,
                           label_top + label_row_of[i] * LABEL_ROW_H, w, h)
        out.routed.append(r)

    out.width = max(row_w, cx_cursor + 40)
    out.height = units_y + row_h + 40
    out.title = graph.title
    return out


def _compose_ring(graph: RenderGraph, out: SvgLayout, units, cross) -> SvgLayout:
    n = len(units)
    sizes = [_unit_box(sid, sub) for sid, _, sub in units]
    circumference = sum(w + h for w, h in sizes) * 1.15 + n * 90
    radius = max(circumference / (2 * pi), 240.0)
    cx = radius + max(w for w, _ in sizes) / 2 + 60
    cy = radius + max(h for _, h in sizes) / 2 + 80
    centers: list[tuple[float, float]] = []
    for i, ((sid, label, sub), (bw, bh)) in enumerate(zip(units, sizes)):
        ang = 2 * pi * i / n - pi / 2
        ux, uy = cx + radius * cos(ang) - bw / 2, cy + radius * sin(ang) - bh / 2
        centers.append((ux + bw / 2, uy + bh / 2))
        if sid is not None:
            out.site_boxes.append(SiteBox(sid, label or sid, ux, uy, bw, bh))
            _shift(sub, ux + SITE_PAD, uy + SITE_TITLE_H + SITE_PAD, out)
        else:
            _shift(sub, ux, uy, out)
    unit_of: dict[str, int] = {}
    for i, (_, _, sub) in enumerate(units):
        for nid in sub.placed:
            unit_of[nid] = i
    boxes = [(c[0] - s[0] / 2, c[1] - s[1] / 2, s[0], s[1])
             for c, s in zip(centers, sizes)]
    for k, e in enumerate(cross):
        i, j = unit_of.get(e.src), unit_of.get(e.dst)
        if i is None or j is None:
            continue
        (x1, y1), (x2, y2) = centers[i], centers[j]
        p1 = _clip_to_rect(x1, y1, x2, y2, *boxes[i])
        p2 = _clip_to_rect(x2, y2, x1, y1, *boxes[j])
        r = RoutedEdge(e, [p1, p2])
        if e.label:
            mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
            norm = max(1, ((mx - cx) ** 2 + (my - cy) ** 2) ** .5)
            ox, oy = (mx - cx) / norm, (my - cy) / norm
            w = max(text_w(s, 12.5) for s in e.label.split("\n")) + 12
            h = 18 * len(e.label.split("\n")) + 6
            blockers = ([(p.x, p.y, p.w, p.h) for p in out.placed.values()]
                        + [(b.x, b.y, b.w, b.h) for b in out.site_boxes]
                        + [rr.label_box for rr in out.routed if rr.label_box])
            for dist in (46, 66, 86, 108, 130, 154):
                rect = (mx + ox * dist - w / 2, my + oy * dist - h / 2, w, h)
                if all(rect[0] + w < bx or rect[0] > bx + bw
                       or rect[1] + h < by or rect[1] > by + bh
                       for bx, by, bw, bh in blockers):
                    break
            r.label_box = rect
        out.routed.append(r)
    out.width = cx + radius + max(w for w, _ in sizes) / 2 + 60
    out.height = cy + radius + max(h for _, h in sizes) / 2 + 60
    return out
