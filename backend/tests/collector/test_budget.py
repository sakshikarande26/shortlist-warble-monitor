from app.client.models import RateLimitInfo
from app.collector.budget import BudgetTracker


def test_optimistic_default_before_first_response():
    budget = BudgetTracker(reserve=40, ceiling=250)
    assert budget.remaining() == 210
    assert budget.can_spend(210) is True
    assert budget.can_spend(211) is False


def test_update_tracks_server_remaining_minus_reserve():
    budget = BudgetTracker(reserve=40, ceiling=250)
    budget.update(RateLimitInfo(limit=250, remaining=100, reset=3600))
    assert budget.remaining() == 60
    assert budget.can_spend(60) is True
    assert budget.can_spend(61) is False


def test_never_goes_negative():
    budget = BudgetTracker(reserve=40, ceiling=250)
    budget.update(RateLimitInfo(limit=250, remaining=5, reset=3600))
    assert budget.remaining() == 0
    assert budget.can_spend(0) is True
    assert budget.can_spend(1) is False


def test_update_with_none_rate_limit_is_a_noop():
    budget = BudgetTracker(reserve=40, ceiling=250)
    budget.update(RateLimitInfo(limit=250, remaining=100, reset=3600))
    budget.update(None)
    assert budget.remaining() == 60
