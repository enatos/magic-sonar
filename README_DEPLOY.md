# なんとかソナー UI & Cloudflare Pages デプロイ運用手順書

## 1. サイト概要
- **公開URL (本番)**: `https://sonar-5ji.pages.dev`
- **初回デプロイURL**: `https://0b9e6440.sonar-5ji.pages.dev`
- **Cloudflare Pages プロジェクト名**: `sonar-5ji` (エイリアス: `sonar`)
- **データ正本**: `data/sonar.jsonl`
- **ビルド成果物**: `dist/index.html`

---

## 2. 更新の仕組み（手動 & 日次）

### (1) ワンストップデプロイ（推奨）
データ更新後に以下のスクリプトを実行すると、「静的ページ生成 → 公開前セキュリティ検査 → Cloudflare Pages デプロイ」が自動で完結します。

```bash
./deploy.sh
```

### (2) 手動での段階実行
1. **静的HTML再生成**:
   ```bash
   python build_site.py
   ```
2. **公開前チェック（セキュリティ検査）**:
   ```bash
   python scripts/pre_deploy_check.py
   ```
3. **Cloudflare Pages デプロイ**:
   ```bash
   npx wrangler pages deploy dist --project-name sonar-5ji
   ```

### (3) 日次バッチ（launchd / 定時実行）との連動
`run_daily.sh` の末尾に `build_site.py` の実行が組み込まれているため、観測更新が行われると自動的に `dist/index.html` も最新化されます。

---

## 3. 戻し方（ロールバック）
デプロイを過去のバージョンに戻す手順：

1. **デプロイ一覧の確認**:
   ```bash
   npx wrangler pages deployment list --project-name sonar-5ji
   ```
2. **Cloudflare Dashboard からのロールバック**:
   Cloudflare ダッシュボードの [Workers & Pages] → [sonar-5ji] → [Deployments] より、過去の正常なデプロイの三点リーダーメニューから「Rollback to this deployment」を実行。
