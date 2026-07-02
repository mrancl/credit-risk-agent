from app.integrations.schema import (
    CanonicalCompanyProfile,
    PublicContractsSummary,
    YearFinancials,
)


def _read_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "insolventa", "insolvent"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _get_first(raw: dict, keys: list[str]) -> object | None:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def _to_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _indicator_map(year_entry: dict) -> dict[str, float]:
    """Flatten a DemoANAF financials year entry's indicator list by code."""
    out: dict[str, float] = {}
    for indicator in year_entry.get("indicators", []) or []:
        code = indicator.get("code")
        value = _to_float(indicator.get("value"))
        if code and value is not None:
            out[code] = value
    return out


def _year_from_indicators(year: int, indicators: dict[str, float]) -> YearFinancials:
    net_profit = indicators.get("I18", 0.0)
    net_loss = indicators.get("I19", 0.0)
    if net_profit == 0.0 and net_loss > 0.0:
        net_profit = -net_loss
    return YearFinancials(
        year=year,
        turnover=indicators.get("I13"),
        net_profit=net_profit if ("I18" in indicators or "I19" in indicators) else None,
        employee_count=int(indicators["I20"]) if "I20" in indicators else None,
        total_liabilities=indicators.get("I7"),
        total_equity=indicators.get("I10"),
        current_assets=indicators.get("I2"),
        cash=indicators.get("I5"),
    )


def _extract_financial_history(raw: dict) -> list[YearFinancials]:
    """Extract all fiscal years from DemoANAF financials, oldest first.

    DemoANAF (get_company and get_company_financials) reports balance-sheet
    data as coded indicators per year: I13 net turnover, I18 net profit,
    I19 net loss, I20 average employees, I7 total liabilities, I10 total
    equity, I2 current assets, I5 cash. Years without a turnover figure are
    skipped (partial fetches).
    """
    financials = raw.get("financials") if isinstance(raw.get("financials"), dict) else raw
    years = financials.get("years") if isinstance(financials, dict) else None
    if not isinstance(years, list):
        return []

    history: dict[int, YearFinancials] = {}
    for entry in years:
        if not isinstance(entry, dict):
            continue
        year = entry.get("year")
        indicators = _indicator_map(entry)
        if not isinstance(year, int) or "I13" not in indicators:
            continue
        history[year] = _year_from_indicators(year, indicators)
    return [history[year] for year in sorted(history)]


def _extract_public_contracts(raw: dict) -> PublicContractsSummary | None:
    """Aggregate the 'public_contracts' block merged in by the data agent.

    Expected shape: the check_company_contracts result (exists/asSupplier/
    asAuthority/latestDate), optionally with 'rows' from
    list_company_contracts ({contractDate, valueRon, ...}).
    """
    block = raw.get("public_contracts")
    if not isinstance(block, dict):
        return None

    as_supplier = int(block.get("asSupplier") or block.get("contracts_as_supplier") or 0)
    as_authority = int(block.get("asAuthority") or block.get("contracts_as_authority") or 0)

    value_by_year: dict[str, float] = {}
    total_value = 0.0
    rows = block.get("rows")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = _to_float(row.get("valueRon"))
            if value is None:
                continue
            year = str(row.get("contractDate") or "")[:4]
            if year.isdigit():
                value_by_year[year] = value_by_year.get(year, 0.0) + value
            total_value += value

    return PublicContractsSummary(
        has_contracts=bool(block.get("exists")) or as_supplier > 0 or as_authority > 0,
        contracts_as_supplier=as_supplier,
        contracts_as_authority=as_authority,
        latest_contract_date=block.get("latestDate") or block.get("latest_contract_date"),
        total_value_ron=total_value if value_by_year else None,
        value_by_year=value_by_year,
    )


def _derive_fiscal_status(raw: dict) -> object | None:
    explicit = _get_first(raw, ["stare_fiscala", "fiscal_status", "onrcStatusLabel", "registrationState"])
    if explicit is not None:
        return explicit
    inactive = raw.get("inactive")
    if isinstance(inactive, bool):
        return "inactive" if inactive else "active"
    return _get_first(raw, ["status"])


def _derive_vat_status(raw: dict) -> object | None:
    # Note: DemoANAF's "vatStatus" field is data freshness, not VAT standing.
    explicit = _get_first(raw, ["status_tva", "vat_status"])
    if explicit is not None:
        return explicit
    vat_registered = raw.get("vatRegistered")
    if isinstance(vat_registered, bool):
        return "registered" if vat_registered else "not_registered"
    return None


def _derive_county(raw: dict) -> object | None:
    explicit = _get_first(raw, ["judet", "county"])
    if explicit is not None:
        return explicit
    headquarters = raw.get("headquartersAddress")
    if isinstance(headquarters, dict):
        return headquarters.get("county")
    return None


def _derive_insolvency(raw: dict) -> bool:
    explicit = _get_first(raw, ["insolventa", "insolvency", "insolvency_flag"])
    if explicit is not None:
        return _read_bool(explicit)
    # Fall back to ONRC status text, e.g. "Insolvență" / "în insolvență".
    for key in ("onrcStatusLabel", "registrationState"):
        value = raw.get(key)
        if isinstance(value, str) and "insolven" in value.lower():
            return True
    return False


def normalize_company_payload(company_identifier: str, raw_payload: dict) -> CanonicalCompanyProfile:
    legal_name = _get_first(raw_payload, ["denumire", "name", "legal_name", "nume"])  # ANAF variants
    fiscal_status = _derive_fiscal_status(raw_payload)
    vat_status = _derive_vat_status(raw_payload)
    registration_date = _get_first(
        raw_payload, ["data_inregistrare", "registration_date", "registrationDate"]
    )
    county = _derive_county(raw_payload)

    caen_code = _get_first(raw_payload, ["primaryCaen", "caenCode", "caen", "cod_caen"])
    debt_to_state = _get_first(raw_payload, ["datorii_stat", "debt_to_state", "debts"])
    turnover = _get_first(raw_payload, ["cifra_afaceri", "turnover"])
    net_profit = _get_first(raw_payload, ["profit_net", "net_profit"])
    employee_count = _get_first(raw_payload, ["numar_angajati", "employee_count"])

    financial_history = _extract_financial_history(raw_payload)
    latest = financial_history[-1] if financial_history else None
    if latest is not None:
        if turnover is None:
            turnover = latest.turnover
        if net_profit is None:
            net_profit = latest.net_profit
        if employee_count is None:
            employee_count = latest.employee_count

    profile = CanonicalCompanyProfile(
        company_identifier=company_identifier,
        legal_name=str(legal_name) if legal_name is not None else None,
        fiscal_status=str(fiscal_status) if fiscal_status is not None else None,
        vat_status=str(vat_status) if vat_status is not None else None,
        registration_date=str(registration_date) if registration_date is not None else None,
        county=str(county) if county is not None else None,
        caen_code=str(caen_code) if caen_code is not None else None,
        insolvency_flag=_derive_insolvency(raw_payload),
        debt_to_state=_to_float(debt_to_state),
        turnover=_to_float(turnover),
        net_profit=_to_float(net_profit),
        employee_count=int(employee_count) if employee_count not in (None, "") else None,
        financial_history=financial_history,
        public_contracts=_extract_public_contracts(raw_payload),
        source_payload=raw_payload,
    )

    missing_fields: list[str] = []
    if profile.legal_name is None:
        missing_fields.append("legal_name")
    if profile.fiscal_status is None:
        missing_fields.append("fiscal_status")
    if profile.turnover is None:
        missing_fields.append("turnover")
    if profile.net_profit is None:
        missing_fields.append("net_profit")

    profile.missing_fields = missing_fields
    return profile
