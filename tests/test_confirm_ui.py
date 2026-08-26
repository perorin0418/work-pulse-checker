from workpulse.confirm_ui import determine_result


def test_determine_result_when_user_submits():
    text, status = determine_result(True, "会議対応", "資料作成")
    assert text == "会議対応"
    assert status == "confirmed"


def test_determine_result_when_timeout_reached():
    text, status = determine_result(False, "", "資料作成")
    assert text == "資料作成"
    assert status == "auto_confirmed"
