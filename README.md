# SCPI bench automation

I built a simulated test bench because I needed a way to repeat measurements without having lab equipment connected. I can step through supply voltages, collect readings from an oscilloscope and a multimeter, and check whether they stay within a limit. Each run saves a dated spreadsheet-friendly file and a report I can open in a browser.

The instruments are software simulations. The scope measures a signal's amplitude and frequency; the multimeter measures voltage and temperature. I also added a temperature run that stops at the first reading outside its allowed range and switches the supply off.

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

## Tests and CI

```sh
python -m pytest
python -m build
```

The suite currently has 46 tests, including actual Tcl and Perl processes, all three TCP instrument endpoints, a real PyVISA timeout, thermal trips, invalid settings and closed-port checks. GitHub Actions runs the suite on Python 3.11, 3.12 and 3.13, installs the package, builds it, runs both sequences and uploads example reports. [CI runs](https://github.com/jackaI1/scpi-bench-automation/actions/workflows/ci.yml)
