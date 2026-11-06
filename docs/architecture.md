# Architecture

1. **Collection:** Selenium visits the site manifest; tshark records one trace per
   visit. Record site ID, session ID, browser settings, condition, and success.
2. **Feature extraction:** Convert metadata into counts, byte totals, packet-size
   statistics, inter-arrival times, and directional bursts. Keep labels separate.
3. **Training and evaluation:** Fit a Random Forest using training sessions only;
   tune on validation sessions and evaluate once on held-out later sessions.
4. **Defense:** Apply bounded jitter with netem or a trace-level simulation.
   Live observation must be downstream of shaping in each direction. Simulation
   cannot measure actual browser loading time or induced retransmissions.
5. **Presentation:** Streamlit dashboard for fresh-visit predictions and comparison
   of baseline and defended results. This component is not implemented yet.

The collector, metadata extractor, date-based Random Forest experiment, bounded
jitter simulation, adaptive comparison, CLI prediction, and local results/replay
dashboard are implemented. See [analysis details](analysis.md) for the exact feature
definition, reproducibility commands, and limitations. The dashboard currently
replays saved traces; fresh controlled visits use the collector and prediction CLI.
Live network shaping has not been implemented or evaluated.
