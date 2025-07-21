"""設定管理、例外クラス、ファイル管理"""

import os
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv


class InputType(Enum):
    """入力タイプ"""
    FILE = "file"
    YOUTUBE = "youtube"


@dataclass
class TranscriptionResult:
    """書き起こし結果を格納するデータクラス"""
    input_source: str          # 入力ソース（ファイルパス or URL）
    input_type: InputType      # ファイル or YouTube
    raw_text: str             # 生の書き起こしテキスト
    formatted_text: str       # 整形済みテキスト
    summary_text: str         # 要約テキスト
    processing_time: float    # 処理時間（秒）
    audio_duration: float     # 音声長（秒）
    segments_count: int       # 分割数
    created_at: datetime      # 処理日時


@dataclass
class AudioSegment:
    """音声セグメントの情報"""
    segment_id: int           # セグメント番号
    start_time: float         # 開始時間（秒）
    end_time: float          # 終了時間（秒）
    file_path: str           # 一時ファイルパス
    transcription: str = ""  # セグメントの書き起こし結果


# 例外クラス
class TranscriberError(Exception):
    """基底例外クラス"""
    pass


class InputValidationError(TranscriberError):
    """入力検証エラー"""
    pass


class APIError(TranscriberError):
    """API関連エラー"""
    pass


class ProcessingError(TranscriberError):
    """処理エラー"""
    pass


def load_config() -> Dict[str, Any]:
    """環境変数から設定を読み込み"""
    load_dotenv()
    
    return {
        "gemini_api_key": os.getenv("GEMINI_API_KEY"),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "max_audio_duration": int(os.getenv("MAX_AUDIO_DURATION", "1800")),
        "retry_count": int(os.getenv("RETRY_COUNT", "5")),
        "retry_delay": int(os.getenv("RETRY_DELAY", "1")),
        "output_dir": os.getenv("OUTPUT_DIR", "./output"),
        "temp_dir": os.getenv("TEMP_DIR", "./temp"),
    }


def setup_logging(level: str = "INFO") -> None:
    """ログ設定"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
        ]
    )


def load_prompt(prompt_type: str) -> str:
    """プロンプトテンプレート読み込み"""
    prompt_path = Path("prompts") / f"{prompt_type}.txt"
    
    if not prompt_path.exists():
        raise FileNotFoundError(f"プロンプトファイルが見つかりません: {prompt_path}")
    
    return prompt_path.read_text(encoding="utf-8").strip()


def save_results(result: TranscriptionResult, output_dir: str, filename: str = None) -> None:
    """結果を3種類のファイルに保存"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # ファイル名を決定
    if filename:
        # 明示的に指定されたファイル名を使用
        input_name = filename
    elif result.input_type == InputType.YOUTUBE:
        # YouTube URLからファイル名を生成（旧形式、フォールバック用）
        input_name = "youtube_video"
    else:
        # ファイルパスからファイル名を取得
        input_name = Path(result.input_source).stem
    
    # 3種類のファイルに保存
    files = {
        f"{input_name}_raw.txt": result.raw_text,
        f"{input_name}_formatted.txt": result.formatted_text,
        f"{input_name}_summary.txt": result.summary_text,
    }
    
    for filename, content in files.items():
        file_path = output_path / filename
        file_path.write_text(content, encoding="utf-8")