# NIFTY Scenario Lab model reference data

`model_data.json` contains the logistic-model weights, calibration parameters, historical scenario statistics, confidence-bucket scorecard, and expected-return blend constants extracted from the supplied `nifty-scenario-lab-github.zip` (snapshot dated 2026-10-01).

The daily report does **not** use the archive's embedded `live` forecast. `src/nifty_scenario_engine.py` fetches fresh NIFTY 50, India VIX, and US VIX data, recomputes the current features, and then applies these frozen, walk-forward-tested weights. The US VIX input is lagged by one Indian trading session to avoid look-ahead bias. If fresh feature data is unavailable, the report says so instead of silently falling back to the stale snapshot.

This is a secondary 1–3 month context overlay. The primary 10–40 trading-day plan remains the Smart Money participant-OI/regime signal and its entry/risk controls. Accuracy and historical scenario statistics are reproduced as supplied; sample sizes and below-baseline directional hit rates are shown in the report.

The model/reference assets are distributed under the MIT License; see `LICENSE`.
