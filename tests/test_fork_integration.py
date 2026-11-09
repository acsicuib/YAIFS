"""Integration tests for reproducible traces across forks."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.fork_support import (
    SEED,
    create_service,
    enable_mobility,
    run_for,
    simulation_of,
    trace_tables,
    user_rows,
)


class ForkTraceTests(unittest.TestCase):
    """Same seeds and untouched branches stay on the same trace."""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.results = Path(self._directory.name)

    def test_same_configuration_and_seed_match(self) -> None:
        """Two fresh runs with one seed emit the same call traces."""
        left_service, left_id = create_service(
            self.results / "left",
            seed=SEED,
            name="left",
        )
        right_service, right_id = create_service(
            self.results / "right",
            seed=SEED,
            name="right",
        )
        run_for(left_service, left_id, 2000.0)
        run_for(right_service, right_id, 2000.0)

        left = simulation_of(left_service, left_id)
        right = simulation_of(right_service, right_id)
        self.assertEqual(trace_tables(left), trace_tables(right))
        self.assertEqual(user_rows(left), user_rows(right))
        self.assertGreater(len(trace_tables(left)[0]), 1)

    def test_untouched_branches_evolve_equally(self) -> None:
        """Parent and child match a straight run when neither is edited."""
        straight_service, straight_id = create_service(
            self.results / "straight",
            seed=SEED,
            name="straight",
        )
        run_for(straight_service, straight_id, 2000.0)
        straight = simulation_of(straight_service, straight_id)

        service, parent_id = create_service(
            self.results / "branched",
            seed=SEED,
            name="parent",
        )
        run_for(service, parent_id, 1000.0)
        child_state = service.fork(parent_id, child_name="same-evolution")
        child_id = child_state.summary.id
        run_for(service, parent_id, 1000.0)
        run_for(service, child_id, 1000.0)

        parent = simulation_of(service, parent_id)
        child = simulation_of(service, child_id)
        straight_traces = trace_tables(straight)
        self.assertEqual(trace_tables(parent), straight_traces)
        self.assertEqual(trace_tables(child), straight_traces)
        self.assertEqual(user_rows(parent), user_rows(straight))
        self.assertEqual(user_rows(child), user_rows(straight))
        self.assertEqual(float(parent.sim.env.now), float(child.sim.env.now))

    def test_mobility_branches_stay_aligned_until_an_edit(self) -> None:
        """Random user generation stays identical on untouched branches."""
        straight_service, straight_id = create_service(
            self.results / "mobility-straight",
            seed=SEED,
            name="straight",
        )
        enable_mobility(straight_service, straight_id)
        run_for(straight_service, straight_id, 2000.0)
        straight = simulation_of(straight_service, straight_id)

        service, parent_id = create_service(
            self.results / "mobility-branched",
            seed=SEED,
            name="parent",
        )
        enable_mobility(service, parent_id)
        run_for(service, parent_id, 1000.0)
        child_state = service.fork(parent_id, child_name="mobility-child")
        child_id = child_state.summary.id
        run_for(service, parent_id, 1000.0)
        run_for(service, child_id, 1000.0)

        parent = simulation_of(service, parent_id)
        child = simulation_of(service, child_id)
        self.assertEqual(trace_tables(parent), trace_tables(straight))
        self.assertEqual(trace_tables(child), trace_tables(straight))
        self.assertEqual(user_rows(parent), user_rows(child))
        self.assertGreater(len(user_rows(parent)), 3)

        other_service, other_id = create_service(
            self.results / "mobility-other-seed",
            seed=SEED + 1,
            name="other-seed",
        )
        enable_mobility(other_service, other_id)
        run_for(other_service, other_id, 2000.0)
        other = simulation_of(other_service, other_id)
        self.assertNotEqual(trace_tables(other), trace_tables(straight))

    def test_fork_after_node_removal_keeps_both_lines_equal(self) -> None:
        """s2 and s3 stay equal when no further failure is applied."""
        service, parent_id = create_service(
            self.results / "failure",
            seed=SEED,
            name="before-failure",
        )
        run_for(service, parent_id, 1000.0)
        removed = "mec-0-worker-2"
        service.remove_node(parent_id, removed)
        child_state = service.fork(parent_id, child_name="after-failure")
        child_id = child_state.summary.id

        parent_nodes = {item["node"] for item in service.list_nodes(parent_id)}
        child_nodes = {item["node"] for item in service.list_nodes(child_id)}
        self.assertNotIn(removed, parent_nodes)
        self.assertEqual(parent_nodes, child_nodes)

        run_for(service, parent_id, 1000.0)
        run_for(service, child_id, 1000.0)
        parent = simulation_of(service, parent_id)
        child = simulation_of(service, child_id)
        self.assertEqual(trace_tables(parent), trace_tables(child))
        self.assertEqual(user_rows(parent), user_rows(child))


if __name__ == "__main__":
    unittest.main()
