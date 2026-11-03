import pytest

from packages.scheduler.src.scheduler import (
    DeterministicScheduler,
    ScheduleError,
    Task,
)


def test_order_is_stable_and_respects_dependencies():
    scheduler = DeterministicScheduler()
    tasks = [
        Task("publish", ("verify",)),
        Task("build", ("plan",)),
        Task("plan"),
        Task("verify", ("build",)),
        Task("audit"),
    ]

    assert scheduler.order(tasks) == ["audit", "plan", "build", "verify", "publish"]
    assert scheduler.order(reversed(tasks)) == ["audit", "plan", "build", "verify", "publish"]


def test_levels_expose_parallelizable_waves():
    scheduler = DeterministicScheduler()
    tasks = [
        Task("root"),
        Task("left", ("root",)),
        Task("right", ("root",)),
        Task("finish", ("left", "right")),
    ]

    assert scheduler.levels(tasks) == [
        ["root"],
        ["left", "right"],
        ["finish"],
    ]


def test_unknown_dependency_is_rejected():
    with pytest.raises(ScheduleError, match="unknown dependency"):
        DeterministicScheduler().order([Task("child", ("missing",))])


def test_cycle_is_rejected_with_deterministic_diagnostic():
    with pytest.raises(ScheduleError, match="dependency cycle"):
        DeterministicScheduler().order([
            Task("a", ("c",)),
            Task("b", ("a",)),
            Task("c", ("b",)),
        ])


def test_duplicate_task_ids_are_rejected():
    with pytest.raises(ScheduleError, match="duplicate task id"):
        DeterministicScheduler().order([Task("same"), Task("same")])


def test_self_dependency_is_rejected():
    with pytest.raises(ScheduleError, match="cannot depend on itself"):
        DeterministicScheduler().order([Task("loop", ("loop",))])


def test_duplicate_dependencies_are_rejected():
    with pytest.raises(ScheduleError, match="duplicate dependencies"):
        DeterministicScheduler().order([Task("child", ("root", "root")), Task("root")])


def test_empty_graph_is_valid():
    assert DeterministicScheduler().order([]) == []
    assert DeterministicScheduler().levels([]) == []
