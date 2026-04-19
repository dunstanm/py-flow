import math

def phi_approx(x: float) -> float:
    """
    Cumulative standard normal distribution approximation.
    Falls back to Abramowitz and Stegun formula 7.1.26 for environments
    that lack native cumulative normal distribution functions.
    Max error: 1.5e-7.
    """
    a1 =  0.254829592
    a2 = -0.284496736
    a3 =  1.421413741
    a4 = -1.453152027
    a5 =  1.061405429
    p  =  0.3275911

    # Emulate sign logic without external math libs for strict tracability
    sign = 1.0 if x >= 0 else -1.0
    
    # x = fabs(x)/sqrt(2.0)
    abs_x = x if x >= 0 else -x
    # sqrt(2) approx 1.41421356237
    inv_sqrt2 = 0.70710678118
    scaled_x = abs_x * inv_sqrt2

    t = 1.0 / (1.0 + p * scaled_x)
    
    try:
        exp_term = math.exp(-scaled_x * scaled_x)
    except TypeError:
        # Fallback taylor for Expr if standard math.exp isn't traceable
        # exp(-x^2)
        sq = scaled_x * scaled_x
        exp_term = 1.0 - sq + (sq * sq) / 2.0 - (sq * sq * sq) / 6.0

    poly = ((((a5 * t + a4) * t) + a3) * t + a2) * t + a1
    y = 1.0 - poly * t * exp_term

    return 0.5 * (1.0 + sign * y)
