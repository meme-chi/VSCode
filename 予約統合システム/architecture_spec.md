# 4チャネル横断 予約処理半自動化システム アーキテクチャ設計書

## 1. システム概要
本システムは、レンタルスペース（Paso / Slow 等）の4つの予約チャネル（スペースマーケット・インスタベース・カシカシ・公式サイト `pasoslow.jp`）における予約受付・ダブルブッキング防止・スマートロック発行・顧客案内・管理画面操作を**完全無料（0円）構成**で半自動化するシステムである。

### 設計の基本方針
1. **入り口の完全統一（メールマスター方式）：** 各媒体の標準カレンダー同期（挙動差異や二重登録の原因）は使用せず、全4チャネルから届く「管理者宛て通知メール」を唯一の正（マスター）としてGmail＋GASで集約する。
2. **Human-in-the-Loop（半自動承認）：** 規約違反やトラブルリスクのあるポータル予約はLINEへ承認通知を送り、管理者のワンタップで後続処理を実行する。公式サイト予約は重複がなければ即時自動確定とする。
3. **ハイブリッド実行基盤：** 24時間365日の監視・台帳化・鍵発行・通知はGoogleクラウド（GAS）で常時稼働させ、ブラウザ操作が必要な管理画面の枠止め・承認ボタン押下は手元PC（Docker ＋ Playwright）で実行する。

---

## 2. システム全体アーキテクチャ図

```mermaid
flowchart TB
    subgraph Channels ["1. 予約受付チャネル（4媒体）"]
        SM["スペースマーケット"]
        IB["インスタベース"]
        KK["カシカシ"]
        WP["公式サイト (pasoslow.jp)<br>WordPress予約プラグイン"]
    end

    subgraph GoogleCloud ["2. 統合制御・マスター基盤（Google Cloud / 完全無料）"]
        GM["Gmail<br>(通知メール受信トレイ)"]
        GAS["Google Apps Script (GAS)<br>・メール種別判定＆正規表現パーサー<br>・重複チェック＆バッファ計算<br>・実行キュー制御"]
        SS[("Google スプレッドシート<br>・統合予約台帳<br>・Playwright実行キュー")]
        GC["Google カレンダー<br>(Paso用 / Slow用 マスター)"]
    end

    subgraph ExternalAPI ["3. 外部API連携（無料枠）"]
        SB["SwitchBot API v1.1<br>(一時パスコード自動発行・削除)"]
        LINE["LINE Messaging API<br>(管理者への通知 ＆ ワンタップ承認UI)"]
        MAIL["顧客自動返信メール<br>(GmailApp / 公式サイト予約者向け)"]
    end

    subgraph LocalDocker ["4. ブラウザ自動操作基盤（Windows PC / Docker）"]
        PW["Python + Playwright (Chromium)<br>・管理画面ログイン＆セッション維持<br>・承認ボタン押下＆定型文送信<br>・他媒体の該当時間帯ブロック/解除"]
    end

    %% データフロー
    SM & IB & KK & WP -->|"① 予約・変更・キャンセル通知メール"| GM
    GM <-->|"② 定期ポーリング＆ラベル管理"| GAS
    GAS <-->|"③ 台帳記録＆キュー追加"| SS
    GAS <-->|"④ 重複照合＆予定作成/変更/削除"| GC

    GAS -->|"⑤ 暗証番号発行/削除"| SB
    GAS <-->|"⑥ 承認依頼通知 / ボタン応答Webhook"| LINE
    GAS -->|"⑦ 確定＆入室案内送信(公式のみ)"| MAIL

    SS <-->|"⑧ 未処理タスク取得＆完了報告"| PW
    PW -.->|"⑨ 枠ブロック / 承認操作 / メッセージ送信"| SM & IB & KK & WP
```

---

## 3. 予約種別ごとの処理シーケンス図

### 3.1 新規予約確定時の処理フロー（全チャネル共通〜分岐）

```mermaid
sequenceDiagram
    autonumber
    actor Guest as 予約者
    participant Media as 各媒体 / 公式サイト
    participant GAS as Gmail + GAS
    participant Cal as Googleカレンダー / 台帳
    participant SB as SwitchBot API
    participant Admin as 管理者 (LINE)
    participant PW as Docker (Playwright)

    Guest->>Media: 予約申込（確定 or リクエスト）
    Media->>GAS: 管理者宛て通知メール送信
    GAS->>GAS: チャネル判定・項目抽出（ID/日時/スペース/連絡先）
    GAS->>Cal: 既存予定＋前後清掃バッファとの重複チェック

    alt 重複あり（ダブルブッキング検知）
        GAS->>Cal: ステータス「重複要確認」で記録
        GAS->>Admin: 【緊急警告】時間重複アラート送信
    else 重複なし（正常）
        GAS->>Cal: カレンダー予定作成（イベントID保存）
        GAS->>SB: 一時パスコード発行（開始15分前〜終了15分後）
        SB-->>GAS: 暗証番号（6桁）返却

        alt 公式サイト（pasoslow.jp）からの予約
            GAS->>Guest: 予約確定＆暗証番号・入室案内メール自動送信
            GAS->>Admin: 公式サイト予約確定サマリー通知
            GAS->>Cal: キュー追加「ポータル3媒体を即時ブロック」
        else ポータル3媒体からの予約（承認制 / 即確定）
            GAS->>Admin: 予約詳細＋[承認実行] / [手動対応]ボタン送信
            Admin->>GAS: [承認実行]ボタン押下（Webhook）
            GAS->>Cal: キュー追加「該当媒体の承認＆案内送信 ＋ 他媒体ブロック」
        end

        PW->>Cal: 実行キューを取得
        PW->>Media: 該当媒体の承認・案内送信 ＆ 他媒体の枠を「利用不可」に変更
        PW->>Cal: ステータスを「完了」に更新
    end
```

### 3.2 キャンセル・日時変更時の同期フロー

```mermaid
flowchart LR
    A["キャンセル / 変更メール受信"] --> B["GASパーサーで<br>「媒体名＋予約ID」を特定"]
    B --> C["スプレッドシートから<br>該当行を検索"]
    C --> D["Googleカレンダーの<br>イベントIDを指定して削除/更新"]
    D --> E["SwitchBot APIで<br>発行済みパスコードを削除/再発行"]
    E --> F["Playwrightキューへ<br>「他媒体のブロック解除」を登録"]
    F --> G["管理者LINEへ<br>キャンセル処理完了を通知"]
```

---

## 4. データ設計（Googleスプレッドシート構成）

### シート1：`予約マスター台帳`
すべてのチャネルの予約を一元管理するメインテーブル。

| 列 | カラム名 | データ型 | 説明・格納例 |
| :--- | :--- | :--- | :--- |
| A | `internal_id` | 文字列 | システム管理ID（例：`RES-20261128-001`） |
| B | `channel` | 文字列 | 媒体名（`spacemarket` / `instabase` / `kashikashi` / `official`） |
| C | `external_res_id` | 文字列 | 各媒体の予約番号（名寄せ・キャンセル時の検索キー） |
| D | `space_name` | 文字列 | 対象スペース（`Paso` / `Slow`） |
| E | `status` | 文字列 | `承認待ち` / `確定(操作待ち)` / `確定(完了)` / `キャンセル` / `重複エラー` |
| F | `start_at` | 日時 | 利用開始日時（`2026/12/01 10:00`） |
| G | `end_at` | 日時 | 利用終了日時（`2026/12/01 13:00`） |
| H | `guest_name` | 文字列 | 予約者氏名 |
| I | `guest_email` | 文字列 | 予約者メールアドレス（公式サイト予約時のみ格納） |
| J | `purpose_options` | 文字列 | 利用目的・人数・オプション（酸素カプセル等） |
| K | `pin_code` | 文字列 | SwitchBotで発行した6桁暗証番号 |
| L | `gcal_event_id` | 文字列 | 登録したGoogleカレンダーのイベントID（変更・削除用） |
| M | `updated_at` | 日時 | 最終更新タイムスタンプ |

### シート2：`Playwright実行キュー`
GASからDocker上のPlaywrightワーカーへブラウザ操作を指示するための連携テーブル。

| 列 | カラム名 | 説明 |
| :--- | :--- | :--- |
| A | `queue_id` | キュー識別ID |
| B | `target_channel` | 操作対象媒体（`spacemarket` / `instabase` / `kashikashi` / `wordpress`） |
| C | `action_type` | `APPROVE_AND_SEND`（承認＆案内送信） / `BLOCK_SLOT`（枠止め） / `UNBLOCK_SLOT`（枠解除） |
| D | `space_name` | `Paso` / `Slow` |
| E | `start_at` / `end_at` | 対象時間帯 |
| F | `message_body` | 送信する入室案内文（`APPROVE_AND_SEND` 時のみ） |
| G | `exec_status` | `PENDING`（未実行） / `RUNNING`（実行中） / `DONE`（完了） / `ERROR`（要手動対応） |
| H | `error_log` | 失敗時のスクリーンショットパス・エラー内容 |

---

## 5. 技術スタック・コスト構成一覧

| レイヤー | 採用技術・サービス | プラン・費用 | 役割 |
| :--- | :--- | :--- | :--- |
| **メール受信・解析** | Gmail ＋ Google Apps Script | **無料**（Google標準枠） | 1〜5分間隔のトリガー実行、正規表現パース |
| **データベース・キュー** | Google スプレッドシート | **無料**（Google標準枠） | 予約台帳、Playwrightとの非同期連携キュー |
| **スケジュール管理** | Google カレンダー | **無料**（Google標準枠） | スペース別空き枠判定、清掃バッファ管理 |
| **スマートロック制御** | SwitchBot API (v1.1) | **無料**（1日1万回まで） | 期間限定パスコードの自動生成・無効化 |
| **管理者通知・承認UI** | LINE Messaging API | **無料**（月200通まで） | Flex Messageによる予約通知・承認ボタン操作 |
| **自動ブラウザ操作** | Docker ＋ Python ＋ Playwright | **無料**（OSS・ローカル稼働） | 管理画面のログイン維持、承認操作、在庫ブロック |

---

## 6. セキュリティ・異常系フォールバック設計

1. **認証情報の分離管理**
   * 3媒体およびWordPressのログインID・パスワード、各種APIキーはソースコード（Gitリポジトリ）に一切含めず、GASの「スクリプトプロパティ」およびDockerの「`.env`（`.gitignore`対象）」に隔離する。
2. **2段階認証・HTML構造変更時の安全停止**
   * Playwrightで管理画面操作中にログイン画面の2段階認証（SMS/メール認証）やDOM要素の不一致が発生した場合、無限リトライを行わず即座にステータスを `ERROR` とし、画面キャプチャを保存した上で管理者LINEへ「手動操作が必要です」と通知する。
3. **PC停止時のタイムラグ制御**
   * Windows PCがスリープまたは電源オフの間に予約が入った場合、GAS側の台帳・カレンダー・鍵発行までは即時完了させ、LINE通知に「※PC停止中のため他媒体の枠止め待機中」と明記する。PC起動時にDockerワーカーが `PENDING` キューを順次消化する。