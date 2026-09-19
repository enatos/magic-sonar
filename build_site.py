#!/usr/bin/env python3
"""
build_site.py - Generate static UI for なんとかソナー from data/sonar.jsonl
"""

import json
from pathlib import Path
from datetime import datetime, timezone
import html

ROOT_DIR = Path(__file__).resolve().parent
DATA_PATH = ROOT_DIR / "data" / "sonar.jsonl"
DIST_DIR = ROOT_DIR / "dist"
OUTPUT_HTML = DIST_DIR / "index.html"


def generate_sparkline_svg(history: list, width: int = 80, height: int = 24) -> str:
    """Generate a compact SVG sparkline from star history."""
    if not history or len(history) < 2:
        return ""

    stars = [h.get("stars", 0) for h in history if isinstance(h, dict) and "stars" in h]
    if len(stars) < 2:
        return ""

    min_s = min(stars)
    max_s = max(stars)
    span_s = max_s - min_s if max_s > min_s else 1

    padding = 2
    usable_w = width - (padding * 2)
    usable_h = height - (padding * 2)

    points = []
    n = len(stars)
    for i, s in enumerate(stars):
        x = padding + (i / (n - 1)) * usable_w
        y = height - padding - ((s - min_s) / span_s) * usable_h
        points.append(f"{x:.1f},{y:.1f}")

    polyline = " ".join(points)
    svg = (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" class="sparkline" '
        f'aria-label="Star trend sparkline">'
        f'<polyline fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" points="{polyline}" />'
        f'</svg>'
    )
    return svg


def load_sonar_data(jsonl_path: Path):
    items = []
    if not jsonl_path.exists():
        return items

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                items.append(data)
            except json.JSONDecodeError:
                continue

    items.sort(
        key=lambda x: (
            x.get("velocity") if x.get("velocity") is not None else -999999.0,
            x.get("current_stars") or 0,
        ),
        reverse=True,
    )
    return items


CLIENT_JS = """
(function() {
  const rawData = JSON.parse(document.getElementById('sonarData').textContent);
  let activeTag = 'all';
  let searchQuery = '';
  let sortKey = 'velocity_desc';

  const tableBody = document.getElementById('repoTableBody');
  const emptyState = document.getElementById('emptyState');
  const searchInput = document.getElementById('searchInput');
  const sortSelect = document.getElementById('sortSelect');
  const tagButtons = document.querySelectorAll('.tag-btn');
  const themeToggle = document.getElementById('themeToggle');

  themeToggle.addEventListener('click', () => {
    const current = document.body.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    document.body.setAttribute('data-theme', next);
    localStorage.setItem('sonar_theme', next);
  });

  const savedTheme = localStorage.getItem('sonar_theme');
  if (savedTheme) {
    document.body.setAttribute('data-theme', savedTheme);
  }

  tagButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      tagButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeTag = btn.getAttribute('data-tag');
      render();
    });
  });

  searchInput.addEventListener('input', (e) => {
    searchQuery = e.target.value.trim().toLowerCase();
    render();
  });

  sortSelect.addEventListener('change', (e) => {
    sortKey = e.target.value;
    render();
  });

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function render() {
    let filtered = rawData.filter(item => {
      if (activeTag !== 'all') {
        if (!item.tags.includes(activeTag)) return false;
      }
      if (searchQuery) {
        const inRepo = item.repo.toLowerCase().includes(searchQuery);
        const inDesc = item.description.toLowerCase().includes(searchQuery);
        const inTags = item.tags.some(t => t.toLowerCase().includes(searchQuery));
        if (!inRepo && !inDesc && !inTags) return false;
      }
      return true;
    });

    filtered.sort((a, b) => {
      if (sortKey === 'velocity_desc') {
        const va = a.velocity != null ? a.velocity : -999999;
        const vb = b.velocity != null ? b.velocity : -999999;
        return vb - va || b.current_stars - a.current_stars;
      }
      if (sortKey === 'stars_desc') {
        return b.current_stars - a.current_stars;
      }
      if (sortKey === 'observed_desc') {
        return b.observed_days - a.observed_days;
      }
      if (sortKey === 'name_asc') {
        return a.repo.localeCompare(b.repo);
      }
      return 0;
    });

    if (filtered.length === 0) {
      tableBody.innerHTML = '';
      emptyState.style.display = 'block';
      return;
    }

    emptyState.style.display = 'none';
    const rows = filtered.map((item, idx) => {
      const v = item.velocity != null ? `+${item.velocity.toFixed(1)}/日` : '計測待ち';
      const vClass = item.velocity_type && item.velocity_type.includes('確定') ? 'v-type-confirmed' : 'v-type-provisional';
      const tagPills = item.tags.map(t => `<span class="item-tag">${escapeHtml(t)}</span>`).join(' ');
      const langPill = item.language ? `<span class="lang-badge">● ${escapeHtml(item.language)}</span>` : '';

      return `
        <tr>
          <td style="color:var(--text-muted);font-size:12px;">${idx + 1}</td>
          <td class="repo-cell">
            <div class="repo-name"><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.repo)}</a></div>
            <div class="repo-desc">${langPill}${escapeHtml(item.description)}</div>
          </td>
          <td class="velocity-cell">
            <span class="velocity-pill">${v}</span>
            <span class="v-type-badge ${vClass}">${escapeHtml(item.velocity_type)}</span>
          </td>
          <td class="stars-num">⭐ ${item.current_stars.toLocaleString()}</td>
          <td>${item.sparkline}</td>
          <td style="color:var(--text-muted);font-variant-numeric:tabular-nums;">${item.observed_days.toFixed(1)}日</td>
          <td><div class="item-tags">${tagPills}</div></td>
        </tr>
      `;
    }).join('');

    tableBody.innerHTML = rows;
  }

  render();
})();
"""


def generate_table_rows_html(client_data: list) -> str:
    """Generate initial HTML table rows for SSR/static rendering."""
    rows = []
    for idx, item in enumerate(client_data):
        v_val = item.get("velocity")
        v_str = f"+{v_val:.1f}/日" if v_val is not None else "計測待ち"
        v_type = item.get("velocity_type", "計測待ち")
        v_class = "v-type-confirmed" if "確定" in v_type else "v-type-provisional"

        tag_pills = " ".join([f'<span class="item-tag">{html.escape(t)}</span>' for t in item.get("tags", [])])
        lang = item.get("language")
        lang_pill = f'<span class="lang-badge">● {html.escape(lang)}</span>' if lang else ""

        repo_name = html.escape(item.get("repo", ""))
        repo_url = html.escape(item.get("url", ""))
        desc = html.escape(item.get("description", ""))
        stars = item.get("current_stars", 0)
        spark = item.get("sparkline", "")
        obs_days = item.get("observed_days", 0)

        row = f"""        <tr>
          <td style="color:var(--text-muted);font-size:12px;">{idx + 1}</td>
          <td class="repo-cell">
            <div class="repo-name"><a href="{repo_url}" target="_blank" rel="noopener noreferrer">{repo_name}</a></div>
            <div class="repo-desc">{lang_pill}{desc}</div>
          </td>
          <td class="velocity-cell">
            <span class="velocity-pill">{v_str}</span>
            <span class="v-type-badge {v_class}">{html.escape(v_type)}</span>
          </td>
          <td class="stars-num">⭐ {stars:,}</td>
          <td>{spark}</td>
          <td style="color:var(--text-muted);font-variant-numeric:tabular-nums;">{obs_days:.1f}日</td>
          <td><div class="item-tags">{tag_pills}</div></td>
        </tr>"""
        rows.append(row)
    return "\n".join(rows)


def generate_markdown(items: list, generated_at_iso: str) -> str:
    """Generate clean Markdown documentation for AI/LLMs."""
    lines = [
        "# なんとかソナー 📡 GitHub トレンド・日速観測データ",
        "",
        f"> 最終更新: {generated_at_iso[:19]}Z | 観測数: {len(items)} | データ正本: sonar.jsonl",
        "",
        "## ⚡️ 急上昇ランキング (TOP 5)",
        "",
        "| 順位 | リポジトリ | 日速 | Star数 | 観測日数 | 言語 | タグ | 説明 |",
        "|:---:|---|:---:|:---:|:---:|:---:|---|---|",
    ]

    top5 = [it for it in items if it.get("velocity") is not None][:5]
    for i, it in enumerate(top5, 1):
        repo = it.get("repo", "")
        url = it.get("url", f"https://github.com/{repo}")
        v = f"+{it.get('velocity', 0):.1f}/日 ({it.get('velocity_type', '')})"
        stars = f"{it.get('current_stars', 0):,}"
        days = f"{it.get('observed_days', 0):.1f}日"
        lang = it.get("language") or "-"
        tags = ", ".join(it.get("tags", [])) or "-"
        desc = (it.get("description") or "-").replace("\n", " ").replace("|", "\\|")
        lines.append(f"| #{i} | [{repo}]({url}) | {v} | ⭐ {stars} | {days} | {lang} | {tags} | {desc} |")

    lines.extend([
        "",
        "## 📋 全観測リポジトリ一覧",
        "",
        "| # | リポジトリ | 日速 | Star数 | 観測日数 | 言語 | タグ | 説明 |",
        "|:---:|---|:---:|:---:|:---:|:---:|---|---|",
    ])

    for idx, it in enumerate(items, 1):
        repo = it.get("repo", "")
        url = it.get("url", f"https://github.com/{repo}")
        v_val = it.get("velocity")
        v = f"+{v_val:.1f}/日 ({it.get('velocity_type', '')})" if v_val is not None else "計測待ち"
        stars = f"{it.get('current_stars', 0):,}"
        days = f"{it.get('observed_days', 0):.1f}日"
        lang = it.get("language") or "-"
        tags = ", ".join(it.get("tags", [])) or "-"
        desc = (it.get("description") or "-").replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {idx} | [{repo}]({url}) | {v} | ⭐ {stars} | {days} | {lang} | {tags} | {desc} |")

    lines.append("")
    return "\n".join(lines)


def generate_llms_txt() -> str:
    """Generate standard llms.txt guide for AI agents."""
    return """# なんとかソナー 📡

> AI・開発ツール・基盤技術の GitHub 新着観測＆Star日速分析ダッシュボード

## 機械可読データ
- [観測データ (Markdown)](https://sonar-5ji.pages.dev/sonar.md): 全観測リポジトリの一覧表（LLM/AIが最も読みやすいフォーマット）
- [観測データ (JSON)](https://sonar-5ji.pages.dev/sonar.json): 全観測リポジトリの完全な構造化データ（API連携用）
- [Webダッシュボード](https://sonar-5ji.pages.dev/): 人間向けインタラクティブUI（静的テーブル＆ランキング）

## 概要
GitHub 上の注目リポジトリを継続観測し、Starの増加ペース（日速 = stars/day）を追跡・可視化しています。
日速は7日間の推移から算出される「確定(7日)」と、観測開始直後の「暫定」に分類されます。
"""


def render_html(items: list, generated_at_iso: str) -> tuple:
    total_count = len(items)
    tags_set = set()
    total_stars = 0
    max_velocity_item = None

    for it in items:
        for t in it.get("tags", []):
            tags_set.add(t)
        total_stars += it.get("current_stars", 0)
        v = it.get("velocity")
        if v is not None:
            if max_velocity_item is None or v > (max_velocity_item.get("velocity") or 0):
                max_velocity_item = it

    sorted_tags = sorted(list(tags_set))
    top_velocity_items = [it for it in items if it.get("velocity") is not None][:5]

    client_data = []
    for rank, it in enumerate(items, 1):
        client_data.append(
            {
                "rank": rank,
                "repo": it.get("repo", ""),
                "url": it.get("url", f"https://github.com/{it.get('repo', '')}"),
                "description": it.get("description", "") or "",
                "language": it.get("language") or "",
                "tags": it.get("tags", []),
                "judge_type": it.get("judge_type", ""),
                "current_stars": it.get("current_stars", 0),
                "velocity": it.get("velocity"),
                "velocity_type": it.get("velocity_type", "計測待ち"),
                "observed_days": it.get("observed_days", 0),
                "sparkline": generate_sparkline_svg(it.get("history", [])),
            }
        )

    client_data_json = json.dumps(client_data, ensure_ascii=False)
    initial_table_rows = generate_table_rows_html(client_data)

    top_cards_html = []
    for i, it in enumerate(top_velocity_items, 1):
        v = it.get("velocity", 0)
        v_type = it.get("velocity_type", "確定(7日)")
        v_class = "v-type-confirmed" if "確定" in v_type else "v-type-provisional"
        top_cls = f"top{i}" if i <= 3 else ""
        repo_name = html.escape(it.get("repo", ""))
        repo_url = html.escape(it.get("url", f"https://github.com/{it.get('repo', '')}"))
        repo_desc = html.escape(it.get("description", "") or "説明なし")
        stars = it.get("current_stars", 0)
        spark = generate_sparkline_svg(it.get("history", []), width=70, height=20)
        tag_badges = "".join([f'<span class="item-tag">{html.escape(t)}</span>' for t in it.get("tags", [])[:2]])

        top_cards_html.append(f"""
        <div class="rank-card {top_cls}">
          <div>
            <div class="rank-header">
              <span class="rank-num">#{i}</span>
              <span class="velocity-pill">+{v:.1f}/日 <span class="v-type-badge {v_class}">{v_type}</span></span>
            </div>
            <div class="rank-repo"><a href="{repo_url}" target="_blank" rel="noopener noreferrer">{repo_name}</a></div>
            <div class="rank-desc">{repo_desc}</div>
          </div>
          <div class="rank-footer">
            <div>
              <span class="stars-num">⭐ {stars:,}</span>
              <div style="margin-top:4px;">{tag_badges}</div>
            </div>
            <div>{spark}</div>
          </div>
        </div>""")

    cards_joined = "\n".join(top_cards_html)
    tags_btn_html = "".join([f'<button class="tag-btn" data-tag="{html.escape(t)}">{html.escape(t)}</button>' for t in sorted_tags])

    max_v_repo = max_velocity_item.get('repo', '-') if max_velocity_item else '-'
    max_v_val = max_velocity_item.get('velocity', 0) if max_velocity_item else 0.0
    latest_obs = items[0].get('latest_observed_at', '')[:10] if items else '-'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>なんとかソナー 📡 | GitHub トレンド・日速観測</title>
  <meta name="description" content="AI・開発ツールの新着リポジトリとStar日速ペースを観測するなんとかソナーの公開ダッシュボード">
  <link rel="alternate" type="application/json" href="/sonar.json" title="なんとかソナー JSON データ">
  <link rel="alternate" type="text/markdown" href="/sonar.md" title="なんとかソナー Markdown データ">
  <style>
    :root {{
      --bg: #0d1117;
      --card-bg: #161b22;
      --card-border: #30363d;
      --text: #c9d1d9;
      --text-muted: #8b949e;
      --text-bright: #f0f6fc;
      --accent: #58a6ff;
      --accent-glow: rgba(88, 166, 255, 0.15);
      --velocity-pos: #3fb950;
      --velocity-bg: rgba(63, 185, 80, 0.15);
      --tag-bg: #21262d;
      --tag-text: #79c0ff;
      --tag-border: #388bfd33;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    }}

    @media (prefers-color-scheme: light) {{
      :root[data-theme="system"] {{
        --bg: #f6f8fa;
        --card-bg: #ffffff;
        --card-border: #d0d7de;
        --text: #24292f;
        --text-muted: #57606a;
        --text-bright: #0969da;
        --accent: #0969da;
        --accent-glow: rgba(9, 105, 218, 0.1);
        --velocity-pos: #1a7f37;
        --velocity-bg: rgba(26, 127, 55, 0.12);
        --tag-bg: #ddf4ff;
        --tag-text: #0969da;
        --tag-border: #54aeff66;
      }}
    }}

    :root[data-theme="light"] {{
      --bg: #f6f8fa;
      --card-bg: #ffffff;
      --card-border: #d0d7de;
      --text: #24292f;
      --text-muted: #57606a;
      --text-bright: #0969da;
      --accent: #0969da;
      --accent-glow: rgba(9, 105, 218, 0.1);
      --velocity-pos: #1a7f37;
      --velocity-bg: rgba(26, 127, 55, 0.12);
      --tag-bg: #ddf4ff;
      --tag-text: #0969da;
      --tag-border: #54aeff66;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: var(--font);
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px 16px 64px;
      transition: background-color 0.2s ease, color 0.2s ease;
    }}

    .container {{
      max-width: 1200px;
      margin: 0 auto;
    }}

    header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 16px;
      margin-bottom: 28px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--card-border);
    }}

    .title-group h1 {{
      font-size: 26px;
      font-weight: 700;
      color: var(--text-bright);
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .title-group p {{
      color: var(--text-muted);
      font-size: 14px;
      margin-top: 4px;
    }}

    .header-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}

    .data-link-btn {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 6px 11px;
      border-radius: 6px;
      font-size: 13px;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      transition: all 0.15s ease;
    }}
    .data-link-btn:hover {{
      border-color: var(--accent);
      color: var(--accent);
    }}

    .theme-toggle {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 13px;
      cursor: pointer;
    }}

    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-bottom: 28px;
    }}

    .metric-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 16px;
    }}

    .metric-label {{
      font-size: 12px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 6px;
    }}

    .metric-value {{
      font-size: 22px;
      font-weight: 700;
      color: var(--text-bright);
    }}

    .metric-sub {{
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
    }}

    .ranking-section {{
      margin-bottom: 36px;
    }}

    .section-title {{
      font-size: 18px;
      font-weight: 600;
      color: var(--text-bright);
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .ranking-cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 14px;
    }}

    .rank-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      position: relative;
      overflow: hidden;
    }}

    .rank-card::before {{
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      width: 4px;
      height: 100%;
      background: var(--accent);
    }}

    .rank-card.top1::before {{ background: #f1e05a; }}
    .rank-card.top2::before {{ background: #e36209; }}
    .rank-card.top3::before {{ background: #a371f7; }}

    .rank-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 8px;
    }}

    .rank-num {{
      font-size: 14px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
      background: var(--tag-bg);
      color: var(--text-bright);
    }}

    .rank-repo {{
      font-size: 16px;
      font-weight: 600;
      word-break: break-all;
    }}

    .rank-repo a {{
      color: var(--accent);
      text-decoration: none;
    }}
    .rank-repo a:hover {{ text-decoration: underline; }}

    .rank-desc {{
      font-size: 13px;
      color: var(--text-muted);
      margin: 8px 0 12px;
      line-height: 1.4;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .rank-footer {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 10px;
      border-top: 1px solid var(--card-border);
    }}

    .velocity-pill {{
      font-size: 13px;
      font-weight: 600;
      color: var(--velocity-pos);
      background: var(--velocity-bg);
      padding: 2px 8px;
      border-radius: 4px;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}

    .controls-panel {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 20px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }}

    .controls-top {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }}

    .search-input {{
      flex: 1;
      min-width: 240px;
      background: var(--bg);
      border: 1px solid var(--card-border);
      color: var(--text-bright);
      padding: 8px 14px;
      border-radius: 6px;
      font-size: 14px;
      outline: none;
    }}
    .search-input:focus {{ border-color: var(--accent); }}

    .sort-select {{
      background: var(--bg);
      border: 1px solid var(--card-border);
      color: var(--text-bright);
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 14px;
      outline: none;
      cursor: pointer;
    }}

    .tags-filter {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }}

    .tag-btn {{
      background: var(--bg);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 4px 10px;
      border-radius: 12px;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .tag-btn:hover {{ border-color: var(--accent); color: var(--text); }}
    .tag-btn.active {{
      background: var(--tag-bg);
      color: var(--tag-text);
      border-color: var(--tag-border);
      font-weight: 600;
    }}

    .table-wrapper {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      overflow-x: auto;
      box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }}

    th {{
      background: var(--card-bg);
      padding: 12px 14px;
      font-weight: 600;
      color: var(--text-muted);
      border-bottom: 1px solid var(--card-border);
      white-space: nowrap;
    }}

    td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--card-border);
      vertical-align: middle;
    }}

    tr:hover td {{
      background: var(--accent-glow);
    }}

    .repo-cell {{
      max-width: 380px;
    }}

    .repo-name {{
      font-weight: 600;
      font-size: 14px;
      word-break: break-all;
    }}
    .repo-name a {{
      color: var(--accent);
      text-decoration: none;
    }}
    .repo-name a:hover {{ text-decoration: underline; }}

    .repo-desc {{
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 3px;
      line-height: 1.35;
      overflow: hidden;
      text-overflow: ellipsis;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
    }}

    .lang-badge {{
      display: inline-block;
      font-size: 11px;
      color: var(--text-muted);
      margin-right: 6px;
    }}

    .stars-num {{
      font-weight: 600;
      color: var(--text-bright);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }}

    .velocity-cell {{
      white-space: nowrap;
    }}

    .v-type-badge {{
      font-size: 10px;
      padding: 1px 5px;
      border-radius: 3px;
      margin-left: 4px;
      display: inline-block;
      border: 1px solid currentColor;
    }}
    .v-type-confirmed {{ color: var(--velocity-pos); }}
    .v-type-provisional {{ color: #d29922; }}

    .item-tags {{
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
    }}

    .item-tag {{
      background: var(--tag-bg);
      color: var(--tag-text);
      font-size: 11px;
      padding: 2px 6px;
      border-radius: 4px;
      border: 1px solid var(--tag-border);
      white-space: nowrap;
    }}

    .sparkline {{
      color: var(--accent);
      vertical-align: middle;
    }}

    footer {{
      margin-top: 48px;
      text-align: center;
      color: var(--text-muted);
      font-size: 13px;
      border-top: 1px solid var(--card-border);
      padding-top: 24px;
    }}

    footer a {{
      color: var(--accent);
      text-decoration: none;
    }}

    .empty-state {{
      padding: 48px 16px;
      text-align: center;
      color: var(--text-muted);
    }}
  </style>
</head>
<body data-theme="dark">
  <div class="container">
    <header>
      <div class="title-group">
        <h1>なんとかソナー 📡</h1>
        <p>AI・開発ツール・基盤技術の GitHub 新着観測＆Star日速分析</p>
      </div>
      <div class="header-actions">
        <a href="/sonar.md" class="data-link-btn" title="AI・エージェント向け Markdown データ">🤖 MD</a>
        <a href="/sonar.json" class="data-link-btn" title="AI・エージェント向け JSON データ">📦 JSON</a>
        <button id="themeToggle" class="theme-toggle" aria-label="テーマ切替">🌓 表示切替</button>
      </div>
    </header>

    <section class="metrics-grid">
      <div class="metric-card">
        <div class="metric-label">観測リポジトリ</div>
        <div class="metric-value">{total_count} <span style="font-size:14px;font-weight:normal;color:var(--text-muted);">/ 200上限</span></div>
        <div class="metric-sub">アクティブ観測プール</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">最高日速</div>
        <div class="metric-value" style="color:var(--velocity-pos);">
          +{max_v_val:.1f} <span style="font-size:14px;font-weight:normal;">stars/日</span>
        </div>
        <div class="metric-sub">{max_v_repo}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">観測総Star数</div>
        <div class="metric-value">{total_stars:,}</div>
        <div class="metric-sub">プール内リポジトリ合計</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">最終観測日時</div>
        <div class="metric-value" style="font-size:16px;margin-top:4px;">{latest_obs}</div>
        <div class="metric-sub">データ正本: <code>sonar.jsonl</code></div>
      </div>
    </section>

    <section class="ranking-section">
      <h2 class="section-title">⚡️ 急上昇ランキング (TOP 5)</h2>
      <div class="ranking-cards">
{cards_joined}
      </div>
    </section>

    <section>
      <div class="controls-panel">
        <div class="controls-top">
          <input type="text" id="searchInput" class="search-input" placeholder="リポジトリ名・説明・タグで検索..." autocomplete="off">
          <select id="sortSelect" class="sort-select">
            <option value="velocity_desc">日速が速い順</option>
            <option value="stars_desc">Star数が多い順</option>
            <option value="observed_desc">観測日数が長い順</option>
            <option value="name_asc">リポジトリ名順 (A-Z)</option>
          </select>
        </div>
        <div class="tags-filter">
          <button class="tag-btn active" data-tag="all">すべて ({total_count})</button>
          {tags_btn_html}
        </div>
      </div>

      <div class="table-wrapper">
        <table id="repoTable">
          <thead>
            <tr>
              <th scope="col" style="width:48px;">#</th>
              <th scope="col">リポジトリ</th>
              <th scope="col" style="width:140px;">日速</th>
              <th scope="col" style="width:100px;">Star数</th>
              <th scope="col" style="width:90px;">推移</th>
              <th scope="col" style="width:90px;">観測日数</th>
              <th scope="col">タグ</th>
            </tr>
          </thead>
          <tbody id="repoTableBody">
{initial_table_rows}
          </tbody>
        </table>
        <div id="emptyState" class="empty-state" style="display:none;">
          条件に一致するリポジトリは見つかりませんでした。
        </div>
      </div>
    </section>

    <footer>
      <p>なんとかソナー 📡 観測正本: <code>sonar.jsonl</code> | 🤖 AI用: <a href="/sonar.md">Markdown</a> · <a href="/sonar.json">JSON</a> · <a href="/llms.txt">llms.txt</a> | Generated: {generated_at_iso[:19]}Z</p>
    </footer>
  </div>

  <script id="sonarData" type="application/json">
{client_data_json}
  </script>

  <script>
{CLIENT_JS}
  </script>
</body>
</html>
""", client_data


def main():
    print(f"Loading data from {DATA_PATH}...")
    items = load_sonar_data(DATA_PATH)
    print(f"Loaded {len(items)} repositories.")

    if not items:
        print("Error: No data loaded from sonar.jsonl")
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    html_content, client_data = render_html(items, now_iso)
    markdown_content = generate_markdown(items, now_iso)
    llms_txt_content = generate_llms_txt()

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html_content, encoding="utf-8")
    (DIST_DIR / "sonar.json").write_text(json.dumps(client_data, ensure_ascii=False, indent=2), encoding="utf-8")
    (DIST_DIR / "sonar.md").write_text(markdown_content, encoding="utf-8")
    (DIST_DIR / "llms.txt").write_text(llms_txt_content, encoding="utf-8")

    print(f"Successfully generated {OUTPUT_HTML} ({len(html_content)} bytes).")
    print(f"Successfully generated {DIST_DIR / 'sonar.json'} ({len(client_data)} items).")
    print(f"Successfully generated {DIST_DIR / 'sonar.md'} ({len(markdown_content)} bytes).")
    print(f"Successfully generated {DIST_DIR / 'llms.txt'} ({len(llms_txt_content)} bytes).")


if __name__ == "__main__":
    main()
