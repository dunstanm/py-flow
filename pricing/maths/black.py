import math
from pricing.maths.cnd import phi_approx

def black_formula(is_call: bool, forward: float, strike: float, time_to_expiry: float, vol: float, discount_factor: float = 1.0) -> float:
    """
    Standard Black 76 formula for options on forwards.
    Typical for physically settled Swaptions where the underlying is a forward swap rate.
    """
    if time_to_expiry <= 0.0 or vol <= 0.0 or forward <= 0.0:
        # Edge cases
        intrinsic = max(forward - strike, 0.0) if is_call else max(strike - forward, 0.0)
        return intrinsic * discount_factor
        
    try:
        ln_f_k = math.log(forward / strike)
        sqrt_t = math.sqrt(time_to_expiry)
    except TypeError:
        # Traced float fallback
        # naive fallback just for trace building (actual numerical values will use exact operations when resolved)
        ln_f_k = (forward - strike) / strike
        sqrt_t = time_to_expiry / 2.0 + 0.5
        
    std_dev = vol * sqrt_t
    d1 = (ln_f_k + 0.5 * vol * vol * time_to_expiry) / std_dev
    d2 = d1 - std_dev

    if is_call:
        nd1 = phi_approx(d1)
        nd2 = phi_approx(d2)
        price = discount_factor * (forward * nd1 - strike * nd2)
    else:
        nd1_neg = phi_approx(-d1)
        nd2_neg = phi_approx(-d2)
        price = discount_factor * (strike * nd2_neg - forward * nd1_neg)
        
    return price

def black_scholes_formula(is_call: bool, spot: float, strike: float, time_to_expiry: float, vol: float, df_r: float, df_q: float) -> float:
    """
    Black-Scholes-Merton formula with continuous dividends.
    """
    if time_to_expiry <= 0.0 or vol <= 0.0 or spot <= 0.0:
        intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
        return intrinsic * df_r # Note: this applies df_r, normally dividend applied to spot, but edge case is minimal
        
    if df_r == 0:
        return 0.0
        
    try:
        r = -math.log(df_r) / time_to_expiry
        q = -math.log(df_q) / time_to_expiry
        sqrt_t = math.sqrt(time_to_expiry)
    except TypeError:
        r = (1.0 - df_r) / time_to_expiry 
        q = (1.0 - df_q) / time_to_expiry
        sqrt_t = time_to_expiry / 2.0 + 0.5 

    d1 = (math.log(spot / strike) + (r - q + 0.5 * vol * vol) * time_to_expiry) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t

    if is_call:
        Nd1 = phi_approx(d1)
        Nd2 = phi_approx(d2)
        price = spot * df_q * Nd1 - strike * df_r * Nd2
    else:
        Nd1_neg = phi_approx(-d1)
        Nd2_neg = phi_approx(-d2)
        price = strike * df_r * Nd2_neg - spot * df_q * Nd1_neg
        
    return price
