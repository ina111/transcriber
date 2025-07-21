# Transcriber

音声ファイルやYouTube動画から音声を書き起こすCLIツール。Google Gemini APIを使用して高精度な音声認識・整形・要約を提供します。

## ✨ 主な機能

- 🎵 **音声ファイル対応**: MP3, WAV, M4A, AAC, FLAC, OGG
- 🎬 **YouTube対応**: URLから直接音声を抽出・書き起こし
- 📝 **3種類の出力**: 生テキスト・整形済み・要約
- ⚡ **長時間音声対応**: 30分以上の音声を自動分割・並列処理
- 🎨 **進捗表示**: 美しいプログレスバーで処理状況を可視化

## 🛠️ インストール

### 必要な環境

- Python 3.9以上
- [uv](https://docs.astral.sh/uv/) (推奨) または pip
- [ffmpeg](https://ffmpeg.org/) (音声処理用)

### ffmpegのインストール

```bash
# macOS (Homebrew)
brew install ffmpeg

# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# Windows (Chocolatey)
choco install ffmpeg

# Windows (Scoop)
scoop install ffmpeg
```

### プロジェクトのセットアップ

```bash
# リポジトリをクローン
git clone <repository-url>
cd transcriber

# 依存関係をインストール
uv sync

# または pip を使用する場合
pip install -e .
```

## ⚙️ 設定

### Gemini API キーの取得

1. [Google AI Studio](https://aistudio.google.com/) にアクセス
2. "Get API Key" → "Create API Key" をクリック
3. APIキーをコピー

### 環境変数の設定

```bash
# .envファイルを作成
cp .env.example .env

# .envファイルを編集してAPIキーを設定
GEMINI_API_KEY=your_api_key_here
```

### 設定項目 (.env)

```bash
# Gemini API設定
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# 処理制限設定
MAX_AUDIO_DURATION=1800  # 30分
RETRY_COUNT=5
RETRY_DELAY=1

# ディレクトリ設定
OUTPUT_DIR=./output
TEMP_DIR=./temp
```

## 🚀 使用方法

### 基本的な使用法

```bash
# 音声ファイルを書き起こし
uv run transcriber "audio.mp3"

# YouTube動画を書き起こし
uv run transcriber "https://youtu.be/VIDEO_ID"

# 出力ディレクトリを指定
uv run transcriber "audio.mp3" --output-dir ./results

# 詳細ログを表示
uv run transcriber "audio.mp3" --verbose
```

### オプション

```bash
uv run transcriber --help
```

| オプション | 説明 |
|------------|------|
| `--output-dir` | 出力ディレクトリを指定 (デフォルト: `./output`) |
| `--format-only` | テキスト整形のみ実行 |
| `--summarize-only` | 要約のみ実行 |
| `--verbose` | 詳細ログを表示 |

### 出力ファイル

処理完了後、指定したディレクトリに3種類のファイルが生成されます：

```
output/
├── input_name_raw.txt      # 生の書き起こしテキスト
├── input_name_formatted.txt # 整形済みテキスト
└── input_name_summary.txt   # 要約テキスト
```


### プロンプトのカスタマイズ

`prompts/` ディレクトリ内のファイルを編集することで、AIの動作をカスタマイズできます：

- `transcribe.txt`: 音声書き起こし用プロンプト
- `format.txt`: テキスト整形用プロンプト  
- `summarize.txt`: テキスト要約用プロンプト

## 🐛 トラブルシューティング

### よくある問題

#### 1. `ffmpeg not found` エラー
```bash
# ffmpegがインストールされているか確認
ffmpeg -version

# インストールされていない場合は上記のインストール手順を参照
```

#### 2. `API key not valid` エラー
- `.env` ファイルにAPIキーが正しく設定されているか確認
- APIキーに余分なスペースや引用符が含まれていないか確認

#### 3. `ファイルが見つかりません` エラー
- ファイルパスが正しいか確認
- 日本語ファイル名の場合は引用符で囲む: `"日本語ファイル.mp3"`

#### 4. YouTube動画のダウンロードに失敗
- インターネット接続を確認
- 動画が利用可能（削除されていない）か確認
- プライベート動画や地域制限がないか確認

### ログの確認

詳細なエラー情報は `--verbose` オプションで確認できます：

```bash
uv run transcriber "audio.mp3" --verbose
```
