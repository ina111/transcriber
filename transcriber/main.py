"""CLI インターフェース（Click使用）"""

import asyncio
import time
from datetime import datetime

import click
from rich.console import Console
from rich.live import Live
from rich.text import Text

from .config import (
    load_config,
    setup_logging,
    load_prompt,
    save_results,
    TranscriptionResult,
)
from .audio import AudioProcessor
from .gemini import GeminiClient


@click.command()
@click.argument('input_source')
@click.option('--output-dir', default='./output', help='出力ディレクトリ')
@click.option('--format-only', is_flag=True, help='整形のみ実行')
@click.option('--summarize-only', is_flag=True, help='要約のみ実行')
@click.option('--verbose', is_flag=True, help='詳細ログ表示')
def transcribe(input_source: str, output_dir: str, format_only: bool, 
               summarize_only: bool, verbose: bool):
    """音声ファイルまたはYouTube URLを書き起こし"""
    
    # ログ設定
    if verbose:
        setup_logging("DEBUG")
    else:
        # 通常実行時はログを無効化
        import logging
        logging.disable(logging.CRITICAL)
    
    try:
        console = Console()
        
        # 設定読み込み
        config = load_config()
        
        # 非同期処理実行
        result, gemini_client, audio_processor = asyncio.run(process_transcription(
            input_source, 
            config,
            format_only,
            summarize_only
        ))
        
        # 結果保存（適切なファイル名を使用）
        output_filename = audio_processor.get_safe_filename()
        save_results(result, output_dir, output_filename)
        
        # コスト情報取得
        cost_info = gemini_client.get_cost_summary()
        
        # サマリー表示
        console.print("\n[bold green]✅ 全体処理完了![/bold green]")
        console.print(f"📁 出力ディレクトリ: {output_dir}")
        console.print(f"⏱️  総処理時間: {result.processing_time:.1f}秒")
        console.print(f"🎵 音声長: {result.audio_duration:.1f}秒")
        if result.segments_count > 1:
            console.print(f"📊 処理セグメント数: {result.segments_count}")
        console.print(f"📈 処理効率: {result.audio_duration/result.processing_time:.1f}x")
        
        # API使用量・コスト表示
        console.print("\n[bold cyan]💰 API使用量・料金[/bold cyan]")
        console.print(f"🔤 総トークン数: {cost_info['total_tokens']:,}")
        if cost_info['audio_input_tokens'] > 0:
            console.print(f"   🎵 音声入力: {cost_info['audio_input_tokens']:,}")
        if cost_info['input_tokens'] > 0:
            console.print(f"   📝 テキスト入力: {cost_info['input_tokens']:,}")
        console.print(f"   📤 出力: {cost_info['output_tokens']:,}")
        console.print(f"💵 料金: ${cost_info['cost_usd']:.4f} (≈{cost_info['cost_jpy']:.1f}円)")
        console.print(f"🤖 モデル: {cost_info['model']}")
        
    except Exception as e:
        click.echo(f"❌ エラー: {e}", err=True)
        raise click.Abort()


async def process_transcription(
    input_source: str, 
    config: dict,
    format_only: bool = False,
    summarize_only: bool = False
) -> TranscriptionResult:
    """書き起こし処理メイン"""
    start_time = time.time()
    
    try:
        # 初期化
        audio_processor = AudioProcessor()
        gemini_client = GeminiClient(config["gemini_api_key"], config["gemini_model"])
        
        # プロンプト読み込み
        transcribe_prompt = load_prompt("transcribe")
        format_prompt = load_prompt("format")
        summarize_prompt = load_prompt("summarize")
        
        console = Console()
        
        async def run_with_spinner(step_num: int, total_steps: int, description: str, coroutine, complete_description: str):
            """スピナー付きでコルーチンを実行"""
            spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            step_start = time.time()
            
            # スピナーのテキストを作成
            def create_spinner_text(char_index):
                spinner = spinner_chars[char_index % len(spinner_chars)]
                elapsed = time.time() - step_start
                return Text(f"{spinner} ステップ {step_num}/{total_steps} {description} ({elapsed:.1f}秒)", style="bold cyan")
            
            # Live表示でスピナーを回しながらコルーチンを実行
            char_index = 0
            with Live(create_spinner_text(char_index), console=console, refresh_per_second=10) as live:
                # 非同期タスクとスピナー更新を並行実行
                async def update_spinner():
                    nonlocal char_index
                    while True:
                        await asyncio.sleep(0.1)
                        char_index += 1
                        live.update(create_spinner_text(char_index))
                
                # スピナータスクを開始
                spinner_task = asyncio.create_task(update_spinner())
                
                try:
                    # メイン処理を実行
                    result = await coroutine
                    
                    # 完了時に最終表示を更新
                    elapsed = time.time() - step_start
                    live.update(Text(f"ステップ {step_num}/{total_steps} {complete_description} ({elapsed:.1f}秒)", style="bold cyan"))
                    
                    return result
                finally:
                    # スピナーを停止
                    spinner_task.cancel()
                    try:
                        await spinner_task
                    except asyncio.CancelledError:
                        pass
        
        total_steps = 5 if not format_only and not summarize_only else 3
        current_step = 0
        
        # Step 1: 入力処理・音声準備
        current_step += 1
        
        # YouTubeの場合はスピナーを使わずに直接処理
        if audio_processor._is_youtube_url(input_source):
            console.print(f"[bold cyan]ステップ {current_step}/{total_steps}[/bold cyan] 🎵 YouTube音声処理")
            audio_path, input_type = audio_processor.process_input(input_source)
            audio_duration = audio_processor.get_audio_duration(audio_path)
        else:
            async def step1_process():
                audio_path, input_type = audio_processor.process_input(input_source)
                audio_duration = audio_processor.get_audio_duration(audio_path)
                return audio_path, input_type, audio_duration
            
            audio_path, input_type, audio_duration = await run_with_spinner(
                current_step, total_steps, "🎵 音声処理中...", step1_process(), "🎵 音声処理完了"
            )
        
        # ファイル情報を表示
        from pathlib import Path
        if input_type.value == "file":
            filename = Path(input_source).name
            console.print(f"📄 ファイル: {filename}")
        # YouTubeの場合は情報が既に表示済み
        
        console.print(f"🎵 音声長: {audio_duration:.1f}秒 ({audio_duration//60:.0f}分{audio_duration%60:.0f}秒)")
        
        # Step 2: 音声分割
        current_step += 1
        
        async def step2_process():
            return audio_processor.split_audio_if_needed(audio_path)
        
        segments = await run_with_spinner(
            current_step, total_steps, "✂️  音声分割チェック中...", step2_process(), "✂️  音声分割完了"
        )
        
        # セグメント数を追加表示
        if len(segments) > 1:
            console.print(f"📊 {len(segments)}セグメントに分割されました")
        
        # Step 3: 音声書き起こし（並列処理）
        raw_texts = []
        
        if not format_only and not summarize_only:
            current_step += 1
            
            async def step3_process():
                if len(segments) == 1:
                    # 単一セグメントの場合は通常処理
                    segment_text = await gemini_client.transcribe_audio(
                        segments[0].file_path, 
                        transcribe_prompt
                    )
                    segments[0].transcription = segment_text
                    return [segment_text]
                else:
                    # 複数セグメントの場合は並列処理
                    tasks = []
                    for i, segment in enumerate(segments):
                        task = gemini_client.transcribe_audio(
                            segment.file_path, 
                            transcribe_prompt
                        )
                        tasks.append((i, task))
                    
                    # 並列実行
                    results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
                    
                    # 結果を順序通りに配置
                    texts = []
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            raise result
                        segments[i].transcription = result
                        texts.append(result)
                    return texts
            
            description = "🎙️  音声書き起こし中..." if len(segments) == 1 else f"🎙️  {len(segments)}セグメント並列処理中..."
            raw_texts = await run_with_spinner(
                current_step, total_steps, description, step3_process(), "🎙️  音声書き起こし完了"
            )
        
        # 書き起こし結果統合
        raw_text = "\n\n".join(raw_texts) if raw_texts else ""
        
        # Step 4: テキスト整形
        formatted_text = ""
        if not summarize_only and raw_text:
            current_step += 1
            
            async def step4_process():
                return await gemini_client.format_text(raw_text, format_prompt)
            
            formatted_text = await run_with_spinner(
                current_step, total_steps, "📝 テキスト整形中...", step4_process(), "📝 テキスト整形完了"
            )
        
        # Step 5: テキスト要約
        summary_text = ""
        if raw_text:
            current_step += 1
            
            async def step5_process():
                source_text = formatted_text if formatted_text else raw_text
                return await gemini_client.summarize_text(source_text, summarize_prompt)
            
            summary_text = await run_with_spinner(
                current_step, total_steps, "📋 テキスト要約中...", step5_process(), "📋 テキスト要約完了"
            )
        
        # 一時ファイル削除
        audio_processor.cleanup_temp_files()
        
        processing_time = time.time() - start_time
        
        return TranscriptionResult(
            input_source=input_source,
            input_type=input_type,
            raw_text=raw_text,
            formatted_text=formatted_text,
            summary_text=summary_text,
            processing_time=processing_time,
            audio_duration=audio_duration,
            segments_count=len(segments),
            created_at=datetime.now()
        ), gemini_client, audio_processor
        
    except Exception as e:
        # エラー時も一時ファイル削除
        try:
            audio_processor.cleanup_temp_files()
        except Exception:
            pass
        raise e


def main():
    """エントリーポイント"""
    transcribe()


if __name__ == "__main__":
    main()