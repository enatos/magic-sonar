# なんとかソナー (Magic Sonar) 📡

AI・エージェント基盤技術・開発ツールの GitHub リポジトリを自動観測し、Star 増加ペース（日速）とトレンドを可視化するシステムです。

- **GitHub リポジトリ**: [https://github.com/enatos/magic-sonar](https://github.com/enatos/magic-sonar)
- **公開ダッシュボード**: [https://sonar-5ji.pages.dev](https://sonar-5ji.pages.dev)
- **データ正本**: `data/sonar.jsonl`（唯一の正本 DB）

---

## 主な特徴
- **JSONL 正本管理**: 外部 DB に依存せず、1行1リポジトリのスナップショットと観測履歴（`history`）を保持。
- **日速計算（Velocity）**: 7日前の観測点との実経過日数から 1 日あたりの Star 増加数を高精度に算出。
- **軽量静的ダッシュボード**: `build_site.py` で単一 HTML を生成。検索・タグ絞り込み・ソート・SVGスパークラインを内包。
- **Cloudflare Pages 連携**: ソナー単体プロジェクトとして高速配信。

---

## ディレクトリ構成
```
├── build_site.py          # 静的UI生成スクリプト (dist/index.html を出力)
├── deploy.sh              # ビルド・セキュリティ検査・Pagesデプロイ
├── run_daily.sh           # 日次観測バッチ実行ラッパー
├── config/
│   └── tags.yaml          # 観測関心タグと検索キーワード定義
├── data/
│   └── sonar.jsonl        # 観測データ正本 (Git管理)
├── scripts/
│   ├── pre_deploy_check.py # 公開前セキュリティ検査
│   └── ...
├── src/
│   ├── cli.py             # CLI エントリポイント
│   ├── config.py          # 設定ローダー
│   ├── evaluator.py       # タグマッチング＆スコアリング
│   ├── github_client.py   # GitHub API クライアント
│   └── storage.py         # JSONL ストレージ操作
└── README_DEPLOY.md       # デプロイ・運用手順書
```

---

## 使い方

### 1. セットアップ
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env に GitHub Personal Access Token を設定
```

### 2. 観測パイプライン実行
```bash
# 日次観測（探索 + 日速更新）
python -m src.cli run

# 観測プール状況確認
python -m src.cli status
```

### 3. 静的サイト生成 & デプロイ
```bash
# サイト生成
python build_site.py

# デプロイ（ビルド＋検査＋Cloudflare Pages反映）
./deploy.sh
```
