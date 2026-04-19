from reactive.traced import _start_tracing
from tests.test_demo_ir_swap import reactive_graph
from store.base import Storable
import pytest

def test_debug(reactive_graph):
    usd_ois_5y = reactive_graph["usd_ois_5y"]
    swap = reactive_graph["swap_usd_5y"]
    fitter = reactive_graph["fitter"]

    print("\n[DEBUG] Init NPV:", swap.npv)
    
    usd_ois_5y.batch_update(rate=0.0510)
    fitter.solve()
    from reaktiv.scheduler import flush
    flush()

    print("[DEBUG] Post solve NPV:", swap.npv)
    print("[DEBUG] Fixed Leg:", swap.fixed_leg_pv)
    print("[DEBUG] Float Leg:", swap.float_leg_pv)
    print("[DEBUG] Fixed Rate:", swap.fixed_rate)
