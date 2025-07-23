"""音声処理（ファイル・YouTube）"""

import os
import logging
import tempfile
import shutil
import uuid
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

import yt_dlp
from pydub import AudioSegment as PyDubAudioSegment
from pydub.silence import detect_silence

from .config import (
    AudioSegment, 
    InputType, 
    InputValidationError, 
    ProcessingError,
    load_config
)


logger = logging.getLogger(__name__)


class AudioProcessor:
    """音声処理クラス"""
    
    def __init__(self):
        """初期化"""
        self.config = load_config()
        # プロセス固有の一時ディレクトリを作成
        base_temp_dir = Path(self.config["temp_dir"])
        self.session_id = str(uuid.uuid4())[:8]
        self.temp_dir = base_temp_dir / f"transcriber_{self.session_id}"
        
        # ディレクトリ作成（Vercel環境での読み取り専用エラーを回避）
        try:
            self.temp_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            # Vercel環境では/tmpディレクトリは既に存在するため、作成不要
            if not self.temp_dir.exists():
                raise ProcessingError(f"一時ディレクトリの作成に失敗しました: {e}")
            
        self.is_vercel = self.config.get("is_vercel", False)
        
        # 対応音声形式
        self.supported_formats = {'.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg'}
        
        # YouTube動画情報保存用
        self.youtube_info = None
        
    def process_input(self, input_source: str) -> Tuple[str, InputType]:
        """入力処理（ファイル/URL判定・前処理）"""
        logger.info(f"入力処理開始: {input_source}")
        
        # YouTube URL判定
        if self._is_youtube_url(input_source):
            logger.info("YouTube URLとして処理")
            audio_path = self.download_youtube_audio(input_source)
            return audio_path, InputType.YOUTUBE
        
        # ローカルファイル判定
        file_path = Path(input_source)
        if not file_path.exists():
            raise InputValidationError(f"ファイルが見つかりません: {input_source}")
        
        if not file_path.is_file():
            raise InputValidationError(f"指定されたパスはファイルではありません: {input_source}")
        
        # 音声形式チェック
        if file_path.suffix.lower() not in self.supported_formats:
            raise InputValidationError(
                f"対応していない音声形式です: {file_path.suffix}\n"
                f"対応形式: {', '.join(self.supported_formats)}"
            )
        
        logger.info("ローカルファイルとして処理")
        # 必要に応じて音声形式変換
        converted_path = self.convert_audio_format(str(file_path))
        
        # ローカルファイルの場合、ファイル名情報を設定
        self.youtube_info = {
            'title': file_path.stem,
            'uploader': None,
            'duration': 0,
            'url': None
        }
        
        return converted_path, InputType.FILE
    
    def _is_youtube_url(self, url: str) -> bool:
        """YouTube URL判定"""
        youtube_domains = [
            'youtube.com', 'www.youtube.com', 'm.youtube.com',
            'youtu.be', 'www.youtu.be'
        ]
        
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() in youtube_domains
        except Exception:
            return False
    
    def download_youtube_audio(self, url: str) -> str:
        """YouTube音声ダウンロード"""
        from rich.console import Console
        console = Console()
        
        console.print(f"[bold blue]🔗 YouTube URL:[/bold blue] {url}")
        console.print("[cyan]📥 動画情報を取得中...[/cyan]")
        
        try:
            # 一時ファイル名生成
            temp_file = self.temp_dir / f"youtube_audio_{int(time.time())}"
            
            # yt-dlp設定（ボット対策強化）
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': str(temp_file) + '.%(ext)s',
                'noplaylist': True,
                'extract_flat': False,
                'quiet': True,  # yt-dlpの出力を抑制
                'no_warnings': True,
                # ボット対策の設定
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'referer': 'https://www.youtube.com/',
                'headers': {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                    'Keep-Alive': '300',
                    'Connection': 'keep-alive',
                },
                # 追加の回避設定
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash', 'hls'],
                        'player_skip': ['configs'],
                    }
                },
                'sleep_interval': 1,  # リクエスト間隔
                'max_sleep_interval': 5,
                # より詳細な設定
                'socket_timeout': 30,
                'retries': 3,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 最初に情報のみ取得
                try:
                    info = ydl.extract_info(url, download=False)
                except yt_dlp.utils.ExtractorError as e:
                    error_msg = str(e)
                    if "Video unavailable" in error_msg:
                        raise ProcessingError("動画が利用できません。プライベート動画、削除された動画、または地域制限がある可能性があります。")
                    elif "Sign in to confirm your age" in error_msg:
                        raise ProcessingError("年齢制限のある動画です。このサービスでは処理できません。")
                    elif "Private video" in error_msg:
                        raise ProcessingError("プライベート動画です。公開動画のURLを使用してください。")
                    else:
                        raise ProcessingError(f"YouTube動画情報の取得に失敗しました: {error_msg}")
                except Exception as e:
                    raise ProcessingError(f"YouTube処理中にエラーが発生しました: {str(e)}")
                
                # 動画情報を保存
                title = info.get('title', 'Unknown Title')
                uploader = info.get('uploader', 'Unknown Channel')
                duration = info.get('duration', 0)
                
                self.youtube_info = {
                    'title': title,
                    'uploader': uploader,
                    'duration': duration,
                    'url': url
                }
                
                # 動画情報を表示
                console.print(f"[green]📺 タイトル:[/green] {title}")
                console.print(f"[green]👤 チャンネル:[/green] {uploader}")
                console.print(f"[green]⏱️  長さ:[/green] {duration//60:.0f}分{duration%60:.0f}秒")
                console.print("[cyan]⬇️  音声をダウンロード中...[/cyan]")
                
                # 実際のダウンロード実行
                ydl.download([url])
                
                # ダウンロードされたファイル名を特定
                downloaded_file = None
                for ext in ['webm', 'm4a', 'mp3', 'wav']:
                    potential_file = temp_file.with_suffix(f'.{ext}')
                    if potential_file.exists():
                        downloaded_file = potential_file
                        break
                
                if not downloaded_file:
                    raise ProcessingError("ダウンロードされたファイルが見つかりません")
                
                # MP3に変換
                mp3_file = self.convert_audio_format(str(downloaded_file))
                
                # 元ファイル削除
                if downloaded_file.exists():
                    downloaded_file.unlink()
                
                logger.info(f"YouTube音声ダウンロード完了: {mp3_file}")
                return mp3_file
                
        except Exception as e:
            error_str = str(e)
            logger.error(f"YouTube音声ダウンロードエラー: {error_str}")
            
            # ボット検出の場合の特別なメッセージ
            if "Sign in to confirm you're not a bot" in error_str:
                raise ProcessingError(
                    "YouTubeがボット検出を行っています。しばらく時間をおいてから再試行するか、"
                    "別の動画URLをお試しください。一般公開されている動画をご利用ください。"
                )
            elif "Private video" in error_str:
                raise ProcessingError("プライベート動画はアクセスできません。一般公開されている動画をお試しください。")
            elif "This video is unavailable" in error_str:
                raise ProcessingError("この動画は利用できません。URLを確認するか、別の動画をお試しください。")
            else:
                raise ProcessingError(f"YouTube音声ダウンロードに失敗しました: {error_str}")
    
    def convert_audio_format(self, input_path: str) -> str:
        """音声形式変換（MP3への統一）"""
        input_file = Path(input_path)
        
        # 既にMP3の場合はそのまま返す
        if input_file.suffix.lower() == '.mp3':
            logger.debug(f"既にMP3形式: {input_path}")
            return input_path
        
        logger.info(f"音声形式変換開始: {input_path} -> MP3")
        
        try:
            # 音声読み込み
            audio = PyDubAudioSegment.from_file(input_path)
            
            # MP3として出力
            output_path = self.temp_dir / f"converted_{input_file.stem}.mp3"
            audio.export(str(output_path), format="mp3")
            
            logger.info(f"音声形式変換完了: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"音声形式変換エラー: {e}")
            raise ProcessingError(f"音声形式変換に失敗しました: {e}")
    
    def split_audio_if_needed(self, audio_path: str) -> List[AudioSegment]:
        """音声分割（必要に応じて）"""
        logger.info(f"音声分割チェック開始: {audio_path}")
        
        try:
            # 高速化: メタデータから音声長を取得（音声を読み込まない）
            duration = self._get_duration_fast(audio_path)
            logger.info(f"音声長: {duration:.1f}秒")
            
            max_duration = self.config["max_audio_duration"]
            
            # 分割不要の場合
            if duration <= max_duration:
                logger.info("分割不要")
                return [AudioSegment(
                    segment_id=0,
                    start_time=0.0,
                    end_time=duration,
                    file_path=audio_path
                )]
            
            logger.info(f"長時間音声のため分割実行（上限: {max_duration}秒）")
            
            # 高速化: 非常に長い音声（3倍以上）は無音検出をスキップ
            if duration > max_duration * 3:
                logger.info("非常に長い音声のため固定時間分割を使用")
                audio = PyDubAudioSegment.from_file(audio_path)
                segments = self._split_by_time(audio, max_duration)
            else:
                # 音声読み込み（必要な場合のみ）
                audio = PyDubAudioSegment.from_file(audio_path)
                
                # 無音部分での分割を試行（高速パラメータ使用）
                segments = self._split_by_silence_fast(audio, max_duration)
                
                # 無音部分での分割に失敗した場合は固定時間で分割
                if not segments:
                    logger.info("無音分割に失敗、固定時間で分割")
                    segments = self._split_by_time(audio, max_duration)
            
            logger.info(f"音声分割完了: {len(segments)}セグメント")
            return segments
            
        except Exception as e:
            logger.error(f"音声分割エラー: {e}")
            raise ProcessingError(f"音声分割に失敗しました: {e}")
    
    def _split_by_silence_fast(self, audio: PyDubAudioSegment, max_duration: int) -> List[AudioSegment]:
        """無音部分での分割（高速版）"""
        logger.info("無音部分での分割を試行（高速モード）")
        
        try:
            # 高速化: より大きな無音間隔と緩い閾値で検出
            silence_ranges = detect_silence(
                audio,
                min_silence_len=3000,  # 3秒以上の無音（高速化）
                silence_thresh=-35,    # -35dB以下を無音（緩い条件で高速化）
                seek_step=1000         # 1秒ステップで検索（高速化）
            )
            
            if not silence_ranges:
                logger.info("無音部分が見つかりません")
                return []
            
            segments = []
            current_start = 0
            segment_id = 0
            
            for silence_start, silence_end in silence_ranges:
                # セグメント長チェック
                segment_duration = (silence_start - current_start) / 1000.0
                
                if segment_duration >= max_duration:
                    # 無音部分で分割
                    segment_file = self._save_segment(
                        audio, current_start, silence_start, segment_id
                    )
                    
                    segments.append(AudioSegment(
                        segment_id=segment_id,
                        start_time=current_start / 1000.0,
                        end_time=silence_start / 1000.0,
                        file_path=segment_file
                    ))
                    
                    current_start = silence_end
                    segment_id += 1
            
            # 最後のセグメント
            if current_start < len(audio):
                segment_file = self._save_segment(
                    audio, current_start, len(audio), segment_id
                )
                
                segments.append(AudioSegment(
                    segment_id=segment_id,
                    start_time=current_start / 1000.0,
                    end_time=len(audio) / 1000.0,
                    file_path=segment_file
                ))
            
            return segments
            
        except Exception as e:
            logger.warning(f"無音分割に失敗: {e}")
            return []
    
    def _split_by_time(self, audio: PyDubAudioSegment, max_duration: int) -> List[AudioSegment]:
        """固定時間での分割"""
        logger.info(f"固定時間での分割: {max_duration}秒間隔")
        
        segments = []
        segment_duration_ms = max_duration * 1000
        total_duration = len(audio)
        
        for i, start_ms in enumerate(range(0, total_duration, segment_duration_ms)):
            end_ms = min(start_ms + segment_duration_ms, total_duration)
            
            segment_file = self._save_segment(audio, start_ms, end_ms, i)
            
            segments.append(AudioSegment(
                segment_id=i,
                start_time=start_ms / 1000.0,
                end_time=end_ms / 1000.0,
                file_path=segment_file
            ))
        
        return segments
    
    def _save_segment(self, audio: PyDubAudioSegment, start_ms: int, end_ms: int, segment_id: int) -> str:
        """セグメントをファイルに保存"""
        segment = audio[start_ms:end_ms]
        output_path = self.temp_dir / f"segment_{segment_id}.mp3"
        segment.export(str(output_path), format="mp3")
        return str(output_path)
    
    def _get_duration_fast(self, audio_path: str) -> float:
        """音声長を高速取得（メタデータベース）"""
        try:
            # 高速化: ffprobeを使用してメタデータから取得
            import subprocess
            import json
            
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', audio_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                info = json.loads(result.stdout)
                duration = float(info['format']['duration'])
                return duration
        except Exception:
            # ffprobeが失敗した場合はpydubで取得
            pass
            
        try:
            audio = PyDubAudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except Exception as e:
            logger.error(f"音声長取得エラー: {e}")
            return 0.0
    
    def get_audio_duration(self, audio_path: str) -> float:
        """音声長を取得（秒）"""
        return self._get_duration_fast(audio_path)
    
    def get_safe_filename(self) -> str:
        """安全なファイル名を生成"""
        if not self.youtube_info:
            return "audio_file"
        
        try:
            title = self.youtube_info.get('title', 'Unknown Title')
            uploader = self.youtube_info.get('uploader')
            
            # ファイル名に使用できない文字を置換
            import re
            safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
            safe_title = safe_title.strip().replace(' ', '_')
            
            if uploader:
                safe_uploader = re.sub(r'[<>:"/\\|?*]', '_', uploader)
                safe_uploader = safe_uploader.strip().replace(' ', '_')
                # タイトルが長い場合は切り詰める
                if len(safe_title) > 50:
                    safe_title = safe_title[:50]
                return f"{safe_uploader}_{safe_title}"
            else:
                # ローカルファイルの場合
                if len(safe_title) > 60:
                    safe_title = safe_title[:60]
                return safe_title
        except Exception as e:
            logger.warning(f"ファイル名生成エラー: {e}")
            return "audio_file"
    
    def cleanup_temp_files(self) -> None:
        """このプロセス専用の一時ファイル削除"""
        logger.info(f"一時ファイル削除開始 (session: {self.session_id})")
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                logger.info(f"一時ファイル削除完了 (session: {self.session_id})")
        except Exception as e:
            logger.warning(f"一時ファイル削除エラー (session: {self.session_id}): {e}")


# 必要なimportを追加
import time