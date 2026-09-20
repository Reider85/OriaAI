from llm_client.agent import IterationMonitor, compute_state_delta


def test_delta_identical_is_1():
    s1 = {"messages": [{"role": "ai", "content": "hello world"}]}
    s2 = {"messages": [{"role": "ai", "content": "hello world"}]}
    assert compute_state_delta(s1, s2) == 1.0


def test_delta_different_is_low():
    s1 = {"messages": [{"role": "ai", "content": "abcdef"}]}
    s2 = {"messages": [{"role": "ai", "content": "xyzqrs"}]}
    assert compute_state_delta(s1, s2) < 0.3


def test_delta_empty_messages():
    assert compute_state_delta({}, {}) == 1.0


def test_monitor_normal_flow_no_false_trigger():
    monitor = IterationMonitor(enabled=True, threshold=0.95)
    assert not monitor.check({"messages": [{"content": "first"}]})
    assert not monitor.check({"messages": [{"content": "second different"}]})
    assert not monitor.check({"messages": [{"content": "third"}]})
    assert monitor._consecutive_similar == 0


def test_monitor_detects_cycle_on_third_iteration():
    monitor = IterationMonitor(enabled=True, threshold=0.95, consecutive=2)
    assert not monitor.check({"messages": [{"content": "same"}]})
    assert not monitor.check({"messages": [{"content": "same"}]})
    assert monitor.check({"messages": [{"content": "same"}]}) is True


def test_monitor_disabled_flag():
    monitor = IterationMonitor(enabled=False, threshold=0.95)
    assert not monitor.check({"messages": [{"content": "same"}]})
    assert not monitor.check({"messages": [{"content": "same"}]})
    assert not monitor.check({"messages": [{"content": "same"}]})