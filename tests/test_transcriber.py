import os
import pytest
from unittest.mock import patch, MagicMock
from transcriber.config import load_config, InputType, InputValidationError, ProcessingError
from transcriber.audio import AudioProcessor
from pathlib import Path
import shutil

# config.py のテスト
def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test_api_key")
    config = load_config()
    assert config["gemini_api_key"] == "test_api_key"

@patch('transcriber.config.load_dotenv')
def test_load_config_no_env(mock_load_dotenv, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    config = load_config()
    assert config["gemini_api_key"] is None

# audio.py のテスト
@pytest.fixture
def audio_processor_mock_config(mocker):
    mocker.patch('transcriber.config.load_config', return_value={
        "temp_dir": "./temp_test",
        "max_audio_duration": 1800,
        "gemini_api_key": "dummy_key"
    })
    # temp_test ディレクトリが存在しない場合、作成する
    temp_test_dir = Path("./temp_test")
    temp_test_dir.mkdir(exist_ok=True)
    yield AudioProcessor()
    # テスト後に temp_test ディレクトリを削除する
    if temp_test_dir.exists():
        shutil.rmtree(temp_test_dir)

def test_is_youtube_url():
    processor = AudioProcessor()
    assert processor._is_youtube_url("https://www.youtube.com/watch?v=test") is True
    assert processor._is_youtube_url("https://youtu.be/test") is True
    assert processor._is_youtube_url("https://example.com/video") is False

@patch('transcriber.audio.AudioProcessor.download_youtube_audio')
@patch('pathlib.Path.exists', return_value=True)
@patch('pathlib.Path.is_file', return_value=True)
def test_process_input_local_file(mock_is_file, mock_exists, mock_download_youtube_audio, audio_processor_mock_config, mocker):
    processor = audio_processor_mock_config
    mocker.patch('pathlib.Path.suffix', new_callable=mocker.PropertyMock, return_value='.mp3')
    
    # ローカルファイルの場合
    audio_path, input_type = processor.process_input("/path/to/local_audio.mp3")
    assert audio_path == "/path/to/local_audio.mp3"
    assert input_type == InputType.FILE
    mock_download_youtube_audio.assert_not_called()
    mock_exists.assert_called_once()
    mock_is_file.assert_called_once()

@patch('transcriber.audio.AudioProcessor.download_youtube_audio', return_value="/path/to/downloaded_audio.mp3")
@patch('pathlib.Path.exists', return_value=False)
def test_process_input_youtube_url(mock_exists, mock_download_youtube_audio, audio_processor_mock_config):
    processor = audio_processor_mock_config
    
    # YouTube URLの場合
    audio_path, input_type = processor.process_input("https://www.youtube.com/watch?v=test")
    assert audio_path == "/path/to/downloaded_audio.mp3"
    assert input_type == InputType.YOUTUBE
    mock_download_youtube_audio.assert_called_once_with("https://www.youtube.com/watch?v=test")
    mock_exists.assert_not_called()

def test_process_input_file_not_found(audio_processor_mock_config):
    processor = audio_processor_mock_config
    with pytest.raises(InputValidationError, match="ファイルが見つかりません"):
        processor.process_input("/path/to/non_existent_file.mp3")

def test_process_input_unsupported_format(audio_processor_mock_config, mocker):
    processor = audio_processor_mock_config
    mocker.patch('pathlib.Path.exists', return_value=True)
    mocker.patch('pathlib.Path.is_file', return_value=True)
    mocker.patch('pathlib.Path.suffix', new_callable=mocker.PropertyMock, return_value='.txt')
    with pytest.raises(InputValidationError, match="対応していない音声形式です"):
        processor.process_input("/path/to/document.txt")

@patch('transcriber.audio.yt_dlp.YoutubeDL')
@patch('transcriber.audio.AudioProcessor.convert_audio_format', return_value="/path/to/converted_audio.mp3")
@patch('pathlib.Path.exists', return_value=True)
@patch('pathlib.Path.unlink')
@patch('time.time', return_value=1234567890)
@patch('rich.console.Console')
def test_download_youtube_audio_success(mock_console, mock_time, mock_unlink, mock_path_exists, mock_convert_audio_format, mock_youtube_dl, audio_processor_mock_config, mocker):
    processor = audio_processor_mock_config
    
    # Mock YoutubeDL instance and its methods
    mock_ydl_instance = MagicMock()
    mock_youtube_dl.return_value.__enter__.return_value = mock_ydl_instance
    
    mock_ydl_instance.extract_info.return_value = {
        'title': 'Test Video',
        'uploader': 'Test Channel',
        'duration': 300,
        'url': 'https://www.youtube.com/watch?v=test',
    }
    
    # Simulate downloaded file existence
    mocker.patch('pathlib.Path.with_suffix', side_effect=lambda ext: Path(f"./temp_test/youtube_audio_1234567890{ext}"))
    
    # Ensure the mocked downloaded file exists for the check
    mock_path_exists.side_effect = lambda: True

    audio_path = processor.download_youtube_audio("https://www.youtube.com/watch?v=test")
    
    mock_youtube_dl.assert_called_once()
    mock_ydl_instance.extract_info.assert_called_once_with("https://www.youtube.com/watch?v=test", download=False)
    mock_ydl_instance.download.assert_called_once_with(["https://www.youtube.com/watch?v=test"])
    mock_convert_audio_format.assert_called_once()
    mock_unlink.assert_called_once()
    assert audio_path == "/path/to/converted_audio.mp3"
    assert processor.youtube_info['title'] == 'Test Video'

@patch('transcriber.audio.yt_dlp.YoutubeDL')
@patch('time.time', return_value=1234567890)
@patch('rich.console.Console')
def test_download_youtube_audio_failure(mock_console, mock_time, mock_youtube_dl, audio_processor_mock_config):
    processor = audio_processor_mock_config
    
    mock_ydl_instance = MagicMock()
    mock_youtube_dl.return_value.__enter__.return_value = mock_ydl_instance
    mock_ydl_instance.extract_info.return_value = {
        'title': 'Test Video',
        'uploader': 'Test Channel',
        'duration': 300,
        'url': 'https://www.youtube.com/watch?v=test',
    }
    mock_ydl_instance.download.side_effect = Exception("Download failed")
    
    with pytest.raises(ProcessingError, match="YouTube音声ダウンロードに失敗しました"):
        processor.download_youtube_audio("https://www.youtube.com/watch?v=test")
    
    mock_youtube_dl.assert_called_once()
    mock_ydl_instance.download.assert_called_once_with(["https://www.youtube.com/watch?v=test"])

@patch('transcriber.audio.PyDubAudioSegment.from_file')
@patch('transcriber.audio.PyDubAudioSegment.export')
def test_convert_audio_format_to_mp3(mock_export, mock_from_file, audio_processor_mock_config, mocker):
    processor = audio_processor_mock_config
    mock_audio_segment = MagicMock()
    mock_from_file.return_value = mock_audio_segment
    
    input_path = "/path/to/audio.wav"
    output_path = processor.convert_audio_format(input_path)
    
    mock_from_file.assert_called_once_with(input_path)
    mock_audio_segment.export.assert_called_once()
    assert output_path.endswith(".mp3")
    assert "converted_audio" in output_path

def test_convert_audio_format_already_mp3(audio_processor_mock_config):
    processor = audio_processor_mock_config
    input_path = "/path/to/audio.mp3"
    output_path = processor.convert_audio_format(input_path)
    assert output_path == input_path

@patch('transcriber.audio.PyDubAudioSegment.from_file', side_effect=Exception("Corrupt file"))
def test_convert_audio_format_failure(mock_from_file, audio_processor_mock_config):
    processor = audio_processor_mock_config
    input_path = "/path/to/corrupt.wav"
    with pytest.raises(ProcessingError, match="音声形式変換に失敗しました"):
        processor.convert_audio_format(input_path)

@patch('transcriber.audio.AudioProcessor._get_duration_fast', return_value=100)
def test_split_audio_if_needed_no_split(mock_get_duration_fast, audio_processor_mock_config):
    processor = audio_processor_mock_config
    audio_path = "/path/to/short_audio.mp3"
    segments = processor.split_audio_if_needed(audio_path)
    
    assert len(segments) == 1
    assert segments[0].segment_id == 0
    assert segments[0].start_time == 0.0
    assert segments[0].end_time == 100.0
    assert segments[0].file_path == audio_path
    mock_get_duration_fast.assert_called_once_with(audio_path)

@patch('transcriber.audio.AudioProcessor._get_duration_fast', return_value=2000)
@patch('transcriber.audio.PyDubAudioSegment.from_file')
@patch('transcriber.audio.detect_silence', return_value=[(1800000, 1801000)]) # 1800s
@patch('transcriber.audio.AudioProcessor._save_segment', side_effect=lambda audio, start, end, id: f"segment_{id}.mp3")
def test_split_audio_if_needed_with_silence_split(mock_save_segment, mock_detect_silence, mock_from_file, mock_get_duration_fast, audio_processor_mock_config, mocker):
    processor = audio_processor_mock_config
    mock_audio_segment = MagicMock()
    mock_audio_segment.__len__.return_value = 2000 * 1000 # 2000 seconds in ms
    mock_from_file.return_value = mock_audio_segment
    
    audio_path = "/path/to/long_audio.mp3"
    segments = processor.split_audio_if_needed(audio_path)
    
    assert len(segments) == 2 # 0-1800, 1801-2000
    assert segments[0].segment_id == 0
    assert segments[0].start_time == 0.0
    assert segments[0].end_time == 1800.0
    assert segments[1].segment_id == 1
    assert segments[1].start_time == 1801.0
    assert segments[1].end_time == 2000.0
    
    mock_get_duration_fast.assert_called_once_with(audio_path)
    mock_from_file.assert_called_once_with(audio_path)
    mock_detect_silence.assert_called_once()
    assert mock_save_segment.call_count == 2

@patch('transcriber.audio.AudioProcessor._get_duration_fast', return_value=2000)
@patch('transcriber.audio.PyDubAudioSegment.from_file')
@patch('transcriber.audio.detect_silence', return_value=[]) # No silence detected
@patch('transcriber.audio.AudioProcessor._save_segment', side_effect=lambda audio, start, end, id: f"segment_{id}.mp3")
def test_split_audio_if_needed_with_time_split(mock_save_segment, mock_detect_silence, mock_from_file, mock_get_duration_fast, audio_processor_mock_config, mocker):
    processor = audio_processor_mock_config
    mock_audio_segment = MagicMock()
    mock_audio_segment.__len__.return_value = 2000 * 1000 # 2000 seconds in ms
    mock_from_file.return_value = mock_audio_segment
    
    audio_path = "/path/to/long_audio.mp3"
    segments = processor.split_audio_if_needed(audio_path)
    
    assert len(segments) == 2 # 0-1800, 1800-2000 (max_audio_duration is 1800)
    assert segments[0].segment_id == 0
    assert segments[0].start_time == 0.0
    assert segments[0].end_time == 1800.0
    assert segments[1].segment_id == 1
    assert segments[1].start_time == 1800.0
    assert segments[1].end_time == 2000.0
    
    mock_get_duration_fast.assert_called_once_with(audio_path)
    mock_from_file.assert_called_once_with(audio_path)
    mock_detect_silence.assert_called_once()
    assert mock_save_segment.call_count == 2

