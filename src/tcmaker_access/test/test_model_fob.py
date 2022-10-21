import pytest
from models import Fob

@pytest.fixture
def sample_record():
    return  {      "url": "https://members.tcmaker.org/api/v1/keyfobs/66666666-1212-2323-3434-444444444444/",
                    "is_membership_valid": True,
                    "membership_valid_through": "2023-04-11T20:52:24-05:00",
                    "created_at": "2022-04-14T08:42:56.229774-05:00",
                    "updated_at": "2022-04-14T08:42:56.229792-05:00",
                    "code": "8675309",
                    "access_level": 1,
                    "is_active": False,
                    "person": "https://members.tcmaker.org/api/v1/persons/cccccccc-6565-5454-2345-555555555555/"
                }

def test_parsing_record(sample_record):
    f = Fob(sample_record)
    assert f.user == 'cccccccc-6565-5454-2345-555555555555'
    assert f.esp_access() == 0

def test_invalid_expiration():
    f = Fob({'url': 'https://members.tcmaker.org/api/v1/keyfobs/11111111-aaaa-dddd-ffff-d0176edfc013/',
     'is_membership_valid': False, 'membership_valid_through': None, 'created_at': '2021-09-20T22:08:38.970711-05:00',
     'updated_at': '2021-09-20T22:08:38.970734-05:00', 'code': '132435', 'access_level': 1, 'is_active': True,
     'person': 'https://members.tcmaker.org/api/v1/persons/22222222-bbbb-cccc-dddd-555555555555/'})
    assert f.expiration_timestamp() == 0
