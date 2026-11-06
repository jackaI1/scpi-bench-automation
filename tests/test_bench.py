import math

import pytest

from scpi_bench.bench import SimBench


def test_real_visa_resources_follow_supply_and_shutdown():
    with SimBench() as bench:
        assert 'SUPPLY' in bench.query('supply', '*IDN?')
        assert 'SCOPE' in bench.query('scope', '*IDN?')
        assert 'DMM' in bench.query('dmm', '*IDN?')
        bench.set_voltage(2.5)
        assert bench.query('supply', 'VOLT?') == '2.500000'
        assert bench.measure('dmm', 'MEAS:VOLT:DC?') == 0
        bench.output(True)
        assert bench.measure('dmm', 'MEAS:VOLT:DC?') == pytest.approx(2.505)
        assert bench.measure('scope', 'MEAS:VAMP?') == pytest.approx(2.45)
        bench.output(False)
        assert bench.measure('scope', 'MEAS:VAMP?') == 0
        assert bench.query('supply', 'OUTP?') == '0'


@pytest.mark.parametrize('value', [-0.1, 5.1, math.nan, math.inf])
def test_rejects_unsafe_supply_voltage(value):
    with SimBench() as bench:
        with pytest.raises(ValueError):
            bench.set_voltage(value)
        assert bench.query('supply', 'OUTP?') == '0'


def test_temperature_is_a_real_scpi_query_and_bad_command_is_visible():
    with SimBench() as bench:
        bench.set_temperature(72)
        assert bench.measure('dmm', 'MEAS:TEMP?') == 72
        assert bench.query('dmm', 'UNKNOWN?') == 'ERROR'
        assert any(event['command'] == 'MEAS:TEMP?' and event['response'] == '72.000000'
                   for event in bench.transcript)
