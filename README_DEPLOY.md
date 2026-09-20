# なんとかソナー UI & Cloudflare Pages デプロイ運用手順書

## 1. サイト概要
- **公開URL (本番)**: `https://sonar-5ji.pages.dev`
- **Cloudflare Pages プロジェクト名**: `sonar-5ji` (エイリアス: `sonar`)
- **データ正本**: `data/sonar.jsonl`
- **ビルド成果物**: `dist/index.html`

---

## 2. 自動更新の仕組み（GitHub Actions - 3日に1回 06:00 JST）

GitHub Actions ワークフロー（`.github/workflows/sonar_update.yml`）により、3日おき朝06:00（JST）に完全自動で以下の処理が実行されます：
1. **GitHub観測実行**: `python -m src.cli run`（新規候補収集 & Star日速計算）
2. **静的サイト生成**: `python build_site.py`（HTML / JSON / Markdown / llms.txt）
3. **公開前検査**: `python scripts/pre_deploy_check.py`（内部URL・個人情報・トークン等の漏洩防止検査）
4. **Cloudflare Pages デプロイ**: `npx wrangler pages deploy dist --project-name sonar`
5. **Gitコミット & プッシュ**: 更新された `data/sonar.jsonl` と `dist/` を自動コミット

### 必要なGitHub Secrets
- `GITHUB_TOKEN`: 自動付与（または個人PAT `PAT_TOKEN`）
- `CLOUDFLARE_API_TOKEN`: Cloudflare Pagesへのデプロイ権限を持つトークン
- `CLOUDFLARE_ACCOUNT_ID`: `aba4ac3abdccd69448f4d2ef251cae10`（未設定時はワークフロー既定値を使用）

---

## 3. 手動更新・デプロイ手順

### (1) ローカルでのワンストップデプロイ
```bash
./deploy.sh
```

### (2) 手動での段階実行
1. **観測 & データ更新**:
   ```bash
   ./.venv/bin/python -m src.cli run
   ```
2. **静的HTML再生成**:
   ```bash
   ./.venv/bin/python build_site.py
   ```
3. **公開前チェック（セキュリティ検査）**:
   ```bash
   ./.venv/bin/python scripts/pre_deploy_check.py
   ```
4. **Cloudflare Pages デプロイ**:
   ```bash
   npx wrangler pages deploy dist --project-name sonar --commit-dirty=true
   ```

---

## 4. 戻し方（ロールバック）
デプロイを過去のバージョンに戻す手順：

1. **デプロイ一覧の確認**:
   ```bash
   npx wrangler pages deployment list --project-name sonar
   ```
2. **Cloudflare Dashboard からのロールバック**:
   Cloudflare ダッシュボードの [Workers & Pages] → [sonar] (または [sonar-5ji]) → [Deployments] より、過去の正常なデプロイの三点リーダーメニューから「Rollback to this deployment」を実行。
