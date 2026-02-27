---
name: generate-invoice
description: |
  請求書PDF生成。misc_income.json の収入データから請求書 Markdown を生成し、pandoc で PDF に変換する。
  「請求書を作成」「インボイス生成」「請求書PDF」などの指示で使用。
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Write, Bash, Glob
argument-hint: "[year_label] [reference_id]"
---

# 請求書 PDF 生成

`misc_income.json` の収入データから請求書を生成する。

## 対象年度

年度ラベル: `$ARGUMENTS` の最初の引数（例: `2025_R7`）
reference_id: `$ARGUMENTS` の2番目の引数（省略時は未生成分を一括生成）

## 処理手順

### 1. 前提条件チェック

pandoc の invoice プロファイルがデプロイされているか確認:

```bash
test -f ~/.pandoc/defaults/invoice.yaml && echo "OK" || echo "未デプロイ"
```

未デプロイの場合、以下を案内:

```bash
bash templates/pandoc/deploy.sh
```

### 2. 請求書 Markdown 生成

```bash
# 特定の reference_id のみ
python3 -m src.generate_invoice {year_label} --ref {reference_id}

# 未生成分を一括
python3 -m src.generate_invoice {year_label}
```

出力先: `years/{year_label}/output/invoices/INV-{reference_id}.md`

生成後、`misc_income.json` の該当エントリの `invoice_file` フィールドが自動更新される。

### 3. PDF 変換

```bash
# 個別
md2pdf years/{year_label}/output/invoices/INV-{reference_id}.md --profile invoice

# 一括（全 .md ファイル）
for f in years/{year_label}/output/invoices/INV-*.md; do
  md2pdf "$f" --profile invoice
done
```

### 4. 確認

PDF が生成されたら、ユーザーに確認を促す。WSL 環境の場合:

```bash
explorer.exe "$(wslpath -w years/{year_label}/output/invoices/INV-{reference_id}.pdf)"
```

## データフロー

```
misc_income.json (income[].*)
        |
        v
src/generate_invoice.py
        |
        v
output/invoices/INV-{reference_id}.md  (Markdown + raw LaTeX)
        |
        v
md2pdf --profile invoice
        |
        v
output/invoices/INV-{reference_id}.pdf  (A4 請求書)
```

## issuer 情報

請求書には `misc_income.json` の `issuer` ブロックから以下を読み取る:

- 発行者氏名
- 郵便番号・住所
- メールアドレス
- 振込先銀行情報（銀行名、支店名、口座種別、口座番号、口座名義）

`issuer` が未設定の場合は WARNING を表示する。

## 注意事項

- 生成される PDF には個人の住所・銀行口座情報が含まれる
- `years/*/output/invoices/` は `.gitignore` で除外されている
- Markdown ファイル自体も invoices/ 内に生成されるため git 管理外
