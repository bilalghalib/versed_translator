import numpy as np

from versed_translator.qe.probe_r1a import fit_predict_logreg, prf


def test_prf_perfect():
    y = np.array([1, 1, 0, 0])
    assert prf(y, y, 1)["f1"] == 1.0


def test_numpy_logreg_separates_and():
    x = np.array([[0, 0], [0, 1], [1, 0], [1, 1]], dtype=float)
    y = np.array([0, 0, 0, 1])
    pred = fit_predict_logreg(x, y, x)
    assert pred[-1] == 1

