"""
確定申告支援ツール - データモデル定義

全モジュール共通のデータ構造を定義する。
JSONシリアライズ可能なdataclassで統一。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional


# ── 列挙型 ──────────────────────────────────────────────

class ReceiptCategory(str, Enum):
    """領収書の分類"""
    MEDICAL = "medical"              # 医療費（病院・診療所）
    PHARMACY = "pharmacy"            # 調剤薬局
    DENTAL = "dental"                # 歯科
    PENSION = "pension"              # 国民年金保険料
    HEALTH_INSURANCE = "health_insurance"  # 国民健康保険税
    OTHER = "other"


class DeductionType(str, Enum):
    """控除区分"""
    MEDICAL_EXPENSE = "medical_expense"        # 医療費控除
    SOCIAL_INSURANCE = "social_insurance"      # 社会保険料控除
    NOT_DEDUCTIBLE = "not_deductible"          # 控除対象外


class JudgmentResult(str, Enum):
    """控除判定結果"""
    DEDUCTIBLE = "deductible"                  # 控除対象
    NOT_DEDUCTIBLE = "not_deductible"          # 控除対象外
    CONDITIONAL = "conditional"                # 条件付き（要確認）
    MYNAPORTAL_COVERED = "mynaportal_covered"  # マイナポータル連携で処理済み


class MedicalExpenseType(str, Enum):
    """医療費集計フォームの区分"""
    TREATMENT = "診療・治療"
    MEDICINE = "医薬品購入"
    NURSING = "介護保険サービス"
    OTHER = "その他の医療費"


class MatchStatus(str, Enum):
    """突合結果"""
    MATCHED = "matched"                        # マイナポータル通知と一致
    RECEIPT_ONLY = "receipt_only"               # 領収書のみ（通知なし）
    NOTIFICATION_ONLY = "notification_only"     # 通知のみ（領収書なし）
    PARTIAL = "partial"                         # 部分一致


# ── マイナポータル医療費通知 ─────────────────────────────

@dataclass
class MynaportalEntry:
    """マイナポータル医療費通知の1行分"""
    year_month: str              # "2025-03"
    category: str                # "医科外来", "歯科外来", "調剤", "入院" 等
    facility: str                # 医療機関名
    days: int                    # 日数
    total: int                   # 医療費総額（10割）
    copay: int                   # 窓口負担相当額
    meal_cost: int = 0           # 食事療養費（入院時）
    insurer: str = ""            # 保険者名


# ── スキャン領収書 ──────────────────────────────────────

@dataclass
class Receipt:
    """スキャンPDF領収書の構造化データ"""
    id: str                          # ファイル名ベースのID
    date: str                        # "2025-04-24"
    patient: str                     # 患者名
    facility: str                    # 医療機関名
    department: str = ""             # 診療科
    insurance_type: str = ""         # "社保", "国保", "自費" 等
    copay_rate: int = 0              # 負担割合(%)
    insurance_amount: int = 0        # 保険診療費①（窓口負担額）
    out_of_pocket: int = 0           # 保険外自費②
    out_of_pocket_detail: dict = field(default_factory=dict)  # 自費内訳
    meal_cost: int = 0               # 食事療養費
    total: int = 0                   # 合計支払額
    receipt_type: str = ""           # "hospital", "pharmacy", "dental", "pension_bill", "insurance_bill"
    category: ReceiptCategory = ReceiptCategory.MEDICAL
    notes: str = ""                  # 備考


# ── 突合結果 ────────────────────────────────────────────

@dataclass
class MatchResult:
    """1件の突合結果"""
    receipt: Optional[Receipt] = None
    notification: Optional[MynaportalEntry] = None
    match_status: MatchStatus = MatchStatus.RECEIPT_ONLY
    patient: str = ""
    year_month: str = ""
    facility: str = ""

    # 控除判定
    judgment: JudgmentResult = JudgmentResult.DEDUCTIBLE
    judgment_reason: str = ""
    tax_answer_ref: str = ""         # 国税庁タックスアンサー番号
    deduction_type: DeductionType = DeductionType.MEDICAL_EXPENSE

    # 集計フォーム用
    deductible_amount: int = 0       # 控除対象額
    reimbursement: int = 0           # 補填額

    # xlsx出力対象フラグ
    include_in_xlsx: bool = False    # 集計フォームに記載するか


# ── 雑所得・経費 ────────────────────────────────────────

@dataclass
class MiscIncome:
    """雑所得"""
    payer: str          # 支払元
    amount: int         # 金額
    income_type: str    # "原稿料", "謝金" 等
    withholding: int = 0  # 源泉徴収税額


@dataclass
class Expense:
    """経費"""
    item: str            # 項目名
    amount_usd: float = 0.0
    amount_jpy: int = 0
    allocation_rate: float = 0.0  # 按分率
    deductible: int = 0           # 経費計上額


@dataclass
class SocialInsurance:
    """社会保険料"""
    insurance_type: str   # "国民年金保険料", "国民健康保険税"
    payer: str            # 名義人
    amount: int = 0       # 金額
    period: str = ""      # 対象期間
    notes: str = ""


@dataclass
class SalaryIncome:
    """源泉徴収票データ（salary_income.json に対応）"""
    payer: str = ""                          # 支払者
    payment_amount: int = 0                  # 支払金額
    income_after_deduction: int = 0          # 給与所得控除後の金額
    total_deduction: int = 0                 # 所得控除の額の合計額
    withholding_tax: int = 0                 # 源泉徴収税額
    social_insurance: int = 0               # 社会保険料等の金額
    life_insurance_deduction: int = 0       # 生命保険料の控除額
    earthquake_insurance_deduction: int = 0  # 地震保険料の控除額
    housing_loan_credit: int = 0            # 住宅借入金等特別控除の額
    spouse_deduction: int = 0               # 配偶者控除等の額
    dependent_deduction: int = 0            # 扶養控除の額


# ── JSON入出力ヘルパー ──────────────────────────────────

def save_json(data, path: str | Path):
    """dataclassまたはdictをJSONファイルに保存"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def _convert(obj):
        if hasattr(obj, '__dataclass_fields__'):
            return asdict(obj)
        if isinstance(obj, Enum):
            return obj.value
        raise TypeError(f"Cannot serialize {type(obj)}")

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=_convert)


def load_json(path: str | Path) -> dict | list:
    """JSONファイルを読み込み"""
    with open(Path(path), 'r', encoding='utf-8') as f:
        return json.load(f)
