# Metadata baseline and simulated jitter

The pipeline uses the audited 803-trace allowlist. It does not recollect, relabel,
or change raw captures. The collection environment remains separate from the new
`.venv-research` analysis environment.

## Windows setup and storage

Work in `D:\Peekaboo\peekaboo`. `scripts/setup-analysis.ps1` recreates the analysis
environment from `requirements-research-lock.txt`. It uses the existing `.venv`
Python or an explicit `-Python` executable path. Existing Python and Wireshark
executables on C: are read; new environments, downloads, caches, metadata, models,
and reports are written on D:.

Every supplied analysis/dashboard PowerShell launcher dot-sources
`scripts/use-d-drive.ps1`. For manual commands, dot-source that script first.
It sets process-local temporary/cache paths without changing Windows settings.
Use the dashboard launcher rather than bare Streamlit to also redirect its
configuration and machine-ID storage to `.cache/streamlit`. That redirection is
checked at startup and does not modify the installed library.

```powershell
.\scripts\run-analysis.ps1 -Stage extract
.\scripts\run-analysis.ps1 -Stage experiment -RunName experiment-v1
.\scripts\start-dashboard.ps1
```

Open http://127.0.0.1:8501 while the launcher runs. The dashboard binds only to
this machine. Existing experiment names cannot be overwritten. An intentional
repeat needs a new name; it does not create a new unseen test set.

## Feature definition

Use **TCP payload byte lengths after successful CONNECT**, not Ethernet frame
lengths or TLS record lengths. TLS handshake sizes are included, but handshake
fields such as SNI are never exported. Zero-payload ACKs and TCP setup/teardown
frames are excluded.

1. Verify the accepted index, unique visit IDs/hashes, baseline conditions, date
   splits, class coverage, and each capture's hash.
2. Decode the proxy port as HTTP with two-pass tshark dissection. Find the ending
   TCP sequence number of each plaintext CONNECT request and successful response.
   Inspect header bytes in memory only; do not save names or payloads as features.
3. Keep streams whose two boundaries are known. Exclude/count pre-existing or
   incomplete connections. Handle fragmented headers and reassembly emitted on
   an ACK. Clip segments/retransmissions crossing a plaintext boundary; retain
   other retransmissions as observed traffic.
4. Map outgoing as browser-to-proxy and incoming as proxy-to-browser using the
   port only within preprocessing. Neither ports nor stream IDs enter the model.
5. Anchor at the first retained payload and keep `[0, 20 seconds)`. The collector
   included lead-in/tail but saved no exact packet-clock navigation boundary.
   This anchor is not a page-load measurement; short spans may include idle time.
6. Compute 107 values: counts, bytes, duration, size/inter-arrival statistics,
   direction fractions, and burst statistics. A burst is a maximal same-direction
   run in the merged time-ordered trace. Standard deviation uses population form;
   empty statistics are zero.

Wireshark can display a reassembled record on its last TCP fragment, so a simple
`tls` display filter can miss earlier fragments. See its
[reassembly documentation](https://www.wireshark.org/docs/wsug_html_chunked/ChAdvReassemblySection.html).

## Outputs and integrity

`data/processed/analysis-v1/features.csv` contains only numeric features.
`visits.jsonl` stores corresponding row identities, labels, and splits separately.
`dataset.json` records checksums/schema/configuration; `extraction-audit.json`
accounts for every accepted visit. Any extraction failure blocks training.

Cached arrays contain only time, size, direction, and an anonymous flow index.
Sidecars store provenance and proxy ports for cache validation, never as model
inputs. Cache keys include extractor version, source hash, port, window, and
tshark version; the arrays are also checksummed. Increment the extractor version
when future changes affect packet selection. Raw files remain the source of
truth. All generated data and models are ignored by Git.

## Model and evaluation

Train on October 28–29 (448), validate on October 30 (187), and test on October 31
(168). All 20 classes occur in each split. Same-day sessions and every simulated
derivative remain with their source split.

Use a 300-tree RandomForestClassifier with square-root feature sampling,
training-based balanced subsample weights, and seed 42. Trees need no scaling.
Choose minimum leaf size 1, 2, or 4 by validation macro F1, then accuracy, then
larger leaf on a tie. Test data never enters fitting/selection. The selected model
remains trained on training dates only. Save a protocol snapshot before test scoring.
See the [classifier documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html).

Compare with a training-defined majority classifier and a seeded uniform guesser.
Expected uniform accuracy is 5%; observed finite-sample random accuracy can differ.
Report accuracy, macro F1, per-class precision/recall/support, confusion matrices,
predictions, and impurity feature importance (descriptive, not causal evidence).

## Simulated defense

Predeclared delay bounds: 0, 5, 20, 50, 100 milliseconds. Nonzero bounds use three
seeds. Draw a uniform candidate delay for each packet. Within each flow/direction,
delivery cannot precede the previous packet. Ordering is preserved and delays
remain within the bound. Different flows/directions can interleave differently.
Derive RNG seeds from experiment seed and capture hash, never site labels.

Retain all selected packets even when delivery extends beyond the window. Sort
delivery times and recompute features. Zero delay must reproduce baseline features
within numeric tolerance. Byte totals remain unchanged.

Compare the original classifier with a classifier trained on defended training
data. Adaptive models use baseline-selected hyperparameters; they are not separately
optimized. Report all predeclared bounds, without selecting on test scores.

Mean packet delay and trace-finish extension are simulation metrics, not measured
page-load time. Zero byte overhead follows from timestamp editing and says nothing
about live retransmission overhead. Browser/TCP feedback and cross-direction
causality are not simulated. Variation between seeds is not a confidence interval
for new websites or future collection dates. Only four dates are represented, with
small, unequal final-test class counts.

## Fresh controlled prediction

Create a fresh visit with the existing collection environment, then use its capture
and recorded proxy port in the analysis environment:

```
python -m peekaboo predict PATH_TO_CAPTURE --proxy-port RECORDED_PORT --model models/experiment-v1/baseline.joblib
```

Only load trusted locally generated joblib models. Outputs are choices among the
known 20 sites, not unknown-site detection; forest scores are not calibrated
confidence. The dashboard currently replays saved held-out captures and labels
that clearly. Fresh collection still runs through the collector/CLI.

Remaining submission work: review results, rehearse a genuinely fresh visit on the
demo machine, and complete the report and individual contribution statements.
Live Linux/VM shaping is a separate optional scope. Loopback results must not be
presented as measured Wi-Fi/ISP observation.
