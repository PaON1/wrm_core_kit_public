# WRM Core Kit

> A small, inspectable research kit for experimenting with trust, coherence, and changing state in distributed systems.

WRM stands for **Waveform Resonance Mechanics**. The project explores a simple idea: a distributed system can carry useful information not only in isolated states, but also in how its states change, recover, and relate over time.

This repository is intentionally small. It is **not** the full WRM research system. It is a public seed layer that other people can inspect, challenge, run, and extend.

## What is here

```text
scripts/
  trust_pulse_emitter.py   emit structured trust-pulse events
  coherence_snapshot.py   summarize coherence from recent pulse history
  wrm_system_audit.py     inspect node reachability and expected logs
  core_kit_preflight.sh   run a repeatable local preflight

config/
  core_kit.env.example    optional local configuration

WRM_LEXICON.md            vocabulary
WRM_MATH_MICROPACK.md     compact math notes
WRM_PHILOSOPHER_LENS.md   philosophical framing
WRM_VOICE_POLICY.md       communication/design intent
```

## Quick start

```bash
git clone https://github.com/PaON1/wrm_core_kit_public.git
cd wrm_core_kit_public
chmod +x scripts/core_kit_preflight.sh
./scripts/core_kit_preflight.sh
```

If the local environment is configured correctly, the preflight emits pulses, builds a coherence snapshot, and runs a fast audit.

## Configuration

Optional configuration lives in `config/core_kit.env`. Start from the example:

```bash
cp config/core_kit.env.example config/core_kit.env
```

If a local config file is not present, the kit uses safe local defaults where possible.

## What this demonstrates

- structured event emission
- log-based state modeling
- recent-history / tail-based coherence calculations
- distributed node introspection
- deterministic, inspectable system plumbing
- local-first experimentation without an opaque cloud dependency

## What this does **not** claim

This is a research prototype, not a finished enterprise platform, safety controller, trading engine, or autonomous governance system. The public kit exists so the underlying abstractions can be examined on their own merits.

## Where it can go

The same basic pattern can be explored with:

- robotics
- HVAC and thermal systems
- cyber telemetry
- grid or energy signals
- traffic and flow systems
- local AI agents
- sensor networks
- educational simulations

Replace the pulse schema, attach real sensor streams, change the coherence function, or feed the event history into a learning pipeline. The kit stays small so the experiment stays legible.

## Research posture

Traditional software often reacts to an event in isolation. WRM asks whether a system can become more useful by also reasoning about **trajectory, context, trust, recovery, and the interval before action**.

The working principles are:

- listen before acting
- preserve evidence
- treat uncertainty as information
- make recovery visible
- keep human judgment available
- prefer inspectable mechanisms over unexplained automation

## Related work

- [Playable Doodles](https://github.com/PaON1/playable-doodles) — a very different domain using the same interest in relationships, continuous variation, and human interaction
- [Freezer Starter](https://github.com/PaON1/freezer-starter) — offline-first mesh presence and drift demo
- [Raymond Bryant / project index](https://github.com/PaON1)
