from workpulse.confirm_ui import chunk_history_into_rows, determine_result, truncate_for_button


def test_determine_result_when_user_submits():
    text, status = determine_result(True, "会議対応", "資料作成")
    assert text == "会議対応"
    assert status == "confirmed"


def test_determine_result_when_timeout_reached():
    text, status = determine_result(False, "", "資料作成")
    assert text == "資料作成"
    assert status == "auto_confirmed"


def test_truncate_for_button_keeps_short_text_unchanged():
    assert truncate_for_button("資料作成", max_length=20) == "資料作成"


def test_truncate_for_button_truncates_long_text_with_ellipsis():
    long_text = "業務標準化対応とAC-5119課題について技術的な問題検討・対応を進めていた"
    result = truncate_for_button(long_text, max_length=20)
    assert len(result) == 20
    assert result.endswith("…")


def test_truncate_for_button_handles_empty_text():
    assert truncate_for_button("", max_length=20) == ""


def test_chunk_history_into_rows_splits_by_row_size():
    items = ["a", "b", "c", "d", "e"]
    rows = chunk_history_into_rows(items, items_per_row=2)
    assert rows == [["a", "b"], ["c", "d"], ["e"]]


def test_chunk_history_into_rows_handles_empty_list():
    assert chunk_history_into_rows([], items_per_row=4) == []
