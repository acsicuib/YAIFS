# Fork reproducibility tests

These tests guarantee that `SimulationService.fork` produces an independent
simulation branch that can evolve on its own.

A fork is the operation used by
`tutorial_scenarios/using_service_layer_01`: one running simulation is split
into two lines, such as `s2` and `s3`. At the fork instant both lines must
stand at the same state. After that, an edit on one line must not change the
other. If neither line is edited, they must keep producing the same users,
service calls, and traces.

The scenario under test is `tutorial_scenarios/using_service_layer_01`.
Results are written to a temporary directory and discarded.

## What a correct fork preserves

- The simulation clock and the history up to the fork time.
- The state of every random generator that the branch has already consumed.
- A separate copy of each generator and of every mutable object, so later
  draws and edits stay on one branch.

Custom DES processes that depend on a random variable are part of this
contract. That includes activation distributions (exponential, uniform,
exponential with a fixed first delay, and the legacy exponential
distribution) and a process that owns both a `random.Random` and a NumPy
generator. User mobility uses the simulation generator. On fork, each of
those generators is copied from its state at registration and then advanced
by replaying the parent, so the child has its own stream positioned at the
same draw.

## Layout

| File | Role |
| --- | --- |
| `test_fork_unit.py` | Generator state and object independence |
| `test_fork_integration.py` | Full traces of complete runs and branches |
| `fork_support.py` | Shared scenario setup, run helper, and trace reader |

### Unit tests

`test_fork_unit.py` checks the fork point itself:

- Service calls consume `sim.rng`, and the child receives an equal but
  distinct generator. A draw on the child does not move the parent.
- Exponential activation of the user-mobility process keeps its own NumPy
  generator, copied the same way.
- Users created by that mobility process match on both branches, but the
  process objects, user lists, and user records are not shared. Creating a
  user on the child leaves the parent unchanged.
- Every stochastic custom DES listed above keeps a private activation
  generator and private callback generators after the fork.
- Topology, services, messages, placement, routing cache, and the mutation
  journal are distinct objects. Changing a user lambda or removing a node
  on the child does not change the parent.

### Integration tests

`test_fork_integration.py` checks evolution over a time window:

- Two fresh runs with the same configuration and seed emit the same event
  and link traces.
- A parent and its fork, continued with no further edits, match a single
  run that never forked. The same holds when users are created at random.
- A different seed changes that mobility trace.
- After a node removal, the two lines still match if no further failure is
  applied. This is the `s2` / `s3` case: they share the failure that
  happened before the fork, and they diverge only when a later edit is
  applied to one of them.

## Run

From the repository root:

```bash
uv run python -m unittest discover -s tests -t . -v
```
