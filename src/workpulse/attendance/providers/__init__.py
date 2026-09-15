# src/workpulse/attendance/providers/__init__.py
"""勤怠サービスごとの実装置き場。

新しいサービスに対応するときは、ここに `BaseProvider` のサブクラスを
1ファイル追加し、`workpulse.attendance.registry._BUILTIN` に登録する。
"""
