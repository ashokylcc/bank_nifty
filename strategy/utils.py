def get_atm_strike(close_price: float) -> int:
    """Rounds to the nearest 100 for Bank Nifty options."""
    return round(close_price / 100) * 100
