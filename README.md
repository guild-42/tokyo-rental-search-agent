# 東京賃貸サーチエージェント

複数の賃貸サイトから物件をスクレイピングして、鮮度順に表示するWebアプリ。SUUMO, LIFULL HOME'S, CHINTAI, Yahoo不動産, door賃貸, eheya, house.com, minimini, apamanshopの9ソース対応。

## 機能

- 9サイトから並列スクレイピング → SQLiteにUPSERT（重複排除）
- 経過日数/家賃/間取り/面積/築年数/駅徒歩でフィルタ
- 地図表示（Leaflet + OpenStreetMap）
- ブックマーク / 閲覧済み区別（localStorage）
- 指定時刻スケジュール or 一定間隔での自動fetch

## ローカル実行

```bash
pip install -r requirements.txt

# データ取得
python main.py fetch --wards "新宿区,中野区,渋谷区" --pages 10

# サーバー起動
python main.py serve --port 8080 --max-age 30
```

http://localhost:8080 で閲覧。

## Docker

```bash
docker compose up -d
```

## 環境変数

| Var | Default | 説明 |
|-----|---------|------|
| `FETCH_INTERVAL_HOURS` | `3` | N時間ごとにfetch（最優先） |
| `FETCH_SCHEDULE_HOURS` | `9,12,15,18,21` | 特定時刻にfetch（`FETCH_INTERVAL_HOURS`未設定時のみ） |
| `FETCH_MAX_PAGES` | `10` | ソースごとの最大ページ数 |
| `FETCH_WARD_CODES` | `13104,13113,13114` | 区コード（新宿,渋谷,中野） |
| `MAX_AGE_DAYS` | `30` | 表示する物件の最大経過日数 |
| `DB_PATH` | `/app/data/rental.db` | SQLiteパス |

### 区コード一覧

千代田=13101, 中央=13102, 港=13103, 新宿=13104, 文京=13105, 台東=13106, 墨田=13107, 江東=13108, 品川=13109, 目黒=13110, 大田=13111, 世田谷=13112, 渋谷=13113, 中野=13114, 杉並=13115, 豊島=13116, 北=13117, 荒川=13118, 板橋=13119, 練馬=13120, 足立=13121, 葛飾=13122, 江戸川=13123

## Coolify デプロイ

1. Coolifyで新しい `Docker Compose` アプリを作成
2. Gitリポジトリ `guild-42/tokyo-rental-search-agent` を接続
3. Compose fileは `docker-compose.yml`
4. 環境変数を上書き（必要なら）
5. 永続ボリューム `rental-data` が `/app/data` にマウントされることを確認
6. デプロイ

ヘルスチェックは `GET /health` で動作確認できます。

## API

- `GET /` - Web UI
- `GET /api/properties` - アクティブ物件のJSON配列
- `GET /api/stats` - DB統計
- `GET /health` - ヘルスチェック

## アーキテクチャ

```
main.py               CLI entry point (fetch / serve / stats / migrate)
src/
  server.py           FastAPI app + background scheduler
  orchestrator.py     9ソース並列fetch → normalize → dedup → upsert
  db.py               SQLite (WAL) lifecycle management
  models.py           Pydantic schemas
  normalizer.py       Source-specific raw dicts → unified Property
  dedup.py            Cross-source dedup key
  scrapers/           9 site scrapers (base.py provides fetch_page/retry/rate-limit)
web/
  index.html / app.js / style.css
```
