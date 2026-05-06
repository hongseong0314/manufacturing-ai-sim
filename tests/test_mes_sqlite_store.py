from src.mes.domain import Equipment, Event, Lot, Recipe, Wafer
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


def test_sqlite_store_reloads_runtime_entities(tmp_path):
    db_path = tmp_path / "mes.sqlite3"
    store = SQLiteMESStore(db_path)
    store.upsert_lot(Lot(lot_id="LOT_1", product_id="P1", quantity=2))
    store.upsert_wafer(Wafer(wafer_id="WAFER_1", lot_id="LOT_1", task_uid=1))
    store.upsert_equipment(
        Equipment(equipment_id="A_0", equipment_group_id="A", status="RUN")
    )
    store.upsert_recipe(
        Recipe(
            recipe_id="SIM_A_BASE",
            operation_id="A",
            equipment_group_id="A",
            parameter_set={"temp": 10.0},
        )
    )

    reloaded = SQLiteMESStore(db_path)

    assert [lot.lot_id for lot in reloaded.lots()] == ["LOT_1"]
    assert [wafer.wafer_id for wafer in reloaded.wafers("LOT_1")] == ["WAFER_1"]
    assert [tool.equipment_id for tool in reloaded.equipment()] == ["A_0"]
    assert [recipe.recipe_id for recipe in reloaded.recipes()] == ["SIM_A_BASE"]
