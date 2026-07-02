from pydantic import BaseModel, Field


class CompanyQuery(BaseModel):
    company_identifier: str = Field(description="CUI, company name, or registration id")


class YearFinancials(BaseModel):
    """One fiscal year of balance-sheet data (DemoANAF indicators I1-I20)."""

    year: int
    turnover: float | None = None  # I13
    net_profit: float | None = None  # I18 (or -I19 when in loss)
    employee_count: int | None = None  # I20
    total_liabilities: float | None = None  # I7
    total_equity: float | None = None  # I10
    current_assets: float | None = None  # I2
    cash: float | None = None  # I5


class PublicContractsSummary(BaseModel):
    """Aggregated SEAP public-procurement exposure for a company."""

    has_contracts: bool = False
    contracts_as_supplier: int = 0
    contracts_as_authority: int = 0
    latest_contract_date: str | None = None
    total_value_ron: float | None = None
    value_by_year: dict[str, float] = Field(default_factory=dict)


class CanonicalCompanyProfile(BaseModel):
    company_identifier: str
    legal_name: str | None = None
    fiscal_status: str | None = None
    vat_status: str | None = None
    registration_date: str | None = None
    county: str | None = None
    caen_code: str | None = None
    insolvency_flag: bool = False
    debt_to_state: float | None = None
    turnover: float | None = None
    net_profit: float | None = None
    employee_count: int | None = None
    financial_history: list[YearFinancials] = Field(default_factory=list)
    public_contracts: PublicContractsSummary | None = None
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
