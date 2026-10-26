from matching_core.scoring import jaccard


def test_both_empty_scores_zero():
    assert jaccard(set(), set()) == 0.0


def test_disjoint_scores_zero():
    assert jaccard({"hiking"}, {"wine"}) == 0.0


def test_identical_scores_one():
    assert jaccard({"hiking", "coffee"}, {"hiking", "coffee"}) == 1.0


def test_partial_overlap():
    assert jaccard({"hiking", "coffee"}, {"hiking", "wine"}) == 1 / 3
