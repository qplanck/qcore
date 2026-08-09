# RFC 0006: Amazon Braket Pulse Adapter

- Status: **Accepted**
- Date: 2026-07-14
- Decision owner: QPlanck maintainer
- Depends on: RFC 0004 and RFC 0005

## Summary

The first provider pulse adapter is the separately distributed
`qplanck-braket` package. It lowers QCore pulse schedules to Amazon Braket pulse
sequences and submits calibrated circuits through one Braket quantum task. The
core `qplanck` distribution has no AWS dependency or credential handling.

The initial public hardware target is a currently advertised Rigetti pulse QPU,
selected by ARN and capability discovery rather than a hard-coded device enum.
Device retirement or replacement therefore produces a clear capability failure
instead of silently selecting another provider target.

## Capability snapshot

`BraketPulseSnapshot` captures the device ARN, ports, frames, clock periods,
supported functions/waveforms, validation constraints, and calibration identity.
Observational capture time is excluded from the semantic hash. A refresh with
unchanged capabilities retains identity.

`BraketChannelMap` explicitly binds each QCore channel to one predefined provider
frame and one unique port. Mapping is derived from provider qubit, direction, and
port-type metadata. Frame-name guessing, dynamic frame creation, heterogeneous
clock periods, and shared-port aliases are rejected.

## Supported lowering

- `Play`, `Delay`, `SetPhase`, `ShiftPhase`, `SetFrequency`, and
  `ShiftFrequency`.
- Constant and sampled waveforms.
- Gaussian waveforms with real amplitude, exact duration/sigma clock conversion,
  and `zero_at_edges=False`.
- Absolute QCore sample times become deterministic per-frame delays.

QCore `Acquire` is rejected because Braket `capture_v0` cannot preserve its
duration and memory-slot semantics. Initial execution binds a pulse program as a
custom gate calibration and uses ordinary terminal circuit measurement.

## Runtime and security

`BraketPulseBackend` accepts `CalibratedCircuit`, checks its target and pulse
snapshot hashes, refreshes the provider snapshot immediately before submission,
and returns a QCore `Job`. One call creates at most one provider task. There are
no blind retries; uncertain submission state is surfaced.

Authentication uses the ambient AWS SDK credential chain. Tokens, access keys,
account identifiers, result-bucket paths, and calibration payloads are excluded
or redacted from manifests and diagnostics. Provider job ARN/status/error codes
are retained.

Pull-request tests are offline and use schema-conforming synthetic fixtures and
AWS stubs. Read-only and paid live checks are manual, protected, and disabled by
default.

## Live evidence gate

The approved future proof is one ten-shot, QCore-lowered Gaussian custom
calibration task with an estimated cost no greater than USD 10. Preflight must
verify ambient identity, IAM, result storage, device ONLINE state, exact snapshot,
payload/shot limits, and the account spending limit. The task is never retried.

No AWS credentials are currently available, so a production provider-execution
claim and production `qplanck-braket` publication remain gated. Offline lowering
and packaging evidence must not be described as hardware execution.

## Deferred work

Arbitrary acquisition, raw capture, dynamic frames, runtime pulse parameters,
direct Rigetti QCS, IBM, lab-instrument control stacks, fidelity claims, and
cross-provider pulse portability are outside this RFC.
