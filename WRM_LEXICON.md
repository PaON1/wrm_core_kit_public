# WRM Lexicon — Definitions + Invariants

## WRM (Waveform Resonance Mechanics)
WRM is a system that treats trust, drift, and behavior as measurable, narratable signals over time.
It produces snapshots that can be inspected by humans and narrated by a voice model.

### Invariants (WRM must always preserve these)
1) **State is visible**: trust, drift, posture are observable.
2) **Memory is explicit**: snapshots reference the events that shaped them.
3) **Action is consent-based**: higher risk posture means tighter gates.
4) **Narration is grounded**: narration must match the snapshot; no freelancing.
5) **Local-first reliability**: logs exist even if networks fail.

## Event (canonical)
A structured record written to logs/events.jsonl.
Minimum: timestamp, type, id, node, payload.

## Snapshot
A compact summary of current state (trust, drift, posture, explanation).
Source of truth for voice narration.
Primary file: logs/latest_snapshot.json

## Trust
A 0–1 score representing system coherence and confidence in current conditions.
High trust does not mean “correct,” it means “stable enough to proceed safely.”

## Drift
A 0–1 signal representing deviation, instability, or disturbance.
Drift can be physical (voltage/frequency) or behavioral (errors, retries, anomalies).

## Posture
A discrete safety mode derived from trust + drift + recurrence:
- Calm: normal flow
- Elevated: reversible steps, careful changes
- High: slow down, verify, consent gates, reduce automation

## Glyph
A symbolic marker of meaning (chapter marker, threshold, alignment check).
Used to make memory human-legible.

## Trust Arc
A time curve of trust over time.

## Spiral Memory
A visualization that emphasizes recency + recurrence, not just linear logs.
