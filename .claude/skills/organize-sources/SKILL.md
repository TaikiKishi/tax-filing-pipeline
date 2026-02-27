---
name: organize-sources
description: |
  ソースファイルの整理・リネーム・manifest.json生成（Stage 0）。
  「ファイルを整理して」「ソースを整理して」「manifest生成」などの指示で使用。
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Write, Bash, Glob, Grep
argument-hint: "[year_label]"
---

# ソースファイル整理（Stage 0）

スキャン済みファイルを整理・リネームし、manifest.jsonを生成する。

## 対象年度

年度ラベル: `$ARGUMENTS` （例: `2025_R7`）

## 実行

```bash
python3 -m src.pipeline $ARGUMENTS --stage 0
```

## 処理内容

1. `docs/references/` 等のソースファイルを `years/{year_label}/sources/` に分類・リネーム
2. カテゴリ別サブディレクトリに配置:
   - `receipts/` — 医療費領収書（`MED-NNN_日付_患者名_施設名.pdf`）
   - `reimbursements/` — 補填書類（`RMB-NNN_日付_ソース名.ext`）
   - `mynaportal/` — マイナポータル出力
   - `social_insurance/` — 社会保険料書類
   - `other/` — その他（ふるさと納税XML等）
3. `years/{year_label}/manifest.json` を生成（原本名→保存名→IDの対応表）

## 前提条件

- `years/{year_label}/data/receipts.json` が存在すること（リネームにレシートデータを使用）
- ソースファイルが `docs/references/` に配置されていること

## 出力

- `years/{year_label}/sources/` 配下にリネーム済みファイル
- `years/{year_label}/manifest.json`
