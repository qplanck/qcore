# qplanck-braket

`qplanck-braket` is QPlanck's separately versioned Amazon Braket adapter. It
lowers validated QPlanck pulse schedules to Braket `PulseSequence` objects and
wraps one Amazon Braket quantum task behind QPlanck's backend and job contracts.

The adapter is intentionally explicit:

- channel mappings refer only to predefined frames advertised by a captured
  device capability snapshot;
- the QPlanck sample period must match every mapped Braket port;
- `Acquire` is rejected because Braket `capture_v0` cannot preserve QPlanck's
  acquisition duration and memory-slot contract;
- submission refreshes device capabilities and refuses stale compiled or pulse
  snapshots;
- credentials come only from the normal AWS SDK credential chain and are never
  accepted by QPlanck artifact objects;
- persisted results, manifests, preflights, and live-smoke evidence use redacted
  device/task identities and omit reservation and S3 destination values. The
  in-memory `BraketJob.id` remains the provider ARN for active job operations;
  `BraketJob.artifact_id` is the persistable form.

The package does not make a hardware-fidelity claim. Live QPU validation is a
manual, protected, budget-capped release gate.

The repository publication workflow is intentionally TestPyPI-only during this
phase. A production PyPI upload path is not present until the protected live
execution gate is satisfied and separately approved.

## Install

```bash
python -m pip install qplanck-braket==0.1.0a1
```

Python 3.11 through 3.13 and `amazon-braket-sdk>=1.124,<1.125` are supported by
this alpha.

## Offline lowering

```python
from qplanck.pulse import DriveChannel, GaussianWaveform, PulseProgram
from qplanck_braket import BraketChannelMap, BraketPulseDevice, lower_pulse_program

# `aws_device` is an already-created braket.aws.AwsDevice. Constructing it may
# access AWS; qplanck-braket never accepts credentials itself. Skip the native
# calibration download when the goal is local lowering only.
device = BraketPulseDevice.from_aws_device(
    aws_device,
    refresh_calibrations=False,
)
frame = next(
    frame
    for frame in device.snapshot.frames
    if len(frame.qubits) == 1
    and device.snapshot.port_by_id[frame.port_id].direction == "tx"
)
channel_map = BraketChannelMap.from_mapping(
    {DriveChannel(0): frame.frame_id},
    snapshot=device.snapshot,
)
program = PulseProgram().play(
    0,
    DriveChannel(0),
    GaussianWaveform(duration=40, sigma=10.0, amplitude=0.2),
)
sequence = lower_pulse_program(
    program,
    channel_map=channel_map,
    snapshot=device.snapshot,
    frames=device.frames,
)
print(sequence.to_ir())
```

This example performs only local lowering after the `AwsDevice` has loaded its
capabilities. It does not submit a quantum task. Hardware submission uses
`BraketPulseBackend` with a `CalibratedCircuit`; the backend refreshes device and
native-calibration identities immediately before creating exactly one task.

## Protected live smoke

The repository's manual `Protected Braket pulse smoke` workflow is default-deny.
Before enabling it, configure a reviewer-protected `braket-live` GitHub
environment with:

- `AWS_BRAKET_ROLE_ARN`, an OIDC-assumable least-privilege role;
- `BRAKET_RESULTS_S3_URI`, an existing `s3://bucket/non-empty-prefix` environment
  variable;
- one active, per-device Amazon Braket spending limit of at most USD 10.

The workflow requires an exact confirmation phrase, accepts only the current
Rigetti Cepheus ARN in `us-west-1`, fixes the workload at 10 shots, performs IAM,
device, spending-limit, target, calibration-snapshot, timing, and payload
preflights, and calls the non-retrying submission path once. Its evidence is an
execution smoke only, never a hardware-fidelity claim.
