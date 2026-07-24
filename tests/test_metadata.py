import base64
import threading

from coldth.metadata import (
    MetadataItem,
    MetadataTracker,
    ShairportMetadataAdapter,
    parse_metadata_item,
)


def xml_item(kind: str, code: str, data: bytes = b"") -> bytes:
    encoded = base64.b64encode(data).decode()
    return (
        f"<item><type>{kind.encode().hex()}</type><code>{code.encode().hex()}</code>"
        f"<length>{len(data)}</length><data encoding=\"base64\">{encoded}</data>"
        "</item>"
    ).encode()


def test_parse_shairport_metadata_item():
    item = parse_metadata_item(xml_item("core", "minm", "Once in a Lifetime".encode()))

    assert item == MetadataItem("core", "minm", b"Once in a Lifetime")


def test_tracker_commits_metadata_sequence_as_one_update():
    tracker = MetadataTracker(lambda: False)

    assert tracker.consume(MetadataItem("ssnc", "mdst", b"")) == []
    assert tracker.consume(MetadataItem("core", "minm", b"This Must Be the Place")) == []
    assert tracker.consume(MetadataItem("core", "asar", b"Talking Heads")) == []
    events = tracker.consume(MetadataItem("ssnc", "mden", b""))

    assert events == [
        (
            "metadata.changed",
            {
                "artist": "Talking Heads",
                "album": None,
                "title": "This Must Be the Place",
                "artwork": None,
                "codec": None,
                "bitrate": None,
            },
        )
    ]


def test_tracker_discards_artwork_unless_enabled():
    enabled = False
    tracker = MetadataTracker(lambda: enabled)
    picture = b"\x89PNG\r\n\x1a\nimage"

    assert tracker.consume(MetadataItem("ssnc", "PICT", picture)) == []
    assert tracker.artwork() is None

    enabled = True
    events = tracker.consume(MetadataItem("ssnc", "PICT", picture))

    assert events[0][0] == "metadata.changed"
    assert events[0][1]["artwork"] == "/api/v1/artwork/current"
    assert tracker.artwork() == (picture, "image/png")


def test_tracker_reports_playback_state():
    tracker = MetadataTracker(lambda: False)

    playing = tracker.consume(MetadataItem("ssnc", "pbeg", b""))
    stopped = tracker.consume(MetadataItem("ssnc", "pend", b""))

    assert playing[0][1]["state"] == "playing"
    assert stopped[0][1]["state"] == "stopped"


def test_adapter_reads_consecutive_xml_records(tmp_path):
    source = tmp_path / "metadata"
    source.write_bytes(
        xml_item("ssnc", "mdst")
        + xml_item("core", "minm", b"Road to Nowhere")
        + xml_item("ssnc", "mden")
    )
    received = []
    ready = threading.Event()
    tracker = MetadataTracker(lambda: False)

    def callback(event_type, data):
        received.append((event_type, data))
        ready.set()

    adapter = ShairportMetadataAdapter(
        str(source), tracker, callback, lambda: True
    )
    adapter.start()
    try:
        assert ready.wait(1)
    finally:
        adapter.stop()

    assert received[0][0] == "metadata.changed"
    assert received[0][1]["title"] == "Road to Nowhere"
