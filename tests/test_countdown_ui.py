from workpulse.countdown_ui import CountdownController


def test_countdown_ticks_down_and_calls_on_finish_at_zero():
    ticks = []
    finished_calls = []

    controller = CountdownController(3, on_tick=ticks.append, on_finish=lambda: finished_calls.append(True))

    controller.tick()
    controller.tick()
    controller.tick()

    assert ticks == [2, 1, 0]
    assert finished_calls == [True]
    assert controller.finished is True


def test_countdown_tick_after_finished_is_noop():
    ticks = []
    finished_calls = []

    controller = CountdownController(1, on_tick=ticks.append, on_finish=lambda: finished_calls.append(True))
    controller.tick()
    controller.tick()

    assert ticks == [0]
    assert finished_calls == [True]


def test_countdown_skip_finishes_immediately():
    ticks = []
    finished_calls = []

    controller = CountdownController(30, on_tick=ticks.append, on_finish=lambda: finished_calls.append(True))
    controller.skip()

    assert controller.finished is True
    assert finished_calls == [True]
    assert ticks == []
