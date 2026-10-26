# Experiment protocol

- Populate `configs/sites.csv` with stable IDs and 20 public page URLs.
- Use a dedicated browser profile and keep cache policy consistent.
- Randomize visits across multiple sessions, pacing requests and logging failures.
- Assign entire sessions to train/validation/test; preserve each visit intact.
- Keep simulated derivatives in the same split as their original traces.
- Never use destination addresses, DNS names, TLS names, filenames, or payloads
  as classifier inputs.
- Report accuracy, macro F1, per-site results, and a confusion matrix; random
  guessing is 5% for a balanced 20-class experiment.
- Test defenses against both the original and a retrained classifier.
- Report bandwidth overhead as `(defended_bytes - baseline_bytes) / baseline_bytes`
  times 100, using comparable repeated visits and the same observation layer.
- Measure page-load delay for live experiments. Label simulated timing estimates
  separately; timestamp edits do not model TCP/browser feedback.
- Record seeds, package versions, capture settings, session splits, and failures.

## Final submission checklist

- Source code and reproducible run instructions.
- Architecture documentation and configuration details.
- Security analysis including results, limitations, and lessons.
- Contribution statement for each member if working as a group.
