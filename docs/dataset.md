# Dataset collection

## Windows pilot launcher

From a normal PowerShell window in the repository, run:

```powershell
.\scripts\collect-pilot.ps1
```

This collects two visits to each of the first three sites, using 20-second windows
and 10-second pauses. It uses fresh profiles, not your personal Chrome profile.
Run `python scripts/dataset-status.py` afterward for counts. Startup errors stop
the session immediately. Do not disable Chrome's sandbox or certificate checks.

The first agent-run attempts failed before capture because Windows denied Chrome's
internal process communication. These failures remain in manifests for audit and
must not be counted toward the target dataset. Running the launcher in your normal
terminal lets us test collection in the intended desktop environment.

Run from the repository root with Selenium installed:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
$env:SE_CACHE_PATH = "$PWD/.cache/selenium"
.venv/Scripts/python.exe -m peekaboo collect --limit 3 --visits 1 --seconds 12 --pause 5
```

The default interface is Windows Npcap loopback. On Linux pass `--interface lo`.
Use `--driver PATH` if ChromeDriver cannot be located automatically. Chrome and
the driver must be compatible. The 20 entries in `configs/sites.csv` are candidate
sites, not a validated dataset. Collect a pilot before running full sessions.

## Observation scope

The browser uses a dedicated localhost HTTP CONNECT proxy. The proxy forwards
TLS unchanged and has no certificate or decryption key. QUIC is disabled, so this
experiment covers HTTPS over TCP. Capture filtering selects only the proxy's
temporary port and excludes other applications' network traffic. Chrome's own
background requests may remain, despite background networking being disabled.

**These are loopback TCP traces, not Internet wire traces.** Packet segmentation,
timing, proxy buffering, and loopback headers differ from a Wi-Fi observation.
Keep this capture method fixed across baseline and defense experiments. Record
the capture point in the final report and avoid generalizing directly to ISP
observation. Live netem shaping needs a separately validated observation setup.

Raw captures include plaintext CONNECT hostnames. Feature extraction must exclude
CONNECT exchanges, addresses, ports, hostnames, and payload contents. Use the
manifest's proxy port only to establish direction, never as a model feature.
Incoming means proxy to browser; outgoing means browser to proxy. Do not naively
use all loopback traffic or infer direction from localhost addresses alone.

## Outputs and acceptance

Each session has a unique directory with frozen settings, randomized visit order,
JSONL manifest, captures, capture logs, and page screenshots. Each visit launches
a fresh browser profile and disables the cache. Labels stay in the manifest,
while capture filenames use random visit IDs.

`candidate` means basic checks passed, not final human acceptance. Review page
screenshots for consent walls, error pages, bot challenges, and unexpected redirects.
`needs_review` and `failed` must not silently enter training. Failed attempts are
retained for audit; reruns are separate attempts. The fixed observation window
may end before a slow page completes. Navigation timings are retained for review.

Capture starts approximately one second before navigation. The fixed capture
window includes that lead-in and a short tail; normalize the analysis window
consistently during preprocessing. A `tls_frames` count is only a sanity check,
not the feature representation (TLS reassembly can span multiple TCP packets).

## Scaling plan

After validating the pilot, target 40 accepted visits per site across multiple
sessions. For example, run 5 visits per site in each of 8 sessions spread over
different times. Use distinct seeds and hold out later sessions. Keep derivatives
of a source trace in the same split. Do not treat sequential batches gathered
minutes apart as evidence of performance across days.

All generated captures, screenshots, manifests, and models stay ignored by Git.
