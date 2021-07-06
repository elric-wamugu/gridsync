from unittest.mock import Mock

from gridsync.recovery import RecoveryKeyImporter


def test_show_error_msg_if_recovery_key_file_contains_only_numeric_chars(
    monkeypatch, tmp_path
):
    fake_error = Mock()
    monkeypatch.setattr("gridsync.recovery.error", fake_error)
    filepath = tmp_path / "test"
    filepath.write_text("123")
    RecoveryKeyImporter().do_import(str(filepath))
    assert fake_error.call_args[0][1] == "Error parsing Recovery Key content"


def test_show_error_msg_if_recovery_file_is_a_directory(
    monkeypatch, tmp_path_factory
):
    fake_error = Mock()
    monkeypatch.setattr("gridsync.recovery.error", fake_error)
    filepath = tmp_path_factory.mktemp("Test.app")
    RecoveryKeyImporter().do_import(str(filepath))
    assert fake_error.call_args[0][1] == "Error loading Recovery Key"


def test_show_error_msg_if_os_error_raises(monkeypatch, tmp_path):
    fake_error = Mock()
    monkeypatch.setattr("gridsync.recovery.error", fake_error)
    monkeypatch.setattr("builtins.open", Mock(side_effect=OSError("!Error!")))
    filepath = tmp_path / "test"
    RecoveryKeyImporter().do_import(str(filepath))
    assert fake_error.call_args[0][2] == "!Error!"


def test_show_error_msg_with_human_friendly_title(monkeypatch, tmp_path):
    fake_error = Mock()
    monkeypatch.setattr("gridsync.recovery.error", fake_error)
    monkeypatch.setattr("builtins.open", Mock(side_effect=OSError("!Error!")))
    filepath = tmp_path / "test"
    RecoveryKeyImporter().do_import(str(filepath))
    assert fake_error.call_args[0][1] == "Error loading Recovery Key"


def test_show_error_msg_if_recovery_file_is_empty(monkeypatch, tmp_path):
    fake_error = Mock()
    monkeypatch.setattr("gridsync.recovery.error", fake_error)
    filepath = tmp_path / "test"
    filepath.touch()
    RecoveryKeyImporter().do_import(str(filepath))
    assert fake_error.call_args[0][1] == "Invalid Recovery Key"
