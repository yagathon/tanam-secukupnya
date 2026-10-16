import pytest

from app import calibration as cal

PAKCOY = ((0, 5), (7, 15), (14, 45), (18, 70), (21, 100), (24, 125), (27, 145), (30, 160))
EMPTY = tuple(() for _ in PAKCOY)


def test_weights_split_between_two_nodes():
    assert cal.node_weights([18, 21], 19.5) == [0.5, 0.5]
    assert cal.node_weights([0, 7], -3) == [1.0, 0.0]
    assert cal.node_weights([0, 7], 40) == [0.0, 1.0]


def test_one_sample_on_a_node_moves_it_at_most_5pct():
    pts, kept = cal.update(PAKCOY, EMPTY, 21, 1.2)
    assert pts[4] == (21, pytest.approx(105.0))
    assert kept[4] == (1.2,)
    assert pts[3] == (18, 70)


def test_sample_between_nodes_moves_both_by_weight():
    pts, _ = cal.update(PAKCOY, EMPTY, 19.5, 1.1)
    assert pts[3][1] == pytest.approx(71.05)
    assert pts[4][1] == pytest.approx(101.5)


def test_median_ignores_one_outlier():
    kept = tuple((1.0, 1.0, 1.0, 1.0) if i == 4 else () for i in range(len(PAKCOY)))
    pts, kept2 = cal.update(PAKCOY, kept, 21, 0.6)
    assert pts[4][1] == 100
    assert kept2[4] == (1.0, 1.0, 1.0, 1.0, 0.6)


def test_keeps_last_five_only():
    kept = tuple((1.0,) * 5 if i == 4 else () for i in range(len(PAKCOY)))
    _, kept2 = cal.update(PAKCOY, kept, 21, 1.3)
    assert kept2[4] == (1.0, 1.0, 1.0, 1.0, 1.3)


def test_monotone_repair():
    pts, _ = cal.update(((0, 10), (7, 10.5)), ((), ()), 0, 2.0)
    assert pts[0][1] == pytest.approx(10.5)
    assert pts[1][1] == pytest.approx(11.5)
