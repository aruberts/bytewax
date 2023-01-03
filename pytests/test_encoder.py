import json
from datetime import datetime, timedelta, timezone

from bytewax._encoder import encode_dataflow
from bytewax.dataflow import Dataflow
from bytewax.inputs import ManualInputConfig
from bytewax.window import EventClockConfig, TumblingWindowConfig


# Helper functions for some steps
def acc_values(acc, event):
    acc.append((event["value"], event["time"]))
    return acc


# Example class to be encoded
class OrderBook:
    def __init__(self):
        self.data = []

    def update(self, data):
        self.data.append(data)


def test_encoding_manual_input():
    flow = Dataflow()
    inp = [0, 1, 2]
    flow.input("inp", ManualInputConfig(lambda: inp))

    assert encode_dataflow(flow) == json.dumps(
        {
            "type": "Dataflow",
            "steps": [
                {
                    "input_config": {
                        "input_builder": "<lambda>",
                        "type": "ManualInputConfig",
                    },
                    "step_id": "inp",
                    "type": "Input",
                },
            ],
        },
        sort_keys=True,
    )


def test_encoding_map():
    flow = Dataflow()
    flow.map(lambda x: x + 1)

    assert encode_dataflow(flow) == json.dumps(
        {"type": "Dataflow", "steps": [{"type": "Map", "mapper": "<lambda>"}]},
        sort_keys=True,
    )


def test_encoding_filter():
    flow = Dataflow()
    flow.filter(lambda x: x == 1)

    assert encode_dataflow(flow) == json.dumps(
        {"type": "Dataflow", "steps": [{"type": "Filter", "predicate": "<lambda>"}]},
        sort_keys=True,
    )


def test_encoding_reduce():
    flow = Dataflow()
    flow.reduce("sessionizer", lambda x, y: x + y, lambda x, y: x == y)

    assert encode_dataflow(flow) == json.dumps(
        {
            "type": "Dataflow",
            "steps": [
                {
                    "type": "Reduce",
                    "step_id": "sessionizer",
                    "reducer": "<lambda>",
                    "is_complete": "<lambda>",
                }
            ],
        },
        sort_keys=True,
    )


def test_encoding_flat_map():
    flow = Dataflow()
    flow.flat_map(lambda x: x + 1)

    assert encode_dataflow(flow) == json.dumps(
        {"type": "Dataflow", "steps": [{"type": "FlatMap", "mapper": "<lambda>"}]},
        sort_keys=True,
    )


def test_encoding_stateful_map():
    flow = Dataflow()
    flow.stateful_map("order_book", lambda key: OrderBook(), OrderBook.update)

    assert encode_dataflow(flow) == json.dumps(
        {
            "type": "Dataflow",
            "steps": [
                {
                    "builder": "<lambda>",
                    "mapper": "update",
                    "step_id": "order_book",
                    "type": "StatefulMap",
                }
            ],
        },
        sort_keys=True,
    )


def test_encoding_fold_window():
    flow = Dataflow()
    start_at = datetime(2005, 7, 14, 12, 30).replace(tzinfo=timezone.utc)
    wc = TumblingWindowConfig(start_at=start_at, length=timedelta(seconds=5))
    cc = EventClockConfig(
        lambda x: datetime.fromisoformat(x["time"]),
        wait_for_system_duration=timedelta(seconds=10),
    )
    flow.fold_window("running_average", cc, wc, lambda x: list(x), acc_values)

    assert encode_dataflow(flow) == json.dumps(
        {
            "type": "Dataflow",
            "steps": [
                {
                    "builder": "<lambda>",
                    "clock_config": {
                        "dt_getter": "<lambda>",
                        "type": "EventClockConfig",
                        "wait_for_system_duration": "0:00:10",
                    },
                    "folder": "acc_values",
                    "step_id": "running_average",
                    "type": "FoldWindow",
                    "window_config": {
                        "length": "0:00:05",
                        "start_at": "2005-07-14T12:30:00+00:00",
                        "type": "TumblingWindowConfig",
                    },
                }
            ],
        },
        sort_keys=True,
    )


def test_encoding_method_descriptor():
    flow = Dataflow()
    flow.flat_map(str.split)

    assert encode_dataflow(flow) == json.dumps(
        {"type": "Dataflow", "steps": [{"type": "FlatMap", "mapper": "split"}]},
        sort_keys=True,
    )