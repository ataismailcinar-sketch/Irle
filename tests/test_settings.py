# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Settings Loader (src/irle/app/settings.py)
=============================================================================
Ortam değişkeni mocklaması ile ayar yükleme mantığını test eder.
"""

import os
import pytest

from irle.app.settings import Settings


class TestSettingsVarsayilanlar:
    """Ortam değişkeni yokken varsayılan değerler."""

    def setup_method(self):
        """Test öncesi ilgili env değişkenlerini temizle."""
        env_keys = [
            "IRLE_GEMINI_API_KEY", "IRLE_GEMINI_MODEL",
            "IRLE_TTS_RATE", "IRLE_TTS_VOLUME", "IRLE_SILENT_MODE",
            "IRLE_SPEECH_LANG", "IRLE_MEMORY_MAX", "IRLE_LOG_LEVEL",
            "IRLE_CAMERA_ID",
        ]
        for key in env_keys:
            os.environ.pop(key, None)

    def test_tts_rate_varsayilan(self):
        s = Settings()
        assert s.tts_rate == 165

    def test_tts_volume_varsayilan(self):
        s = Settings()
        assert s.tts_volume == 1.0

    def test_silent_mode_varsayilan(self):
        s = Settings()
        assert s.tts_silent_mode is False

    def test_speech_language_varsayilan(self):
        s = Settings()
        assert s.speech_language == "tr-TR"

    def test_memory_max_varsayilan(self):
        s = Settings()
        assert s.memory_max_records == 500

    def test_log_level_varsayilan(self):
        s = Settings()
        assert s.log_level == "INFO"

    def test_camera_id_varsayilan(self):
        s = Settings()
        assert s.camera_id == 0


class TestSettingsEnvVarsayilan:
    """Ortam değişkeni ile değer override."""

    def test_tts_rate_override(self, monkeypatch):
        monkeypatch.setenv("IRLE_TTS_RATE", "200")
        s = Settings()
        assert s.tts_rate == 200

    def test_tts_volume_override(self, monkeypatch):
        monkeypatch.setenv("IRLE_TTS_VOLUME", "0.5")
        s = Settings()
        assert abs(s.tts_volume - 0.5) < 1e-6

    def test_silent_mode_true(self, monkeypatch):
        monkeypatch.setenv("IRLE_SILENT_MODE", "true")
        s = Settings()
        assert s.tts_silent_mode is True

    def test_silent_mode_1(self, monkeypatch):
        monkeypatch.setenv("IRLE_SILENT_MODE", "1")
        s = Settings()
        assert s.tts_silent_mode is True

    def test_silent_mode_evet(self, monkeypatch):
        monkeypatch.setenv("IRLE_SILENT_MODE", "evet")
        s = Settings()
        assert s.tts_silent_mode is True

    def test_silent_mode_false(self, monkeypatch):
        monkeypatch.setenv("IRLE_SILENT_MODE", "false")
        s = Settings()
        assert s.tts_silent_mode is False

    def test_speech_language_override(self, monkeypatch):
        monkeypatch.setenv("IRLE_SPEECH_LANG", "en-US")
        s = Settings()
        assert s.speech_language == "en-US"

    def test_memory_max_override(self, monkeypatch):
        monkeypatch.setenv("IRLE_MEMORY_MAX", "100")
        s = Settings()
        assert s.memory_max_records == 100

    def test_log_level_override(self, monkeypatch):
        monkeypatch.setenv("IRLE_LOG_LEVEL", "DEBUG")
        s = Settings()
        assert s.log_level == "DEBUG"

    def test_camera_id_override(self, monkeypatch):
        monkeypatch.setenv("IRLE_CAMERA_ID", "1")
        s = Settings()
        assert s.camera_id == 1


class TestSettingsGeçersizDegerler:
    """Geçersiz env değişkeni değerleri varsayılana düşmeli."""

    def test_tts_rate_gecersiz_string(self, monkeypatch):
        monkeypatch.setenv("IRLE_TTS_RATE", "gecersiz")
        s = Settings()
        assert s.tts_rate == 165  # varsayılan

    def test_tts_volume_gecersiz(self, monkeypatch):
        monkeypatch.setenv("IRLE_TTS_VOLUME", "abc")
        s = Settings()
        assert s.tts_volume == 1.0  # varsayılan

    def test_memory_max_gecersiz(self, monkeypatch):
        monkeypatch.setenv("IRLE_MEMORY_MAX", "yüz")
        s = Settings()
        assert s.memory_max_records == 500  # varsayılan


class TestSettingsRepr:
    """__repr__ formatını kontrol eder."""

    def test_repr_format(self):
        s = Settings()
        r = repr(s)
        assert "Settings(" in r
        assert "tts_rate=" in r
        assert "tts_silent_mode=" in r
        assert "speech_language=" in r
        assert "log_level=" in r


class TestSettingsAppCommands:
    """Uygulama komut haritası sabit, ortam değişkeninden etkilenmemeli."""

    def test_notepad_var(self):
        s = Settings()
        assert "notepad" in s.app_commands
        assert s.app_commands["notepad"] == "notepad.exe"

    def test_chrome_var(self):
        s = Settings()
        assert "chrome" in s.app_commands
