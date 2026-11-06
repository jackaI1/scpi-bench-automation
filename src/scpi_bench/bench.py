"""All instrument reads and writes go through the actual PyVISA-sim backend.

SIM:* commands belong to our fixture model, not to a hardware driver.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
from importlib.resources import as_file, files
import math

import pyvisa


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f'{name} must be finite')
    return value


class SimBench:
    """Own a simulated supply, DMM and scope and their resource lifetimes.

    This class deliberately accepts no hardware backend. The deterministic
    fixture connects a unity-gain DUT with +0.2% DMM and -2% scope gain error.
    """

    def __init__(self):
        self.transcript = []
        self._stack = ExitStack()
        self.instruments = {}

    def __enter__(self):
        try:
            path = self._stack.enter_context(as_file(files('scpi_bench') / 'bench.yaml'))
            self.manager = pyvisa.ResourceManager(f'{path}@sim')
            self._stack.callback(self.manager.close)
            for name in ('supply', 'dmm', 'scope'):
                self.instruments[name] = self._stack.enter_context(
                    self.manager.open_resource(f'TCPIP::{name}::INSTR',
                                               read_termination='\n',
                                               write_termination='\n', timeout=500))
            self.output(False)
            self.set_voltage(0)
            self.set_temperature(25)
            return self
        except BaseException:
            self._stack.close()
            raise

    def __exit__(self, *exc):
        try:
            self.output(False)
        finally:
            self._stack.close()

    def write(self, instrument, command):
        self.instruments[instrument].write(command)
        self.transcript.append(dict(timestamp_utc=utc_now(), instrument=instrument,
                                    command=command, response=''))

    def query(self, instrument, command):
        try:
            response = self.instruments[instrument].query(command).strip()
        except Exception as error:
            self.transcript.append(dict(timestamp_utc=utc_now(), instrument=instrument,
                                        command=command, response=f'ERROR: {error}'))
            raise
        self.transcript.append(dict(timestamp_utc=utc_now(), instrument=instrument,
                                    command=command, response=response))
        return response

    def measure(self, instrument, command):
        return finite(self.query(instrument, command), 'measurement')

    def set_voltage(self, value):
        value = finite(value, 'voltage')
        if not 0 <= value <= 5:
            raise ValueError('voltage must be between 0 and 5 V')
        self.write('supply', f'VOLT {value:.6f}')
        self.sync_fixture()

    def output(self, enabled):
        self.write('supply', f'OUTP {int(enabled)}')
        self.sync_fixture()

    def sync_fixture(self):
        voltage = self.measure('supply', 'VOLT?')
        enabled = self.query('supply', 'OUTP?') == '1'
        actual = voltage if enabled else 0
        self.write('dmm', f'SIM:INPUT {actual * 1.002:.6f}')
        self.write('scope', f'SIM:INPUT {actual * 0.98:.6f}')

    def set_temperature(self, value):
        value = finite(value, 'temperature')
        self.write('dmm', f'SIM:TEMP {value:.6f}')
