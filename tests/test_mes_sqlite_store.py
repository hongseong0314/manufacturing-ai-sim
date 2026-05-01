from src.mes.domain import Event
from src.mes.sqlite_store import SQLiteMESStore


def test_sqlite_store_reloads_persisted_events(tmp_path):
    db_path = tmp_path / "mes.sqlite3"
    store = SQLiteMESStore(db_path)
    store.add_event(
        Event(
            event_id="EVT_TEST",
            event_type="COMMAND_EXECUTED",
            correlation_id="CORR_TEST",
        )
    )

    reloaded = SQLiteMESStore(db_path)
    events = reloaded.events("CORR_TEST")

    assert len(events) == 1
    assert events[0].event_id == "EVT_TEST"
    assert events[0].event_type == "COMMAND_EXECUTED"
