import numpy as np

from app.core.split import Board, cut_cost, split_boards


def test_fits_single_board():
    g = np.zeros((20, 25), dtype=np.int16)
    boards = split_boards(g, 29, 29)
    assert boards == [Board(0, 0, 20, 25, "A1")]


def test_cut_cost_counts_same_color_pairs_crossing_line():
    g = np.zeros((4, 6), dtype=np.int16)
    g[:, 3:] = 1                     # 列 2|3 之间是色边界
    assert cut_cost(g, axis=1, pos=3) == 0
    assert cut_cost(g, axis=1, pos=2) == 4


def test_seam_prefers_color_boundary_within_slack():
    g = np.zeros((10, 40), dtype=np.int16)
    g[:, 27:] = 1                    # 边界在 27，板宽 29，slack 3 → 候选 26..29，选 27
    boards = split_boards(g, 29, 29, slack=3)
    assert [b.col0 for b in boards] == [0, 27]
    assert all(b.cols <= 29 for b in boards)


def test_labels_and_coverage():
    g = np.zeros((60, 60), dtype=np.int16)
    boards = split_boards(g, 29, 29, slack=0)
    assert len(boards) == 9
    assert boards[0].label == "A1" and boards[-1].label == "C3"
    covered = np.zeros((60, 60), int)
    for b in boards:
        covered[b.row0:b.row0 + b.rows, b.col0:b.col0 + b.cols] += 1
    assert (covered == 1).all()


def test_empty_columns_cost_zero():
    g = np.full((5, 10), -1, dtype=np.int16)
    g[:, :4] = 0
    assert cut_cost(g, axis=1, pos=6) == 0
