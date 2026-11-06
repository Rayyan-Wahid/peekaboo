# Peekaboo

**HTTPS Website Fingerprinting and Traffic Privacy Defense**

Information Security course project: identify a visited website from packet sizes,
directions, and timing, then evaluate a timing-jitter defense.

## Current status

Collection is complete: 803 accepted captures across 20 sites. The project now
implements metadata extraction, fixed date splits, a Random Forest baseline,
bounded timing-jitter simulation, adaptive-classifier comparison, and a local
Streamlit results/replay dashboard. See [analysis and run instructions](docs/analysis.md).
Results are generated locally; no accuracy or privacy level is assumed in advance.

On this Windows workspace, all new tooling, caches, and outputs stay on D:.
From `D:\Peekaboo\peekaboo`, run:

```powershell
.\scripts\setup-analysis.ps1
.\scripts\run-analysis.ps1 -Stage all -RunName experiment-v1
.\scripts\start-dashboard.ps1
```

The existing `.venv` remains the collection environment. `.venv-research` holds
the analysis dependencies. Keep raw data out of Git; source code and experiment
configuration are versioned separately. Existing run names cannot be overwritten;
use a new name for an intentional repeat and preserve earlier results.

## Setup

Python 3.11+ is required. From the repository directory:

```sh
python -m venv .venv
```

Activate on Windows PowerShell with `.venv\Scripts\Activate.ps1`, or on Linux
with `source .venv/bin/activate`. Then:

```sh
python -m pip install -e .
peekaboo --version
peekaboo doctor
```

When implementing the research pipeline, install its optional dependencies:

```sh
python -m pip install -e ".[research]"
```

Traffic capture requires tshark and a supported browser/driver. Live jitter would
use Linux traffic control; the implemented defense is an explicitly labeled offline
simulation. `configs/analysis.toml` controls the analysis pipeline;
`configs/experiment.toml` contains the older collection plan.

## Research scope

- Approximately 20 known public pages, 40 successful baseline visits each.
- Random Forest using traffic metadata; exclude IP addresses, DNS, TLS names,
  payloads, and identifying filenames from model features.
- Separate collection sessions into training, validation, and test sets.
- Evaluate both the original classifier and one retrained on defended data.
- Report accuracy, macro F1, confusion matrix, bandwidth overhead, and delay.
- Clearly distinguish trace simulation from measured live-network results.

Collect only team-generated traffic on controlled devices, with paced visits
and no personal logins. Packet captures and generated models are ignored by Git.

## Layout

```text
configs/         Experiment settings and site manifest
src/peekaboo/    Python package and CLI
data/raw/        Local packet captures (ignored)
data/processed/  Local feature datasets (ignored)
models/         Local trained models (ignored)
reports/        Local experiment outputs (ignored)
docs/           Proposal, architecture, and experiment protocol
```

See [architecture](docs/architecture.md), [experiment protocol](docs/experiment-protocol.md),
and [project proposal](docs/Peekaboo_Proposal.docx).

## Implementation milestones

1. Browser automation, capture boundaries, session metadata, and failure logging.
2. Metadata feature extraction and session-based dataset splitting.
3. Random Forest baseline and reproducible metrics.
4. Timing jitter and adaptive-classifier comparison.
5. Dashboard, security analysis, run instructions, and class demonstration.
