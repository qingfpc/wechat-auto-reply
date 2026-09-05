from pathlib import Path
from tempfile import TemporaryDirectory

from wechat_draft_brain import config


def _config_paths(monkeypatch):
    temp = TemporaryDirectory()
    root = Path(temp.name)
    default_path = root / "default.yaml"
    user_path = root / "user.yaml"
    default_path.write_text(
        "hotkey: '<ctrl>+<alt>+w'\ncapture: ocr\ntheme: dark\nlayout: {}\npolicy: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "DEFAULT_CONFIG", default_path)
    monkeypatch.setattr(config, "USER_CONFIG", user_path)
    return temp, user_path


def test_malformed_user_config_falls_back_without_overwriting(monkeypatch):
    temp, user_path = _config_paths(monkeypatch)
    with temp:
        original = "llm: [broken"
        user_path.write_text(original, encoding="utf-8")

        result = config.load_config_result()

        assert result.config["capture"] == "ocr"
        assert any("用户配置无法读取" in warning for warning in result.warnings)
        assert user_path.read_text(encoding="utf-8") == original


def test_unreadable_user_config_falls_back(monkeypatch):
    temp, user_path = _config_paths(monkeypatch)
    with temp:
        user_path.write_text("theme: light", encoding="utf-8")
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path == user_path:
                raise PermissionError("blocked")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", guarded_open)
        result = config.load_config_result()

        assert result.config["theme"] == "dark"
        assert any("PermissionError" in warning for warning in result.warnings)


def test_invalid_field_types_use_safe_defaults(monkeypatch):
    temp, user_path = _config_paths(monkeypatch)
    with temp:
        user_path.write_text(
            "hotkey: []\nlayout: broken\npolicy:\n  auto_scenes: money\n",
            encoding="utf-8",
        )

        result = config.load_config_result()

        assert result.config["hotkey"] == "<ctrl>+<alt>+w"
        assert result.config["layout"]["ocr_min_score"] == 0.75
        assert result.config["policy"]["auto_scenes"] == ["smalltalk", "logistics"]
        assert len(result.warnings) == 3


def test_save_refuses_to_overwrite_malformed_user_config(monkeypatch):
    temp, user_path = _config_paths(monkeypatch)
    with temp:
        original = "llm: [broken"
        user_path.write_text(original, encoding="utf-8")

        try:
            config.save_user_settings(theme="light")
        except ValueError as exc:
            assert "无法安全读取" in str(exc)
        else:
            raise AssertionError("malformed config should not be overwritten")
        assert user_path.read_text(encoding="utf-8") == original


def test_non_finite_number_uses_safe_default(monkeypatch):
    temp, user_path = _config_paths(monkeypatch)
    with temp:
        user_path.write_text("capture_dedup_seconds: .nan\n", encoding="utf-8")

        result = config.load_config_result()

        assert result.config["capture_dedup_seconds"] == 10
        assert any("不是有限数字" in warning for warning in result.warnings)


def test_save_refuses_invalid_llm_section(monkeypatch):
    temp, user_path = _config_paths(monkeypatch)
    with temp:
        original = "llm: []\n"
        user_path.write_text(original, encoding="utf-8")

        try:
            config.save_user_settings(theme="light")
        except ValueError as exc:
            assert "llm 不是对象" in str(exc)
        else:
            raise AssertionError("invalid llm section should not be overwritten")
        assert user_path.read_text(encoding="utf-8") == original


def test_privacy_defaults_are_enabled(monkeypatch):
    temp, _ = _config_paths(monkeypatch)
    with temp:
        result = config.load_config_result()

        assert result.config["privacy"] == {
            "save_source_text": True,
            "save_last_screenshot": True,
        }


def test_save_user_privacy_settings(monkeypatch):
    temp, user_path = _config_paths(monkeypatch)
    with temp:
        config.save_user_settings(
            save_source_text=False,
            save_last_screenshot=False,
        )

        result = config.load_config_result()

        assert result.config["privacy"] == {
            "save_source_text": False,
            "save_last_screenshot": False,
        }
        assert "save_source_text: false" in user_path.read_text(encoding="utf-8")


def test_invalid_privacy_settings_use_safe_defaults(monkeypatch):
    temp, user_path = _config_paths(monkeypatch)
    with temp:
        user_path.write_text(
            "privacy:\n  save_source_text: disabled\n  save_last_screenshot: 1\n",
            encoding="utf-8",
        )

        result = config.load_config_result()

        assert result.config["privacy"] == {
            "save_source_text": True,
            "save_last_screenshot": True,
        }
        assert len(result.warnings) == 2
