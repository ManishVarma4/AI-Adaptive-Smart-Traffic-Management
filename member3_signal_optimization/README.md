# Member 3 — Emergency-Aware Adaptive Signals (SUMO)

Features:
- Normal cars plus explicit ambulance/fire-truck test vehicles.
- Left, straight, and right routes from all four approaches.
- Adaptive mode prioritizes an active emergency vehicle's inbound approach.
- Starvation protection: approaches waiting at least 90 seconds are scheduled,
  with emergency priority capped when a non-emergency approach is overdue.
- Yellow (3s) and all-red (1s) intervals between served approaches.
- Fixed-time baseline uses 30s green and a cyclic N → S → E → W order.

## Windows PowerShell
```powershell
$env:SUMO_HOME = "C:\Program Files (x86)\SUMO"
$env:Path += ";C:\Program Files (x86)\SUMO\bin"
$env:PYTHONPATH += ";C:\Program Files (x86)\SUMO\tools"
python .\member3_signal_optimization\run_comparison.py
python .\member3_signal_optimization\run_comparison.py --gui
```

Outputs:
- `comparison_results.csv`
- `green_decisions.csv`

The explicit emergency vehicles are synthetic test vehicles. This is a
simulation prototype, not a certified traffic controller. SUMO's vehicle class
does not itself change a traffic light: TraCI detects the emergency type and
the adaptive controller selects its approach at the next safe phase transition.
Check route validity, signal states, and CSV outputs after running.
