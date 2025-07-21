"""Gemini API クライアント"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, Callable, Any
from pathlib import Path

import google.generativeai as genai

from .config import APIError, load_config


logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """トークン使用量情報"""
    input_tokens: int = 0
    output_tokens: int = 0
    audio_input_tokens: int = 0
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.audio_input_tokens
    
    def calculate_cost(self, model: str) -> float:
        """料金を計算（USD）"""
        if "2.5-flash" in model.lower():
            # Gemini 2.5 Flash料金
            text_input_cost = (self.input_tokens / 1_000_000) * 0.30
            audio_input_cost = (self.audio_input_tokens / 1_000_000) * 1.00
            output_cost = (self.output_tokens / 1_000_000) * 2.50
            return text_input_cost + audio_input_cost + output_cost
        elif "2.5-pro" in model.lower():
            # Gemini 2.5 Pro料金（200k以下として計算）
            input_cost = (self.input_tokens / 1_000_000) * 1.25
            output_cost = (self.output_tokens / 1_000_000) * 10.00
            return input_cost + output_cost
        else:
            return 0.0
    
    def __add__(self, other):
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            audio_input_tokens=self.audio_input_tokens + other.audio_input_tokens
        )


class GeminiClient:
    """Gemini API クライアント"""
    
    def __init__(self, api_key: str, model: str):
        """クライアント初期化"""
        if not api_key:
            raise APIError("Gemini API キーが設定されていません")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
        self.model_name = model
        self.config = load_config()
        self.total_usage = TokenUsage()
        
        logger.info(f"Gemini クライアント初期化完了: {model}")
    
    async def transcribe_audio(self, audio_path: str, prompt: str) -> str:
        """音声書き起こし"""
        logger.info(f"音声書き起こし開始: {audio_path}")
        
        try:
            # 音声ファイルをアップロード
            audio_file = genai.upload_file(path=audio_path)
            logger.debug(f"音声ファイルアップロード完了: {audio_file.name}")
            
            # プロンプトと音声でコンテンツ生成
            response = await self._retry_with_backoff(
                self._generate_content,
                [prompt, audio_file]
            )
            
            # トークン使用量を記録
            usage = self._extract_token_usage(response, is_audio=True)
            self.total_usage += usage
            
            logger.info("音声書き起こし完了")
            return response.text
            
        except Exception as e:
            logger.error(f"音声書き起こしエラー: {e}")
            raise APIError(f"音声書き起こしに失敗しました: {e}")
    
    async def format_text(self, raw_text: str, prompt: str) -> str:
        """テキスト整形"""
        logger.info("テキスト整形開始")
        
        try:
            full_prompt = f"{prompt}\n\n{raw_text}"
            
            response = await self._retry_with_backoff(
                self._generate_content,
                full_prompt
            )
            
            # トークン使用量を記録
            usage = self._extract_token_usage(response)
            self.total_usage += usage
            
            logger.info("テキスト整形完了")
            return response.text
            
        except Exception as e:
            logger.error(f"テキスト整形エラー: {e}")
            raise APIError(f"テキスト整形に失敗しました: {e}")
    
    async def summarize_text(self, text: str, prompt: str) -> str:
        """テキスト要約"""
        logger.info("テキスト要約開始")
        
        try:
            full_prompt = f"{prompt}\n\n{text}"
            
            response = await self._retry_with_backoff(
                self._generate_content,
                full_prompt
            )
            
            # トークン使用量を記録
            usage = self._extract_token_usage(response)
            self.total_usage += usage
            
            logger.info("テキスト要約完了")
            return response.text
            
        except Exception as e:
            logger.error(f"テキスト要約エラー: {e}")
            raise APIError(f"テキスト要約に失敗しました: {e}")
    
    async def _generate_content(self, content):
        """コンテンツ生成（同期関数を非同期で実行）"""
        # 同期関数を非同期で実行
        return await asyncio.get_event_loop().run_in_executor(
            None, self.model.generate_content, content
        )
    
    async def _retry_with_backoff(self, func: Callable, *args, **kwargs) -> Any:
        """リトライ機能（指数バックオフ）"""
        retry_count = self.config["retry_count"]
        retry_delay = self.config["retry_delay"]
        
        for attempt in range(retry_count):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
                    
            except Exception as e:
                if attempt == retry_count - 1:
                    # 最後の試行で失敗した場合は例外を再発生
                    raise e
                
                # リトライ対象のエラーかチェック
                if not self._is_retryable_error(e):
                    raise e
                
                # 指数バックオフで待機
                wait_time = retry_delay * (2 ** attempt)
                logger.warning(f"APIエラー（試行 {attempt + 1}/{retry_count}）: {e}")
                logger.info(f"{wait_time}秒後にリトライします...")
                
                await asyncio.sleep(wait_time)
        
        raise APIError("リトライ回数を超過しました")
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """リトライ可能なエラーかどうかを判定"""
        error_str = str(error).lower()
        
        # リトライ対象のエラーパターン
        retryable_patterns = [
            "rate limit",
            "quota exceeded",
            "timeout",
            "connection error",
            "server error",
            "503",
            "502",
            "500",
        ]
        
        return any(pattern in error_str for pattern in retryable_patterns)
    
    def _extract_token_usage(self, response, is_audio: bool = False) -> TokenUsage:
        """レスポンスからトークン使用量を抽出"""
        try:
            if hasattr(response, 'usage_metadata'):
                metadata = response.usage_metadata
                
                input_tokens = getattr(metadata, 'prompt_token_count', 0)
                output_tokens = getattr(metadata, 'candidates_token_count', 0)
                
                if is_audio:
                    # 音声入力の場合はaudio_input_tokensとして記録
                    return TokenUsage(
                        input_tokens=0,
                        output_tokens=output_tokens,
                        audio_input_tokens=input_tokens
                    )
                else:
                    return TokenUsage(
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        audio_input_tokens=0
                    )
            else:
                logger.warning("レスポンスにusage_metadataが含まれていません")
                return TokenUsage()
                
        except Exception as e:
            logger.warning(f"トークン使用量の抽出に失敗: {e}")
            return TokenUsage()
    
    def get_total_usage(self) -> TokenUsage:
        """総トークン使用量を取得"""
        return self.total_usage
    
    def get_cost_summary(self) -> dict:
        """コスト情報のサマリーを取得"""
        cost_usd = self.total_usage.calculate_cost(self.model_name)
        cost_jpy = cost_usd * 150  # 仮の為替レート（実際には動的に取得すべき）
        
        return {
            "total_tokens": self.total_usage.total_tokens,
            "input_tokens": self.total_usage.input_tokens,
            "output_tokens": self.total_usage.output_tokens,
            "audio_input_tokens": self.total_usage.audio_input_tokens,
            "cost_usd": cost_usd,
            "cost_jpy": cost_jpy,
            "model": self.model_name
        }