"""Process exceptions must stop the run loop and surface to callers.

Previously a registered process that raised (for example create_user on a
removed node) killed the yafs-simulation-thread while Simulation.run() and
SimulationService.wait_until_ready() kept waiting for scheduled_until.
"""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from yafs.api import Infrastructure, Simulation
from yafs.distribution import deterministicDistributionStartPoint
from yafs.services.models import SimulationStatus
from yafs.services.simulation_service import SimulationService

API_SCENARIO = (
    Path(__file__).resolve().parents[1]
    / "tutorial_scenarios"
    / "using_API_layer"
)
SERVICE_SCENARIO = (
    Path(__file__).resolve().parents[1]
    / "tutorial_scenarios"
    / "using_service_layer_01"
)


def _boom_process(context) -> None:
    context.create_user(
        app_ref=0,
        message="M.AR.0_0",
        node_id="no-such-node",
        lambda_value=10,
    )


def _run_with_timeout(callable_obj, *, timeout: float = 10.0):
    """Run callable in a thread; return (result, error) or raise on hang."""
    box: dict[str, object] = {}

    def target() -> None:
        try:
            box["result"] = callable_obj()
        except BaseException as exc:  # noqa: BLE001 - test harness
            box["error"] = exc

    thread = threading.Thread(target=target, name="test-timeout-runner")
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        raise AssertionError(
            f"Callable did not finish within {timeout} seconds "
            "(simulation likely hung after a process exception)"
        )
    return box.get("result"), box.get("error")


class ProcessExceptionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.results = Path(self._directory.name)

    def _make_simulation(self) -> Simulation:
        return Simulation(
            infrastructure=Infrastructure(
                path_to_lab_scenario=API_SCENARIO,
                results_path=self.results,
            ),
            seed=1,
        )

    def test_run_raises_when_registered_process_fails(self) -> None:
        simulation = self._make_simulation()
        simulation.register_process(
            "boom",
            _boom_process,
            deterministicDistributionStartPoint(50, 1000, name="b"),
        )
        try:
            _, error = _run_with_timeout(
                lambda: simulation.run(stop_time=500, step=100),
                timeout=10.0,
            )
            self.assertIsInstance(error, ValueError)
            self.assertIn("Node does not exist", str(error))
            self.assertIn("simulation failed at t=", str(error))
            state = simulation.get_state()
            self.assertTrue(state["failed"])
            self.assertIn("Node does not exist", state["error"])
        finally:
            simulation.stop()

    def test_run_for_marks_failed_and_blocks_restart(self) -> None:
        simulation = self._make_simulation()
        simulation.register_process(
            "boom",
            _boom_process,
            deterministicDistributionStartPoint(50, 1000, name="b"),
        )
        try:
            simulation.run_for(duration=500, step=100)
            deadline = time.monotonic() + 10.0
            state = simulation.get_state()
            while not state["failed"] and time.monotonic() < deadline:
                time.sleep(0.01)
                state = simulation.get_state()
            self.assertTrue(state["failed"], state)
            self.assertIn("Node does not exist", state["error"] or "")

            with self.assertRaises(ValueError) as raised:
                simulation.run(stop_time=500, step=100)
            self.assertIn("Node does not exist", str(raised.exception))
            self.assertIn("simulation failed at t=", str(raised.exception))

            with self.assertRaises(ValueError):
                simulation.run_for(duration=100, step=50)
        finally:
            simulation.stop()
            # stop() must remain usable after a failure
            self.assertTrue(simulation.get_state()["failed"])

    def test_valid_node_still_completes(self) -> None:
        simulation = self._make_simulation()

        def ok(context) -> None:
            context.create_user(
                app_ref=0,
                message="M.AR.0_0",
                node_id="edc-0-worker-1",
                lambda_value=10,
            )

        simulation.register_process(
            "ok",
            ok,
            deterministicDistributionStartPoint(50, 1000, name="ok"),
        )
        try:
            result, error = _run_with_timeout(
                lambda: simulation.run(stop_time=500, step=100),
                timeout=10.0,
            )
            self.assertIsNone(error)
            self.assertIsNotNone(result)
            self.assertFalse(result["failed"])
            self.assertGreaterEqual(result["now"], 500.0)
        finally:
            simulation.stop()


class ProcessExceptionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.results = Path(self._directory.name)
        self.service = SimulationService()
        created = self.service.create_simulation(
            scenario_path=SERVICE_SCENARIO,
            results_path=self.results,
            seed=1,
            name="process-failure",
        )
        self.simulation_id = created.summary.id
        self.simulation = self.service.registry.require(
            self.simulation_id
        ).simulation

    def tearDown(self) -> None:
        try:
            self.service.stop(self.simulation_id)
        except Exception:
            pass

    def test_wait_until_ready_returns_after_process_failure(self) -> None:
        self.simulation.register_process(
            "boom",
            _boom_process,
            deterministicDistributionStartPoint(50, 1000, name="b"),
        )
        self.service.schedule_for(
            self.simulation_id,
            duration=500,
            step=100,
        )

        _, error = _run_with_timeout(
            lambda: self.service.wait_until_ready(
                self.simulation_id,
                poll_interval=0.01,
            ),
            timeout=10.0,
        )
        self.assertIsNone(error)
        state = self.service.get_state(self.simulation_id)
        self.assertEqual(state.summary.status, SimulationStatus.FAILED)
        self.assertIn("Node does not exist", state.summary.error or "")

        with self.assertRaises(RuntimeError) as raised:
            self.service.schedule_for(
                self.simulation_id,
                duration=100,
                step=50,
            )
        self.assertIn("not actionable", str(raised.exception))
