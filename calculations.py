"""Pure finance calculations. All rates are decimal fractions, not percentages."""
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class CapitalCosts:
    beta_levered: float
    cost_equity_usd: float
    cost_equity_local: float
    cost_debt_usd: float
    cost_debt_local: float
    spread_local: float
    wacc_usd: float
    wacc_local: float

    def to_dict(self):
        return asdict(self)


def calculate(beta_unlevered: float, us_yield: float, foreign_yield: float,
              equity_risk_premium: float, debt_share: float, tax_rate: float,
              bbb_spread_usd: float, foreign_spread_override: float | None = None) -> CapitalCosts:
    """Hamada relevering, domestic-currency CAPM, and yield-adjusted foreign debt.

    Foreign borrowing cost (automatic) is derived via the interest-rate ratio:
      (1 + local debt cost) = (1 + USD debt cost) * (1 + local gov yield) / (1 + US gov yield)
    Local spread = local debt cost - local gov yield.
    This is a MODELING ASSUMPTION, not a live quoted BBB spread; verify against class formulas.
    """
    if not (0 <= debt_share < 1):
        raise ValueError('Debt share must be >= 0% and < 100%.')
    if not (0 <= tax_rate <= 1):
        raise ValueError('Tax rate must be between 0% and 100%.')
    if beta_unlevered < 0 or equity_risk_premium < 0 or bbb_spread_usd < 0:
        raise ValueError('Beta, ERP, and USD borrowing spread cannot be negative.')
    if us_yield <= -1 or foreign_yield <= -1:
        raise ValueError('Yields must exceed -100%.')
    if foreign_spread_override is not None and foreign_spread_override < 0:
        raise ValueError('Local spread override cannot be negative.')

    equity_share = 1 - debt_share
    de_ratio = debt_share / equity_share
    beta_l = beta_unlevered * (1 + (1 - tax_rate) * de_ratio)
    ke_us = us_yield + beta_l * equity_risk_premium
    ke_local = foreign_yield + beta_l * equity_risk_premium
    kd_us = us_yield + bbb_spread_usd
    kd_local_auto = (1 + kd_us) * ((1 + foreign_yield) / (1 + us_yield)) - 1
    local_spread_auto = kd_local_auto - foreign_yield
    spread_local = local_spread_auto if foreign_spread_override is None else foreign_spread_override
    kd_local = foreign_yield + spread_local
    wacc_us = equity_share * ke_us + debt_share * kd_us * (1 - tax_rate)
    wacc_local = equity_share * ke_local + debt_share * kd_local * (1 - tax_rate)
    return CapitalCosts(beta_l, ke_us, ke_local, kd_us, kd_local, spread_local, wacc_us, wacc_local)
