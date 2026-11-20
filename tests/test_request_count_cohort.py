"""Request counters must use the emit cohort, not end_time completions alone.

Previously ``summarize_service_response`` counted:

- ``requests_total`` from ``SRC_M`` / ``time_emit``
- ``requests_successful`` from completions filtered by ``end_time``

Backlog that finishes inside a later window then made ``successful > total``.
"""

from __future__ import annotations

import unittest

import pandas as pd

from yafs.metrics import MetricsAnalyzer

APP_NAME = "CohortApp"
MODULE_NAME = "svc"
REQUEST_MESSAGE = "M.req"
REPLY_MESSAGE = "M.reply"
APP_DEFINITION = [
    {
        "id": APP_NAME,
        "name": APP_NAME,
        "has_backward_return": True,
        "module": [
            {
                "id": APP_NAME,
                "name": MODULE_NAME,
                "type": "MODULE",
                "RAM": 1,
            }
        ],
        "message": [
            {
                "id": 0,
                "name": REQUEST_MESSAGE,
                "s": "None",
                "d": MODULE_NAME,
                "bytes": 20,
                "instructions": 30,
            },
            {
                "id": 1,
                "name": REPLY_MESSAGE,
                "s": MODULE_NAME,
                "d": "None",
                "bytes": 20,
                "instructions": 30,
            },
        ],
        "transmission": [
            {
                "message_in": REQUEST_MESSAGE,
                "module": MODULE_NAME,
                "message_out": REPLY_MESSAGE,
            }
        ],
    }
]


def _src(request_id: int, emit: float) -> dict:
    return {
        "id": request_id,
        "type": "SRC_M",
        "app": APP_NAME,
        "module": "None",
        "message": REQUEST_MESSAGE,
        "DES.src": 0,
        "DES.dst": 0,
        "TOPO.src": 0,
        "TOPO.dst": 0,
        "module.src": "None",
        "service": 0,
        "time_in": emit,
        "time_out": emit,
        "time_emit": emit,
        "time_reception": emit,
    }


def _comp(request_id: int, emit: float, done: float) -> dict:
    return {
        "id": request_id,
        "type": "COMP_M",
        "app": APP_NAME,
        "module": MODULE_NAME,
        "message": REQUEST_MESSAGE,
        "DES.src": 0,
        "DES.dst": 1,
        "TOPO.src": 0,
        "TOPO.dst": 1,
        "module.src": "None",
        "service": 0,
        "time_in": emit + 0.1,
        "time_out": done - 0.1,
        "time_emit": emit,
        "time_reception": emit + 0.1,
    }


def _sink(request_id: int, done: float) -> dict:
    return {
        "id": request_id,
        "type": "SINK_M",
        "app": APP_NAME,
        "module": "None",
        "message": REPLY_MESSAGE,
        "DES.src": 1,
        "DES.dst": 0,
        "TOPO.src": 1,
        "TOPO.dst": 0,
        "module.src": MODULE_NAME,
        "service": 0,
        "time_in": done,
        "time_out": done,
        "time_emit": done,
        "time_reception": done,
    }


def _analyzer(events: list[dict]) -> MetricsAnalyzer:
    return MetricsAnalyzer(
        app_definition=APP_DEFINITION,
        event_df=pd.DataFrame(events),
        link_df=pd.DataFrame(columns=list(MetricsAnalyzer.LINK_COLUMNS)),
    )


class RequestCountCohortTests(unittest.TestCase):
    def test_backlog_completion_does_not_inflate_successful(self) -> None:
        # id=1 emitted before the window, completes inside it (backlog).
        # id=2 emitted and completed inside the window.
        # id=3 emitted inside the window, still in flight at to_time.
        events = [
            _src(1, emit=5.0),
            _comp(1, emit=5.0, done=15.0),
            _sink(1, done=15.0),
            _src(2, emit=12.0),
            _comp(2, emit=12.0, done=18.0),
            _sink(2, done=18.0),
            _src(3, emit=16.0),
            _comp(3, emit=16.0, done=25.0),
            _sink(3, done=25.0),
        ]
        summary = _analyzer(events).summarize_service_response(
            from_time=10.0,
            to_time=20.0,
            include_return_messages=True,
        )
        self.assertEqual(len(summary), 1)
        row = summary.iloc[0]
        self.assertEqual(float(row["requests_total"]), 2.0)  # ids 2 and 3
        self.assertEqual(float(row["requests_successful"]), 1.0)  # only id 2
        self.assertEqual(float(row["requests_unsuccessful"]), 1.0)  # id 3 in flight
        self.assertLessEqual(
            float(row["requests_successful"]),
            float(row["requests_total"]),
        )

    def test_full_horizon_successful_never_exceeds_total(self) -> None:
        events = [
            _src(1, emit=1.0),
            _comp(1, emit=1.0, done=2.0),
            _sink(1, done=2.0),
            _src(2, emit=3.0),  # still in flight / incomplete in this trace
        ]
        summary = _analyzer(events).summarize_service_response(
            include_return_messages=True,
        )
        row = summary.iloc[0]
        self.assertEqual(float(row["requests_total"]), 2.0)
        self.assertEqual(float(row["requests_successful"]), 1.0)
        self.assertEqual(float(row["requests_unsuccessful"]), 1.0)


if __name__ == "__main__":
    unittest.main()
