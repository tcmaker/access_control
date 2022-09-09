import random
import string

import pytest
from config import Configuration, ConfigurationException
from door_hardware_service import process_args
from .mock_reader_board import MockReaderBoard

def test_default_locations(sample_config_a, sample_config_b, tmp_path):
    # config b should be used
    c1 = Configuration(process_args([]), defaultlocation=[sample_config_b,sample_config_a], skip_key_compute=True)
    assert c1.name in sample_config_b

    # missing file
    output = tmp_path / "doesntexist.yaml"
    c2 = Configuration(process_args([]), defaultlocation=[str(output), sample_config_a], skip_key_compute=True)
    assert c2.name in sample_config_a


def test_parameter_priority_default(sample_config_a, sample_config_b):
    #default location
    c1 = Configuration(process_args([]),defaultlocation=[sample_config_a], skip_key_compute=True)
    assert c1.name in sample_config_a

    #cli over that
    c2 = Configuration(process_args(['-c',sample_config_b]),defaultlocation=[sample_config_a], skip_key_compute=True)
    assert c2.name in sample_config_b

    # then kwargs
    c2 = Configuration(process_args(['-c', sample_config_b]), defaultlocation=[sample_config_a], name="awesome", skip_key_compute=True)
    assert c2.name == "awesome"

def test_protocol_enforcement():
    c1 = Configuration(listen='tcp://0.0.0.0:6000' , skip_key_compute=True)
    c2 = Configuration(listen='unix:///tmp/socket' , skip_key_compute=True)
    with pytest.raises(ConfigurationException):
        c3 = Configuration(listen='nottcporunix://0.0.0.0:6000', skip_key_compute=True)

def test_tcp_enforce_valid_hostport():
    c1 = Configuration(listen='tcp://0.0.0.0:6000', skip_key_compute=True)
    with pytest.raises(ConfigurationException):
        c2 = Configuration(listen='tcp://0.0.0.0:asdf')
    # Validating hostnames is too much of a pain

# def test_scanner_mapping(sample_config_a):
#     rb = MockReaderBoard("rb1",model="Mock",version="1.0",numScanners=2,numRelays=2)
#     devices = {rb.device_id: rb}
#     c = Configuration(scanners={'firstone' : {'board' : 'rb1','scanner':1},
#                                 'secondone': {'board': 'rb1', 'scanner': 2}},defaultlocation=[sample_config_a])
#     c.map_names(devices)
#     assert rb.scanner_names[0] == 'firstone'
#     assert rb.scanner_names[1] == 'secondone'
#
#     assert c.get_scanner('rb1',2) == 'secondone'
#
# def test_relay_mapping(sample_config_a):
#     rb = MockReaderBoard("rb1",model="Mock",version="1.0",numScanners=2,numRelays=2)
#     devices = {rb.device_id: rb}
#     c = Configuration(relays={'firstone' : {'board' : 'rb1','relay':1},
#                                 'secondone': {'board': 'rb1', 'relay': 2}},defaultlocation=[sample_config_a])
#     c.map_names(devices)
#     assert rb.relay_names[0] == 'firstone'
#     assert rb.relay_names[1] == 'secondone'
#
#     assert c.get_relay('firstone') == ('rb1', 1)

def test_key_loading(sample_key):
    c = Configuration(defaultkey=sample_key, skip_key_compute=True)
    assert c.key == 'SKIPPED' #b'sKOzHAg8IsKW+klCTti4wIAOwGTGovy0ceo9pFAvekc='

    c1 = Configuration(process_args(['-k',sample_key]),skip_key_compute=True)
    assert c1.key == 'SKIPPED' # b'sKOzHAg8IsKW+klCTti4wIAOwGTGovy0ceo9pFAvekc='

def test_missing_key(tmp_path):
    output = str((tmp_path / "boguskey").absolute())
    with pytest.raises(ConfigurationException,match='missing'):
        c1 = Configuration(process_args(['-k', output]))

def test_empty_key(tmp_path):
    output = tmp_path / "emptykey"
    output.write_text("")
    with pytest.raises(ConfigurationException,match='empty'):
        c1 = Configuration(process_args(['-k', str(output.absolute())]))

def test_enforces_aliases(tmp_path):
    c0 = Configuration(devices={'azAZ09_':'aserial'})
    with pytest.raises(ConfigurationException,match='alias'):
        c1 = Configuration(devices={'asd$f':'aserial'})

def test_alias_must_start_with_letter():
    c0 = Configuration(devices={'azAZ09_': 'aserial'})
    with pytest.raises(ConfigurationException, match='alias'):
        c1 = Configuration(devices={'1asdf4': 'aserial'})
    with pytest.raises(ConfigurationException, match='alias'):
        c1 = Configuration(devices={'_2asd_fs': 'aserial'})


@pytest.fixture
def sample_config_a(tmp_path,sample_key):
    return sample_config(tmp_path,sample_key)

@pytest.fixture
def sample_config_b(tmp_path,sample_key):
    return sample_config(tmp_path,sample_key)

@pytest.fixture()
def sample_key(tmp_path):
    output = tmp_path / ".testkey"
    output.write_text("asdf")
    return str(output.absolute())

def sample_config(tmp_path, key):
    file_prefix = "".join([random.choice(string.ascii_letters) for n in range(8)])
    board_id = "board_" + "".join([random.choice(string.ascii_letters) for n in range(4)])
    output = tmp_path / f"{file_prefix}.yaml"
    output.write_text(
f"""
hardware_service:
  name: {file_prefix}
  key: {key}  
  listen: unix:///tmp/hardware_service

  # remote authorization and coordination server
  auth: https://authserver.com
  devices:        
    anotherboard: "{board_id}"
""")
    return str(output.absolute())
