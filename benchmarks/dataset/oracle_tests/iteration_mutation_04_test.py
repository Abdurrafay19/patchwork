def test_prunes_inactive():
    sessions = {
        "s1": {"active": True},
        "s2": {"active": False},
        "s3": {"active": False},
    }
    assert prune_inactive_sessions(sessions) == {"s1": {"active": True}}