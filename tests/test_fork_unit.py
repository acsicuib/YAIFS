"""Unit tests for fork: generator state and independent copies."""

from __future__ import annotations

import random
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np

from tests.fork_support import (
    SEED,
    create_service,
    enable_mobility,
    generator_state,
    run_for,
    simulation_of,
    states_equal,
    trace_tables,
    user_rows,
    virgin_numpy_rng,
    virgin_sim_rng,
)
from yafs.distribution import (
    exponentialDistribution,
    exponentialDistributionStartPoint,
    exponential_distribution,
    uniformDistribution,
)


class OwnedGeneratorProcess:
    """Custom DES whose draws come from generators it owns."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.numpy_rng = np.random.RandomState(seed)

    def __call__(self, _context: object) -> None:
        self.rng.random()
        self.numpy_rng.random()


def _is_random_generator(value: object) -> bool:
    return isinstance(value, (random.Random, np.random.RandomState))


def _owned_generators(callback: object) -> dict[str, object]:
    found = {}
    for name, value in vars(callback).items():
        if _is_random_generator(value):
            found[name] = value
    return found


def _restore_generator(generator: object, state: object) -> None:
    if isinstance(generator, np.random.RandomState):
        generator.set_state(state)
        return
    generator.setstate(state)


class ForkRandomStateTests(unittest.TestCase):
    """Random generators survive a fork as equal but distinct objects."""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.results = Path(self._directory.name)

    def test_service_call_generator_is_copied(self) -> None:
        """Service invocations consume sim.rng; the fork keeps that state."""
        service, parent_id = create_service(self.results, seed=SEED)
        run_for(service, parent_id, 1000.0)
        parent = simulation_of(service, parent_id)
        self.assertFalse(
            states_equal(parent.sim.rng.getstate(), virgin_sim_rng(SEED))
        )

        child_state = service.fork(parent_id, child_name="calls-child")
        child = simulation_of(service, child_state.summary.id)

        self.assertIsNot(parent.sim.rng, child.sim.rng)
        self.assertTrue(
            states_equal(parent.sim.rng.getstate(), child.sim.rng.getstate())
        )

        parent_before = parent.sim.rng.getstate()
        drawn = child.sim.rng.random()
        self.assertEqual(parent.sim.rng.getstate(), parent_before)
        child.sim.rng.setstate(parent_before)
        self.assertEqual(parent.sim.rng.random(), drawn)

        parent_events, parent_links = trace_tables(parent)
        child_events, child_links = trace_tables(child)
        self.assertGreater(len(parent_events), 1)
        self.assertEqual(parent_events, child_events)
        self.assertEqual(parent_links, child_links)
        self.assertIn("COMP_M", {row[1] for row in parent_events[1:]})

    def test_activation_generator_is_copied(self) -> None:
        """Exponential process activations keep their own generator."""
        service, parent_id = create_service(self.results, seed=SEED)
        enable_mobility(service, parent_id)
        run_for(service, parent_id, 2000.0)
        parent = simulation_of(service, parent_id)
        parent_process = parent._registered_processes["user-mobility"]
        parent_rnd = parent_process.live_distribution.rnd
        self.assertGreater(parent_process.activation_count, 0)
        self.assertFalse(
            states_equal(generator_state(parent_rnd), virgin_numpy_rng(7))
        )

        child_state = service.fork(parent_id, child_name="activation-child")
        child = simulation_of(service, child_state.summary.id)
        child_process = child._registered_processes["user-mobility"]
        child_rnd = child_process.live_distribution.rnd

        self.assertIsNot(parent_rnd, child_rnd)
        self.assertTrue(
            states_equal(
                generator_state(parent_rnd),
                generator_state(child_rnd),
            )
        )
        self.assertEqual(
            parent_process.activation_count,
            child_process.activation_count,
        )

        parent_before = generator_state(parent_rnd)
        child_rnd.random()
        self.assertTrue(
            states_equal(generator_state(parent_rnd), parent_before)
        )

    def test_user_generation_is_copied_and_not_shared(self) -> None:
        """Mobility-created users match, but the branches do not alias."""
        service, parent_id = create_service(self.results, seed=SEED)
        enable_mobility(service, parent_id)
        run_for(service, parent_id, 2000.0)

        child_state = service.fork(parent_id, child_name="users-child")
        child_id = child_state.summary.id
        parent = simulation_of(service, parent_id)
        child = simulation_of(service, child_id)

        parent_callback = parent._registered_processes[
            "user-mobility"
        ].callback
        child_callback = child._registered_processes[
            "user-mobility"
        ].callback
        self.assertIsNot(parent_callback, child_callback)
        self.assertEqual(parent_callback.user_des, child_callback.user_des)
        self.assertIsNot(parent_callback.user_des, child_callback.user_des)
        self.assertGreater(len(parent_callback.user_des), 0)
        self.assertEqual(user_rows(parent), user_rows(child))

        child_callback.user_des.append(-1)
        self.assertNotIn(-1, parent_callback.user_des)

        before = user_rows(parent)
        service.create_users(
            child_id,
            {
                "sources": [
                    {
                        "app": 0,
                        "message": "M.AR.0_0",
                        "id_resource": "cdc-0-worker-1",
                        "lambda": 300,
                    }
                ]
            },
        )
        self.assertEqual(user_rows(parent), before)
        self.assertGreater(len(user_rows(child)), len(before))

        parent_users = parent.infrastructure.users
        child_users = child.infrastructure.users
        self.assertIsNot(parent_users, child_users)
        self.assertIsNot(parent_users["sources"], child_users["sources"])
        child_users["sources"].append({"probe": True})
        self.assertNotIn({"probe": True}, parent_users["sources"])

    def test_custom_des_random_variables_are_duplicated(self) -> None:
        """Every stochastic DES keeps a private generator after a fork."""
        service, parent_id = create_service(self.results, seed=SEED)
        parent = simulation_of(service, parent_id)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            activations = {
                "des-exponential": exponential_distribution(
                    lambd=80,
                    seed=3,
                    name="des-exponential",
                ),
                "des-uniform": uniformDistribution(
                    min=40,
                    max=80,
                    seed=5,
                    name="des-uniform",
                ),
                "des-exponential-start": exponentialDistributionStartPoint(
                    start=30,
                    lambd=80,
                    seed=9,
                    name="des-exponential-start",
                ),
                "des-legacy-exponential": exponentialDistribution(
                    lambd=80,
                    seed=13,
                    name="des-legacy-exponential",
                ),
            }
        for index, (name, distribution) in enumerate(activations.items()):
            parent.register_process(
                name,
                OwnedGeneratorProcess(seed=100 + index),
                distribution,
            )

        run_for(service, parent_id, 1000.0)
        child_state = service.fork(parent_id, child_name="des-child")
        child = simulation_of(service, child_state.summary.id)

        for name in activations:
            parent_process = parent._registered_processes[name]
            child_process = child._registered_processes[name]
            self.assertGreater(parent_process.activation_count, 1)
            self.assertEqual(
                parent_process.activation_count,
                child_process.activation_count,
            )
            self.assertIsNot(parent_process.callback, child_process.callback)

            parent_rnd = parent_process.live_distribution.rnd
            child_rnd = child_process.live_distribution.rnd
            self._assert_generator_copied(parent_rnd, child_rnd)
            self.assertIsNot(
                parent_rnd,
                parent_process.distribution.rnd,
            )

            parent_owned = _owned_generators(parent_process.callback)
            child_owned = _owned_generators(child_process.callback)
            self.assertEqual(set(parent_owned), {"rng", "numpy_rng"})
            for attr in parent_owned:
                self._assert_generator_copied(
                    parent_owned[attr],
                    child_owned[attr],
                )

            template_owned = _owned_generators(
                child_process.callback_template
            )
            self.assertIsNot(
                template_owned["rng"],
                child_owned["rng"],
            )
            self.assertIsNot(
                template_owned["numpy_rng"],
                child_owned["numpy_rng"],
            )

        activation_generators = [
            child._registered_processes[name].live_distribution.rnd
            for name in activations
        ]
        self.assertEqual(
            len(activation_generators),
            len(set(map(id, activation_generators))),
        )

    def _assert_generator_copied(self, parent_rng, child_rng) -> None:
        self.assertIsNot(parent_rng, child_rng)
        self.assertTrue(
            states_equal(
                generator_state(parent_rng),
                generator_state(child_rng),
            )
        )
        parent_before = generator_state(parent_rng)
        child_before = generator_state(child_rng)
        child_rng.random()
        self.assertTrue(
            states_equal(generator_state(parent_rng), parent_before)
        )
        self.assertFalse(
            states_equal(generator_state(child_rng), child_before)
        )
        _restore_generator(child_rng, child_before)


class ForkIsolationTests(unittest.TestCase):
    """Forked branches do not share mutable simulation objects."""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.results = Path(self._directory.name)

    def _forked_pair(self):
        service, parent_id = create_service(self.results, seed=SEED)
        enable_mobility(service, parent_id)
        run_for(service, parent_id, 1000.0)
        child_state = service.fork(parent_id, child_name="isolated-child")
        parent = simulation_of(service, parent_id)
        child = simulation_of(service, child_state.summary.id)
        return service, parent_id, child_state.summary.id, parent, child

    def test_topology_services_and_routing_are_distinct(self) -> None:
        service, parent_id, child_id, parent, child = self._forked_pair()

        self.assertIsNot(parent.sim.topology, child.sim.topology)
        self.assertIsNot(parent.sim.topology.G, child.sim.topology.G)
        self.assertIs(
            parent.sim.topology,
            parent.infrastructure.topology,
        )
        parent_nodes = service.list_nodes(parent_id)
        child_nodes = service.list_nodes(child_id)
        self.assertEqual(parent_nodes, child_nodes)

        node_id = "cdc-0-worker-1"
        parent_attrs = parent.sim.topology.G.nodes[node_id]
        child_attrs = child.sim.topology.G.nodes[node_id]
        self.assertIsNot(parent_attrs, child_attrs)
        child_attrs["probe"] = "child-only"
        self.assertNotIn("probe", parent_attrs)

        self.assertIsNot(
            parent.infrastructure.services,
            child.infrastructure.services,
        )
        app_name = "Augmented Reality (AR)"
        parent_message = parent.infrastructure.services[app_name].get_message(
            "M.AR.0_0"
        )
        child_message = child.infrastructure.services[app_name].get_message(
            "M.AR.0_0"
        )
        self.assertIsNot(parent_message, child_message)
        original_bytes = parent_message.bytes
        child_message.bytes = original_bytes + 25
        self.assertEqual(parent_message.bytes, original_bytes)

        self.assertIsNot(
            parent.infrastructure.placement,
            child.infrastructure.placement,
        )
        self.assertIsNot(
            parent.infrastructure.placement.data,
            child.infrastructure.placement.data,
        )
        self.assertIsNot(
            parent.infrastructure.routing,
            child.infrastructure.routing,
        )
        self.assertIsNot(
            parent.infrastructure.routing.cache,
            child.infrastructure.routing.cache,
        )
        child.infrastructure.routing.cache["probe"] = "child-only"
        self.assertNotIn("probe", parent.infrastructure.routing.cache)

        self.assertIsNot(parent._journal, child._journal)

    def test_user_distributions_and_lambdas_are_distinct(self) -> None:
        service, _parent_id, child_id, parent, child = self._forked_pair()
        parent_sources = parent.sim.alloc_source
        child_sources = child.sim.alloc_source
        self.assertEqual(set(parent_sources), set(child_sources))

        for des, parent_source in parent_sources.items():
            child_source = child_sources[des]
            self.assertIsNot(
                parent_source["distribution"],
                child_source["distribution"],
            )
            self.assertIsNot(
                parent_source["source_definition"],
                child_source["source_definition"],
            )
            parent_next = parent_source["distribution"].next()
            child_source["distribution"].time = 17
            self.assertEqual(parent_source["distribution"].next(), parent_next)

        sample_des = sorted(parent_sources)[0]
        service.update_user_lambda(child_id, sample_des, 17)
        self.assertEqual(child_sources[sample_des]["lambda"], 17)
        self.assertNotEqual(parent_sources[sample_des]["lambda"], 17)

    def test_node_removal_does_not_change_the_parent(self) -> None:
        service, parent_id, child_id, _parent, _child = self._forked_pair()
        removed = "mec-0-worker-2"
        service.remove_node(child_id, removed)

        parent_names = {item["node"] for item in service.list_nodes(parent_id)}
        child_names = {item["node"] for item in service.list_nodes(child_id)}
        self.assertIn(removed, parent_names)
        self.assertNotIn(removed, child_names)

    def test_s1_node_removal_leaves_s0_unchanged(self) -> None:
        """A failure applied to s1 does not remove the node from s0."""
        removed = "mec-0-worker-2"
        service, s0_id = create_service(
            self.results,
            seed=SEED,
            name="topology-changes-root",
        )
        run_for(service, s0_id, 1000.0)
        s0_before = {
            item["node"] for item in service.list_nodes(s0_id)
        }
        self.assertIn(removed, s0_before)

        s1 = service.fork(
            s0_id,
            child_name="topology-changes-1-failure",
        )
        s1_id = s1.summary.id
        s1_before = {
            item["node"] for item in service.list_nodes(s1_id)
        }
        self.assertIn(removed, s1_before)

        service.remove_node(s1_id, removed)

        s0_nodes = {
            item["node"] for item in service.list_nodes(s0_id)
        }
        s1_nodes = {
            item["node"] for item in service.list_nodes(s1_id)
        }
        self.assertIn(removed, s0_nodes)
        self.assertNotIn(removed, s1_nodes)
        self.assertEqual(s0_nodes, s0_before)

        s0 = simulation_of(service, s0_id)
        s1_sim = simulation_of(service, s1_id)
        self.assertIsNot(s0.sim.topology.G, s1_sim.sim.topology.G)
        self.assertTrue(s0.sim.topology.G.has_node(removed))
        self.assertFalse(s1_sim.sim.topology.G.has_node(removed))


if __name__ == "__main__":
    unittest.main()
