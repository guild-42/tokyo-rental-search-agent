# Phase 3 設計書: 10分周期 + モバイルUI + メール通知

---

## 1. スクレイピング周期を 10 分に変更

### 変更内容
コード変更不要。環境変数のみ。

```
FETCH_INTERVAL_MINUTES=10
```

### 実現可能性
- 現在の 1 fetch cycle = **約 8-10 分** (7サイト × 4区 並列)
- 10 分間隔 → cycle 完了と次の開始がほぼ連続
- `asyncio.Lock` が重複 fetch を防止 (前回が終わってなければ skip)
- HOMES の 202 throttle で cycle が 12-15 分に延びるケースあり → skip 発生するが安全

### 変更箇所

| ファイル | 変更 |
|---------|------|
| `Dockerfile` | `ENV FETCH_INTERVAL_MINUTES=10` |
| `docker-compose.yml` | `FETCH_INTERVAL_MINUTES=10` |
| `docker-compose.yaml` | `FETCH_INTERVAL_MINUTES=10` |
| `env.example` | `FETCH_INTERVAL_MINUTES=10` |
| Coolify 環境変数 | `FETCH_INTERVAL_MINUTES=10` |

---

## 2. モバイル UI 最適化

### 現状の課題
- フィルタパネル: 200px 上限で溢れ、操作しにくい
- 地図: 250px 固定で小さすぎる
- カード: PC レイアウトのまま横並び画像が狭い
- ソース切替 / ブックマークの操作がタッチ端末で困難

### ワイヤーフレーム: モバイル (≤ 480px)

```
┌──────────────────────────┐
│  ■ いい物件は7日まで  90件 │  ← ヘッダー (固定)
├──────────────────────────┤
│                          │
│                          │
│        🗺 地図            │  ← 画面の 55% (flex-grow)
│     (marker cluster)     │
│                          │
│                          │
├──────────────────────────┤
│ ▾ フィルタ         リセット │  ← タップで折りたたみ
├──────────────────────────┤  ← 展開時のみ表示
│ 予算 [____]〜[____] 万円  │
│ 間取り ○1R ○1K ○1DK ...  │
│ 駅徒歩 [____]分          │
│ 面積 [____]㎡〜          │
│ 築年数 [____]年以内      │
│ ☑ 地図内のみ ☑ 未読のみ  │
├──────────────────────────┤
│ 85件表示   [鮮度順 ▾] [▾] │  ← リストヘッダー + fold
├──────────────────────────┤
│ ┌────────────────────┐   │
│ │ N  ○○マンション ☆   │   │  ← カード (縦レイアウト)
│ │ 5.8万円 +3000       │   │
│ │ 1K / 22㎡ / 築10年  │   │
│ │ 新宿駅 徒歩8分      │   │
│ │ [suumo]             │   │
│ └────────────────────┘   │
│ ┌────────────────────┐   │
│ │ 2  △△アパート ☆     │   │
│ │ 7.2万円 +5000       │   │
│ │ ...                 │   │
│ └────────────────────┘   │
└──────────────────────────┘
```

### ワイヤーフレーム: タブレット (481px 〜 768px)

```
┌───────────────────────────────────────┐
│  ■ いい物件は7日まで          90件    │
├───────────────────────────────────────┤
│                                       │
│             🗺 地図 (50%)              │
│                                       │
├───────────┬───────────────────────────┤
│ フィルタ   │ 85件   [鮮度順▾]  [▾]    │
│ 予算 ...   │ ┌─────────────────────┐  │
│ 間取り ... │ │ N  ○○マンション     │  │
│ 徒歩 ...   │ │ 5.8万 1K/22㎡      │  │
│ ...        │ │ 新宿駅 徒歩8分      │  │
│            │ └─────────────────────┘  │
│ [リセット] │ ┌─────────────────────┐  │
│            │ │ ...                 │  │
└───────────┴───────────────────────────┘
```

### CSS 変更概要

```css
/* ≤ 480px: Full stack, map dominant */
@media (max-width: 480px) {
  main { flex-direction: column; height: auto; min-height: 100vh; }
  header h1 { font-size: 14px; }
  #filter-panel {
    width: 100%; min-width: unset;
    max-height: none; border: none;
    padding: 8px 12px;
  }
  /* フィルタ折りたたみ (JS toggle) */
  #filter-panel.collapsed { display: none; }
  #map-container { height: 55vh; min-height: 200px; }
  /* カード: 画像を上に or 非表示 */
  .property-card { flex-direction: column; gap: 6px; }
  .card-image { width: 100%; height: 140px; }
  .card-rent { font-size: 16px; }
  .card-title .name { font-size: 13px; }
  /* ボタンのタッチ対応 */
  .checkbox-grid label { padding: 6px 8px; font-size: 13px; }
  #btn-reset { padding: 12px; font-size: 14px; }
}

/* 481 ~ 768px: Tablet - map top, filter+list side-by-side */
@media (min-width: 481px) and (max-width: 768px) {
  main { flex-direction: column; }
  #map-container { height: 45vh; }
  .lower-section { display: flex; flex: 1; }
  #filter-panel { width: 220px; max-height: none; }
}
```

### フィルタパネル折りたたみ (モバイル)
- ヘッダーに「▾ フィルタ」ボタン追加
- モバイルでは **デフォルト折りたたみ** (地図を最大化)
- タップで展開
- localStorage で状態永続化

---

## 3. 条件マッチ新着物件のメール通知

### 概要
各 fetch cycle 後、**条件に合う新着物件** があればメールで通知。
- 宛先: `.env` の `NOTIFY_EMAIL_TO` に指定
- 送信: Google Service Account 経由 Gmail API
- 条件: `.env` の `NOTIFY_CONDITIONS` に指定 (家賃上限, 間取り, 駅徒歩 etc.)

### `.env` フォーマット (追加分)

```env
# ---- メール通知設定 ----

# 通知先メールアドレス
NOTIFY_EMAIL_TO=your-email@example.com

# 通知元 (Service Account が impersonate する Workspace ユーザー)
NOTIFY_EMAIL_FROM=your-workspace-user@your-domain.com

# Google Service Account 認証 JSON ファイルパス
GOOGLE_SERVICE_ACCOUNT_JSON=/app/secrets/service-account.json

# 通知条件 (JSON 形式)
# 各フィールドは AND 条件。省略されたフィールドは制限なし。
# 新着物件 (first_seen が直近の fetch cycle 内) のうち、
# この条件を全て満たすもののみ通知する。
NOTIFY_CONDITIONS={"rent_max": 80000, "walk_max": 10, "size_min": 20, "layouts": ["1K", "1DK", "1LDK"], "age_max": 20}

# 通知の有効/無効 (0 = off, 1 = on)
NOTIFY_ENABLED=1
```

### アーキテクチャ

```
fetch_all()
    ↓ (upsert 完了)
notify_if_needed(conn, prev_fetch_at)
    ↓
    1. DB から first_seen > prev_fetch_at の新着を取得
    2. NOTIFY_CONDITIONS で絞り込み
    3. 0 件なら終了
    4. HTML メール本文を生成 (物件カード一覧)
    5. Gmail API で送信
```

### 新規ファイル

**`src/notifier.py`**
```python
class PropertyNotifier:
    def __init__(self, conditions: dict, email_to: str, email_from: str, sa_json_path: str):
        ...

    def filter_new_properties(self, conn, since: str) -> list[Property]:
        """first_seen > since かつ条件マッチする物件を返す"""
        ...

    def build_email_html(self, properties: list[Property]) -> str:
        """物件カード一覧の HTML メールを生成"""
        ...

    async def send_email(self, subject: str, html_body: str):
        """Gmail API (Service Account delegated) で送信"""
        ...

    async def notify_if_needed(self, conn, prev_fetch_at: str):
        """メインエントリポイント: 条件マッチ新着があればメール送信"""
        ...
```

### Google Service Account 設定手順
1. GCP コンソールで Service Account 作成
2. Gmail API 有効化
3. Workspace 管理コンソールで Domain-wide Delegation 設定
4. Service Account JSON を `/app/secrets/service-account.json` に配置
5. `NOTIFY_EMAIL_FROM` に impersonate 対象ユーザーを指定

### orchestrator 統合
```python
# fetch_all() の末尾、upsert 後:
if os.environ.get("NOTIFY_ENABLED") == "1":
    from .notifier import PropertyNotifier
    notifier = PropertyNotifier(...)
    await notifier.notify_if_needed(conn, prev_fetch_at)
```

### メール本文イメージ

```
Subject: 🏠 新着 3件 — いい物件は7日まで

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

■ ○○マンション【NEW】
  5.8万円 (+3,000) | 1K | 22㎡ | 築10年
  新宿区西新宿2丁目 / 新宿駅 徒歩8分
  → https://suumo.jp/...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

■ △△アパート【NEW】
  7.2万円 (+5,000) | 1DK | 28㎡ | 築5年
  中野区中野4丁目 / 中野駅 徒歩6分
  → https://homes.co.jp/...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

条件: 家賃≤8万 / 駅徒歩≤10分 / 面積≥20㎡ / 築≤20年
全物件を見る: https://7days.actraise.org
```

---

## 4. 実装順序

| # | タスク | 見積 | 依存 |
|---|--------|-----|------|
| 1 | スクレイピング周期を 10 分に変更 (env のみ) | 5 分 | なし |
| 2 | モバイル CSS + フィルタ折りたたみ | 2 時間 | なし |
| 3 | `src/notifier.py` + Gmail API 連携 | 3 時間 | Google SA JSON |
| 4 | orchestrator に notifier 統合 | 30 分 | #3 |
| 5 | env.example 更新 + ドキュメント | 15 分 | #3 |
| 6 | ローカル検証 + commit + push | 30 分 | #1-5 |
| 7 | Coolify redeploy + 動作確認 | 15 分 | #6 |

**合計: ~6.5 時間**

---

## 5. 変更ファイル一覧

| ファイル | 変更 |
|---------|------|
| `Dockerfile` | `FETCH_INTERVAL_MINUTES=10` |
| `docker-compose.yml` / `.yaml` | 同上 |
| `env.example` | 周期 + メール通知設定追加 |
| `requirements.txt` | `google-auth`, `google-api-python-client`, `google-auth-oauthlib` 追加 |
| `web/style.css` | モバイル CSS (@media 480px, 768px) |
| `web/index.html` | フィルタ折りたたみボタン, `<meta viewport>` 確認 |
| `web/app.js` | フィルタ toggle (モバイル), bounds filter 調整 |
| `src/notifier.py` (新規) | PropertyNotifier + Gmail API 送信 |
| `src/orchestrator.py` | notify_if_needed 呼び出し追加 |
| `src/server.py` | prev_fetch_at の保持 |
