"""バリデータのテスト: 正常系1 + 異常系パターン。"""

import textwrap
from pathlib import Path

import pytest

from nwdsl.loader import LoadError, load_document
from nwdsl.validate import has_errors, validate_document

SAMPLE = Path(__file__).parent.parent / "examples" / "sample-corp" / "network.yaml"

MINIMAL = """
nwdsl: "0.1"
network: {name: test}
sites:
  - {id: hq, name: 本社}
  - {id: br, name: 支店}
devices:
  - id: rt1
    site: hq
    role: router
    interfaces: [{name: ge0}, {name: ge1}]
  - id: rt2
    site: br
    role: router
    interfaces: [{name: ge0}]
clouds:
  - {id: wan, name: WAN網, kind: wan}
circuits:
  - {id: cct1, provider: NTT, service: IP-VPN}
"""


def _load(tmp_path: Path, body: str, base: str = MINIMAL):
    f = tmp_path / "net.yaml"
    f.write_text(base + textwrap.dedent(body), encoding="utf-8")
    return load_document(f)


def _codes(issues):
    return {i.code for i in issues}


def test_sample_corp_is_valid():
    issues = validate_document(load_document(SAMPLE))
    assert issues == []


def test_unknown_field_rejected(tmp_path):
    with pytest.raises(LoadError, match="スキーマ違反"):
        _load(tmp_path, """
        links:
          - type: lan-cable
            endpoints: ["rt1:ge0", "rt2:ge0"]
            cirucit: cct1   # タイポ
        """)


def test_missing_site_ref(tmp_path):
    doc = _load(tmp_path, """
    segments:
      - {id: seg1, site: nowhere}
    """)
    assert "ref.site" in _codes(validate_document(doc))


def test_undeclared_interface(tmp_path):
    doc = _load(tmp_path, """
    links:
      - type: lan-cable
        endpoints: ["rt1:ge99", "rt1:ge1"]
    """)
    assert "ref.interface" in _codes(validate_document(doc))


def test_unknown_endpoint(tmp_path):
    doc = _load(tmp_path, """
    links:
      - type: logical
        endpoints: ["rt1", "ghost"]
    """)
    assert "ref.endpoint" in _codes(validate_document(doc))


def test_lan_cable_cross_site_rejected(tmp_path):
    doc = _load(tmp_path, """
    links:
      - type: lan-cable
        endpoints: ["rt1:ge0", "rt2:ge0"]
    """)
    assert "link.lan-cross-site" in _codes(validate_document(doc))


def test_wan_circuit_requires_circuit(tmp_path):
    doc = _load(tmp_path, """
    links:
      - type: wan-circuit
        endpoints: ["rt1:ge0", "wan"]
    """)
    assert "link.circuit-required" in _codes(validate_document(doc))


def test_circuit_forbidden_on_tunnel(tmp_path):
    doc = _load(tmp_path, """
    links:
      - type: tunnel
        endpoints: ["rt1", "rt2"]
        circuit: cct1
    """)
    assert "link.circuit-forbidden" in _codes(validate_document(doc))


def test_circuit_multi_use_rejected(tmp_path):
    doc = _load(tmp_path, """
    links:
      - type: wan-circuit
        endpoints: ["rt1:ge0", "wan"]
        circuit: cct1
      - type: wan-circuit
        endpoints: ["rt2:ge0", "wan"]
        circuit: cct1
    """)
    assert "circuit.multi-use" in _codes(validate_document(doc))


def test_physical_port_reuse_rejected(tmp_path):
    doc = _load(tmp_path, """
    links:
      - type: lan-cable
        endpoints: ["rt1:ge0", "rt1:ge1"]
      - type: wan-circuit
        endpoints: ["rt1:ge0", "wan"]
        circuit: cct1
    """)
    assert "link.port-reuse" in _codes(validate_document(doc))


def test_unused_circuit_is_warning_only(tmp_path):
    doc = _load(tmp_path, "")
    issues = validate_document(doc)
    assert "circuit.unused" in _codes(issues)
    assert not has_errors(issues)


def test_view_site_ref(tmp_path):
    doc = _load(tmp_path, """
    views:
      - id: v1
        title: test
        include_sites: [nowhere]
    """)
    assert "ref.view-site" in _codes(validate_document(doc))


def test_duplicate_device_cloud_id(tmp_path):
    doc = _load(tmp_path, """
    segments: []
    """)
    # devices と clouds の名前空間衝突を別データで確認
    f = tmp_path / "dup.yaml"
    f.write_text(MINIMAL.replace("id: wan, name: WAN網", "id: rt1, name: WAN網"),
                 encoding="utf-8")
    doc = load_document(f)
    assert "dup.id" in _codes(validate_document(doc))


def test_bad_cidr_rejected(tmp_path):
    with pytest.raises(LoadError):
        _load(tmp_path, """
        segments:
          - {id: seg1, site: hq, ipv4: 10.0.0.999/24}
        """)
