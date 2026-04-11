import sys
import os

project_root = os.path.abspath(os.getcwd())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from pricing.marketmodels.integrated_rate_curve import IntegratedShortRateCurve
    from pricing.marketmodels.curve_fitter import CurveFitter
    print("Imports successful")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
