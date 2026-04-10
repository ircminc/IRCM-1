"""CAS reason code classification and denial analysis."""
from __future__ import annotations
import pandas as pd
from .aggregator import get_adjustments_df

# Embedded CAS reason code lookup (subset — expand as needed)
CAS_REASON_DESCRIPTIONS: dict[str, str] = {
    "1":  "Deductible amount",
    "2":  "Coinsurance amount",
    "3":  "Co-payment amount",
    "4":  "The service/equipment/drug is not covered by the plan",
    "5":  "The procedure code/type of bill is inconsistent with place of service",
    "6":  "The procedure/revenue code is inconsistent with the patient's age",
    "7":  "The procedure/revenue code is inconsistent with the patient's gender",
    "8":  "The procedure code is inconsistent with the provider type/specialty",
    "9":  "The diagnosis is inconsistent with patient age",
    "10": "The diagnosis is inconsistent with patient gender",
    "11": "The diagnosis is inconsistent with the procedure",
    "12": "The diagnosis is inconsistent with the provider type",
    "13": "The date of death precedes the date of service",
    "14": "The date of birth follows the date of service",
    "15": "The authorization number is missing, invalid, or does not apply to the billed services",
    "16": "Claim/service lacks information or has submission/billing error(s)",
    "18": "Exact duplicate claim/service",
    "19": "Claim denied because this is a work-related injury/illness",
    "20": "Claim denied because this injury/illness is covered by the liability carrier",
    "21": "Claim denied because this injury/illness is the liability of the no-fault carrier",
    "22": "This care may be covered by another payer per coordination of benefits",
    "23": "The impact of prior payer(s) adjudication including payments and/or adjustments",
    "24": "Charges are covered under a capitation agreement/managed care plan",
    "26": "Expenses incurred prior to coverage",
    "27": "Expenses incurred after coverage terminated",
    "29": "The time limit for filing has expired",
    "31": "Claim denied as patient cannot be identified as our insured",
    "32": "Our records indicate that this dependent is not an eligible dependent",
    "33": "Insured has no dependent coverage",
    "34": "Insured has no coverage for newborns",
    "35": "Lifetime benefit maximum has been reached",
    "39": "Services denied at the time authorization/pre-certification was requested",
    "40": "Charges do not meet qualifications for emergent/urgent care",
    "44": "Prompt pay discount",
    "45": "Charge exceeds fee schedule/maximum allowable",
    "49": "These are non-covered services because this is a routine exam or screening procedure",
    "50": "These are non-covered services because this is not deemed a 'medical necessity' by the payer",
    "51": "These are non-covered services because this is a pre-existing condition",
    "55": "Claim/service denied because procedure/treatment is deemed experimental/investigational",
    "57": "Payment adjusted because the service was not provided by a contracted/participating provider",
    "59": "Processed based on multiple or concurrent procedure rules",
    "85": "Patient Interest Adjustment (use only for interest payments made by Medicare)",
    "96": "Non-covered charge(s)",
    "97": "The benefit for this service is included in the payment/allowance for another service",
    "109": "Claim/service not covered by this payer/contractor",
    "119": "Benefit maximum for this time period or occurrence has been reached",
    "197": "Precertification/authorization/notification absent",
    "200": "Expenses incurred during lapse in coverage",
    "253": "Sequestration - reduction in federal payment",
}

DENIAL_CATEGORIES: dict[str, str] = {
    "billing_error":    ["4","5","6","7","8","9","10","11","12","15","16","18"],
    "duplicate":        ["18"],
    "eligibility":      ["26","27","29","31","32","33","34","35","200"],
    "authorization":    ["15","39","197"],
    "medical_necessity":["50","55","57"],
    "coordination":     ["22","23"],
    "contractual":      ["44","45","97"],
    "patient_resp":     ["1","2","3"],
    "non_covered":      ["4","49","51","96","109","119"],
}


def categorize_reason_code(rc: str) -> str:
    for category, codes in DENIAL_CATEGORIES.items():
        if rc in codes:
            return category
    return "other"


def denial_summary(file_ids: list[int] | None = None) -> pd.DataFrame:
    """
    Returns a summary DataFrame of denials by reason code.
    Columns: reason_code, description, group_code, category, count, total_amount, pct_of_total
    """
    df = get_adjustments_df(file_ids=file_ids)
    if df.empty:
        return pd.DataFrame(columns=["reason_code","description","group_code","category","count","total_amount","pct_of_total"])

    # Only denial-type adjustments (CO = contractual, OA = other; PR = patient resp)
    df = df[df["group_code"].isin(["CO", "OA", "PI", "CR"])]
    if df.empty:
        return pd.DataFrame()

    grp = df.groupby(["reason_code","group_code"]).agg(
        count=("amount","count"),
        total_amount=("amount","sum"),
    ).reset_index()

    total = grp["count"].sum()
    grp["description"] = grp["reason_code"].map(CAS_REASON_DESCRIPTIONS).fillna("Unknown")
    grp["category"]    = grp["reason_code"].apply(categorize_reason_code)
    grp["pct_of_total"] = (grp["count"] / total * 100).round(1)
    return grp.sort_values("count", ascending=False).reset_index(drop=True)


def top_denial_categories(file_ids: list[int] | None = None) -> pd.DataFrame:
    """Aggregate denial counts and amounts by category."""
    df = denial_summary(file_ids=file_ids)
    if df.empty:
        return df
    return (
        df.groupby("category")
        .agg(count=("count","sum"), total_amount=("total_amount","sum"))
        .reset_index()
        .sort_values("count", ascending=False)
    )
