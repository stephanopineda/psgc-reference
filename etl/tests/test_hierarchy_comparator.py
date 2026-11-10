import pytest

from psgc_etl.compare import compare_hierarchy_edges


def edge(child, parent, *, evidence="PSGC row 2"):
    return {
        "child_psgc_code": child,
        "parent_psgc_code": parent,
        "relationship_type": "PARENT_OF",
        "review_status": "PROPOSED",
        "rationale": "[TEST] Fixture relationship.",
        "evidence_reference": evidence,
    }


def test_identical_hierarchies_have_no_topology_changes():
    previous = [edge("0100100000", "0100000000")]
    current = [edge("0100100000", "0100000000", evidence="PSGC row 3")]

    result = compare_hierarchy_edges(previous, current)

    assert result["summary"] == {
        "previous_edge_count": 1,
        "current_edge_count": 1,
        "retained_child_count": 1,
        "unchanged_edge_count": 1,
        "changed_parent_count": 0,
        "added_edge_count": 0,
        "removed_edge_count": 0,
    }


def test_changed_parent_is_not_an_added_or_removed_child():
    previous = [edge("0100100000", "0100000000")]
    current = [edge("0100100000", "0100000001")]

    result = compare_hierarchy_edges(previous, current)

    assert result["summary"]["changed_parent_count"] == 1
    assert result["summary"]["added_edge_count"] == 0
    assert result["summary"]["removed_edge_count"] == 0

    change = result["changed_parent_relationships"][0]
    assert change["child_psgc_code"] == "0100100000"
    assert change["previous_edge"]["parent_psgc_code"] == "0100000000"
    assert change["current_edge"]["parent_psgc_code"] == "0100000001"


def test_added_and_removed_children_are_reported_separately():
    previous = [edge("0100100000", "0100000000")]
    current = [edge("0100200000", "0100000000")]

    result = compare_hierarchy_edges(previous, current)

    assert result["summary"]["added_edge_count"] == 1
    assert result["summary"]["removed_edge_count"] == 1
    assert result["added_edges"][0]["child_psgc_code"] == "0100200000"
    assert result["removed_edges"][0]["classification"] == "REMOVED_FROM_HIERARCHY"


def test_source_evidence_is_preserved_for_changed_relationships():
    previous = [edge("0100100000", "0100000000", evidence="Old row 10")]
    current = [edge("0100100000", "0100000001", evidence="New row 20")]

    result = compare_hierarchy_edges(previous, current)
    change = result["changed_parent_relationships"][0]

    assert change["previous_edge"]["evidence_reference"] == "Old row 10"
    assert change["current_edge"]["evidence_reference"] == "New row 20"


def test_duplicate_child_edges_are_rejected():
    edges = [
        edge("0100100000", "0100000000"),
        edge("0100100000", "0100200000"),
    ]

    with pytest.raises(ValueError, match="multiple edges"):
        compare_hierarchy_edges(edges, [])


def test_invalid_parent_code_is_rejected():
    edges = [edge("0100100000", "")]

    with pytest.raises(ValueError, match="invalid parent code"):
        compare_hierarchy_edges(edges, [])
