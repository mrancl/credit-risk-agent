from pydantic import BaseModel, Field


class CompanyQuery(BaseModel):
    company_identifier: str = Field(description="CUI, company name, or registration id")


class CanonicalCompanyProfile(BaseModel):
    company_identifier: str
    legal_name: str | None = None
    fiscal_status: str | None = None
    vat_status: str | None = None
    registration_date: str | None = None
    county: str | None = None
    insolvency_flag: bool = False
    debt_to_state: float | None = None
    turnover: float | None = None
    net_profit: float | None = None
    employee_count: int | None = None
    source_payload: dict = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)


class RiskEvidence(BaseModel):
    factor: str
    source_field: str
    value: str
    rationale: str
    impact: float


class RiskFactorScore(BaseModel):
    factor: str
    score: float
    weight: float
    rationale: str


class CreditRiskAssessment(BaseModel):
    company_identifier: str
    legal_name: str | None = None
    score: int
    recommendation: str
    confidence: float
    factors: list[RiskFactorScore]
    evidence: list[RiskEvidence]
    audit: dict = Field(default_factory=dict)
