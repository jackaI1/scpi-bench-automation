I merged this into my existing [lab-assay-lims project](https://github.com/jackaI1/lab-assay-lims/tree/main/projects/scpi-bench-automation). The current code is in `projects/scpi-bench-automation/` there. I kept the code here so older links still work.

The move keeps the original layout, including `tests/test_bench.py`, `tests/test_transport.py`, `tests/test_runner.py`, `src/scpi_bench/runner.py`. I replaced the README with the report below and left out Git history, installed dependencies, caches and generated build output from the hub copy.

The 3 files of test code and supporting test helpers moved with the code. No project-specific GitHub Actions workflow was retained; the report records the omitted checks, and the test sources can be run locally from the linked folder.

Omitted workflows: `scpi-bench-automation-ci.yml`: The relocated workflow did not complete successfully within the migration batch. Local test sources remain available.

---

# scpi-bench-automation

I built a simulated test bench to learn how the underlying idea works. This is a learning project.

## Try a measurement run

I use Python 3.11 or newer. No instrument drivers or equipment are needed.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[dev]'
scpi-bench sweep --voltages 0 2.5 5
```

The command prints the path to `report.html`. Open that file in a browser. The default limit is 0.11 V from the requested voltage for both voltage readings. This example passes:

| Supply setting | Multimeter reading | Scope amplitude |
| --- | --- | --- |
| 0 V | 0 V | 0 V |
| 2.5 V | 2.505 V | 2.45 V |
| 5 V | 5.01 V | 4.9 V |

I can tighten the limit to make a failed run, or leave time for each voltage to settle:

```sh
scpi-bench sweep --voltages 1 2 3 --tolerance 0.01 --settle 0.1
```

A failed limit returns exit code 1, so another script can detect it. A completed passing run returns 0; a configuration or instrument error returns 2. Ctrl-C returns 130 and requests shutdown.

## Watch a temperature profile

A thermal soak means holding a powered device while checking its temperature over time. Here I supply a simulated temperature profile, in degrees Celsius:

```sh
scpi-bench soak --temperatures 25 40 61 30 --low 20 --high 60 --interval 1
```

This records 25, 40 and 61, then stops before 30. The supply turns off on the trip. The two limits are inclusive, so exactly 20 or 60 passes. For a passing run, try `scpi-bench soak --temperatures 25 30 35`.

## What I save

Every run gets its own UTC-timestamped folder inside `reports/`. Use `--output <folder>` to change the parent folder.

- `measurements.csv`: time, elapsed seconds, readings and each sample's pass/fail result.
- `report.html`: a self-contained summary with a measurement table.
- `run.json`: limits, instrument identities, overall result and shutdown confirmation.
- `scpi.csv`: the commands sent to each instrument and their replies.

Completed samples are written as they arrive. Instrument errors preserve the partial report. The supply is switched off when a run passes, fails, encounters an error or is interrupted.

## Use Tcl or Perl

SCPI is a set of text commands used to control instruments. Python sends them through PyVISA, an instrument communication library, using its `pyvisa-sim` simulation backend. My local TCP server bridges the same commands to those simulators, so I can also use small Tcl and Perl scripts.

Start the supply server in one terminal:

```sh
scpi-bench serve --instrument supply --port 5025
```

In another terminal, run either wrapper:

```sh
tclsh wrappers/scpi.tcl 127.0.0.1 5025 '*IDN?' 'VOLT 2.5' 'OUTP ON' 'VOLT?' 'OUTP OFF'
perl wrappers/scpi.pl 127.0.0.1 5025 '*IDN?' 'VOLT 2.5' 'OUTP ON' 'VOLT?' 'OUTP OFF'
```

Both print the instrument identity and `2.500000`. I use `--instrument dmm` with `MEAS:TEMP?`, or `--instrument scope` with `MEAS:FREQ?`, to try the other instruments. Each server exposes one instrument. Stop it with Ctrl-C; it closes the socket and turns the supply off. Tcl and Perl are included on my Mac; on Ubuntu I install them with `sudo apt-get install tcl perl`.

## How I model the bench

The supply sets the amplitude of a simulated 1 kHz signal. I gave the multimeter a +0.2% gain error and the scope a -2% gain error so the limits have something to catch. Python updates the simulated connections when the voltage or output state changes; measurements still travel through actual PyVISA queries. Turning the supply off makes both voltage readings zero.

This is a repeatable software fixture, not a model of real circuit or thermal physics. I have not validated these commands on physical instruments. The runner deliberately accepts only the simulator backend. I explain the model, supported commands, failure handling and hardware adaptation in [the bench notes](docs/bench.md).

## Tests and limits

There are 3 test source files in this copy. That source count does not establish an execution result. This is a source snapshot, and running it on a new machine may need environment-specific setup.



The relocated workflow did not complete successfully within the migration batch. Local test sources remain available.

No project-specific GitHub Actions workflow was retained. The local test sources remain in this folder.
