# Bench model and command reference

I split this project into the instrument boundary (`bench.py`), sequences (`runner.py`), evidence (`report.py`) and a local TCP bridge (`server.py`). The command-line entry point is `cli.py`; the simulated instruments are defined in `bench.yaml` and included in the installed package.

## Where the measurements come from

`SimBench` opens three TCPIP-style VISA resources with an explicit `<packaged YAML>@sim` backend. These resource names are logical simulator addresses, not network connections. No real instrument or NI-VISA installation is used. The TCP server is a separate loopback socket that forwards requests to these resources.

PyVISA-sim stores instrument properties but does not connect separate devices. My fixture model handles that connection explicitly: it reads `VOLT?` and `OUTP?` from the supply, calculates DMM input as voltage × 1.002 and scope amplitude as voltage × 0.98, then updates the simulated input properties with `SIM:INPUT`. Output off sets both inputs to zero. The scope frequency is fixed at 1000 Hz, even with no amplitude. Its measurement represents signal amplitude, not a DC voltage channel measurement.

Temperature points come from `--temperatures`. Each point is injected with `SIM:TEMP`, then read back with `MEAS:TEMP?`. `--interval` is the delay between samples; the first sample is immediate. `--settle` delays each sweep reading after a voltage change. Defaults are zero to keep automated runs fast. These are deterministic profiles and gain errors, without noise, thermal inertia, waveform capture or physical circuit simulation.

## Commands

The Python sequences use these same SCPI commands as the TCP bridge. Case is normalized by the bridge. Each connection targets the instrument chosen when its server started.

| Instrument | Commands |
| --- | --- |
| All three | `*IDN?`, `*OPC?` |
| Supply | `VOLT <0..5>`, `VOLT?`, `OUTP ON`, `OUTP OFF`, `OUTP 1`, `OUTP 0`, `OUTP?` |
| Multimeter | `MEAS:VOLT:DC?`, `MEAS:TEMP?` |
| Scope | `MEAS:VAMP?`, `MEAS:FREQ?` |

`*OPC?` asks whether the previous operation completed and returns `1`. Both wrappers send it after a write, so a bad value cannot silently succeed. They print only replies to the user's queries and exit nonzero on error, connection failure or a two-second timeout. The server sends `ERROR: ...` on unsupported commands and values. Successful writes have no reply; queries return one ASCII line. Commands are newline-terminated, at most 4095 characters, without semicolon batching or binary transfers.

`SIM:INPUT` and `SIM:TEMP` are private fixture commands. They are recorded in the Python transcript but intentionally unavailable through the TCP bridge. They are not portable hardware commands.

The server accepts one client at a time, uses a one-second idle socket timeout, and listens only on `127.0.0.1`. Each server owns a complete bench, so separate server processes do not share state. A DMM or scope server starts with zero voltage input and 25 C temperature. Run the Python sweep to exercise the connected three-instrument model. I do not run multiple `SimBench` contexts concurrently because PyVISA caches resource managers by backend path.

## Limits and failure behaviour

A sweep checks both `abs(DMM - setpoint) <= tolerance` and `abs(scope - setpoint) <= tolerance`, in volts. Frequency is recorded as a diagnostic. It collects the full sweep even if a limit fails. A soak checks `low <= temperature <= high` and stops immediately at its first failed sample. Invalid settings are rejected before the output is enabled or a report folder is created. Voltage must be finite and between 0 and 5 V. Limits, delays and profile values must be finite; delays and voltage tolerance must be nonnegative. Profiles contain between 1 and 10,000 samples.

The runner uses `finally` to disable output, verifies it with `OUTP?`, and records the result in `run.json`. A communication failure becomes `ERROR`, retains completed rows and includes the error in the report. An interruption also finalizes partial evidence before propagating to the CLI. Process termination with SIGKILL or a power failure cannot run Python cleanup. CSV samples are closed after each write; I do not claim durability against disk failure.

Unique timestamped folders prevent one run overwriting another. Reports contain instrument IDs, the simulator backend, settings, UTC timestamps, elapsed time and a per-run SCPI transcript. CSV files contain numeric measurements and status, and HTML text is escaped. Reports are ignored by git. The simulator identities are fictional, and there are no credentials.

## Resource ownership

The TCP server prints its owner, PID, process start time, exact port and cleanup method on startup. Keep it in the foreground and stop it with Ctrl-C. The context manager shuts down its serving thread and closes its listener. Tests own their listeners and silent timeout peers within context managers, interrupt active client sockets, join every serving thread and check that instrument ports reject connections after cleanup. They launch no detached fixture processes or browser pages. Tcl and Perl subprocesses have an outer test timeout.

## Adapting to a physical bench

I would first check each instrument's programming manual, resource address, termination characters, safe voltage/current limits and shutdown behaviour. A separate hardware bench implementation would expose the same sequence methods while removing `SIM:*` writes entirely. It would need real wiring, current limiting, settling characterization and independent hardware protection before use. Changing just the VISA backend is insufficient for this model.

I used the official [PyVISA resource documentation](https://pyvisa.readthedocs.io/en/stable/introduction/resources.html) for terminations and timeouts and the [PyVISA-sim definition guide](https://pyvisa.readthedocs.io/projects/pyvisa-sim/en/latest/definitions.html) for YAML properties and resource mappings.
