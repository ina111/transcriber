# Vercel デプロイメントガイド

## 概要

この書き起こしWebアプリケーションをVercelにデプロイするための手順です。

## 前提条件

1. Vercelアカウント（無料プランでも可能）
2. GitHubアカウント
3. Gemini API キー

## デプロイ手順

### 1. GitHubにプッシュ

```bash
git add .
git commit -m "Add web GUI for transcription service"
git push origin main
```

### 2. Vercelにデプロイ

1. [Vercel Dashboard](https://vercel.com/dashboard)にアクセス
2. "New Project"をクリック
3. GitHubリポジトリをインポート
4. プロジェクト設定を確認してデプロイ

### 3. 環境変数設定

Vercelダッシュボードで以下の環境変数を設定：

```
GEMINI_API_KEY=your_gemini_api_key_here
TEMP_DIR=/tmp
OUTPUT_DIR=/tmp
VERCEL_ENV=production
```

## 制限事項

### サーバーレス環境の制限

- **ファイルサイズ**: 最大50MB
- **メモリ**: 最大3GB
- **一時ファイル**: `/tmp`ディレクトリのみ利用可能

### 音声処理の制限

- **ffmpeg**: サーバーレス環境では利用不可
- **長時間音声**: 自動分割で対応
- **YouTube**: yt-dlpライブラリで処理

## トラブルシューティング

### よくある問題

1. **API Key エラー**
   - ブラウザでアクセス時にポップアップが表示されます
   - Gemini API キーを入力して検証してください

2. **ファイルサイズ制限**
   - 50MBを超えるファイルはエラーになります
   - 事前に音声ファイルを圧縮してください

3. **タイムアウトエラー**
   - 長い音声の場合、処理に時間がかかります
   - Vercel Proプランでタイムアウトを延長可能

### デバッグ

Vercelでのログ確認：
```bash
vercel logs --follow
```

## API エンドポイント

デプロイ後の利用可能なエンドポイント：

- `GET /`: メインWebページ
- `POST /api/transcribe/file`: 音声ファイル書き起こし
- `POST /api/transcribe/youtube`: YouTube URL書き起こし
- `POST /api/validate-api-key`: API キー検証
- `GET /api/check-api-key`: API キー確認
- `GET /api/health`: ヘルスチェック

## セキュリティ

- API キーはlocalStorageに保存されます（ブラウザのみ）
- サーバー側では環境変数または一時的に使用
- 一時ファイルは処理後に自動削除

## パフォーマンス最適化

1. **音声ファイル**:
   - MP3形式を推奨
   - ビットレート128kbps以下

2. **YouTube動画**:
   - 短い動画（30分以下）を推奨
   - プライベート動画は利用不可

## サポート

問題が発生した場合は、以下を確認してください：

1. Vercelのログ
2. ブラウザの開発者ツール（Console）
3. API キーの有効性
4. ファイル形式とサイズ

## 料金について

- **Vercel**: Hobbyプランは無料
- **Gemini API**: 使用量に応じて課金
- **帯域幅**: Vercelの制限内で利用