import math

from _research_helpers import ROOT  # noqa: F401
from backend.app.research import special as sp


def test_student_t_and_fisher_z_basics():
    assert 0.0 < sp.t_two_sided_p(2.0, 20) < 0.1
    assert sp.t_two_sided_p(0.0, 20) == 1.0
    assert sp.t_two_sided_p(float("inf"), 5) == 0.0
    assert sp.t_two_sided_p(2.0, 0) == 1.0
    assert sp.fisher_z(1.0) < 20 and sp.fisher_z(-1.0) > -20
