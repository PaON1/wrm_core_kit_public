# WRM Math Micro-Pack (minimal)

This is the small set of math WRM actually uses in the podcast MVP.

## 1) Normalization (clamp)
Keep signals bounded.
x_clamped = min(1, max(0, x))

## 2) Drift from deviations (example)
If df = frequency deviation, dv = voltage deviation:
drift = clamp01( 0.55 * min(1, |dv|/0.25) + 0.55 * min(1, |df|/0.35) )

## 3) Drift recurrence
Given a rolling window of drift values d[i]:
recurrence = count(d[i] >= threshold) / N

## 4) Trust update (simple local-first model)
trust_new = clamp01( trust_prev - (0.55*drift_now + 0.25*recurrence) + recover )
recover = 0.010 if drift_now < 0.06 else 0

## 5) Posture classification
If trust <= 0.35 OR drift >= 0.35 OR recurrence >= 0.45 → High
Else if trust <= 0.60 OR drift >= 0.16 OR recurrence >= 0.20 → Elevated
Else → Calm

## 6) Audio length heuristic (voice control)
Target narration length ≈ 80–95 words for ~25–35 seconds spoken (varies by voice).
