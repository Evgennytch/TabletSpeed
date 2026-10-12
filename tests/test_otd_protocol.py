import struct
import pytest
from tabletspeed.sources import parse_otd_message, OTDProtocolError, TabletSource, build_otd_hello

def test_parse_otd_state_coordinates():
    header=struct.pack("<III",2,41,7)
    payload=struct.pack("<Iff",3,12.5,30.25)+bytes(17)
    typ,point=parse_otd_message(header,payload)
    assert typ==2 and point["tablet_id"]==7
    assert point["x"]==12.5 and point["y"]==30.25

def test_otd_state_requires_valid_position_bits():
    typ,point=parse_otd_message(struct.pack("<III",2,41,1),struct.pack("<Iff",1,1,2)+bytes(17))
    assert typ==2 and point is None

def test_otd_bad_frame_is_rejected():
    with pytest.raises(OTDProtocolError): parse_otd_message(struct.pack("<III",2,100,0),bytes(20))



def test_otd_discovery_reads_default_and_metadata(tmp_path):
    root=tmp_path/"otd-ipc"/"servers"/"v2"
    (root/"available").mkdir(parents=True)
    (root/"default.txt").write_text("sample.driver\n",encoding="utf-8")
    sock=tmp_path/"otd.sock"
    (root/"available"/"sample.driver.txt").write_text(f"ID=sample.driver\nSOCKET={sock}\n",encoding="utf-8")
    assert TabletSource.discover_socket(tmp_path)==sock


def test_otd_hello_frame_layout():
    hello=build_otd_hello()
    assert len(hello)==800
    assert struct.unpack_from("<III",hello)==(6,800,0)
