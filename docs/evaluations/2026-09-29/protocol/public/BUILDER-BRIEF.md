# Builder brief (common to both builders)

You are implementing the simulated purchase-order workflow in `REQUIREMENTS.md` behind the
adapter interface in `ADAPTER.md`. The evaluator will run your implementation through the
common harness: the visible tests in `tests/` plus held-out tests that use the same harness,
the same adapter factory and the same semantics.

## Deliverables (all inside your workspace)

1. **The implementation.** A Python package and an adapter module exposing
   `create_adapter(home, env)`, loadable with `PO_ADAPTER=package.module:create_adapter`
   and `PO_ADAPTER_PATH=<your source dir>`.
2. **Your own tests,** beyond the visible ones, for the behaviour you implemented.
3. **`README.md`,** covering:
   * exact reproduction steps: the Python environment, the environment variables, and the
     commands that run the visible tests and your tests
   * where state is stored under `home`
   * how an operator inspects a request, exports and verifies an audit bundle, and reconciles
     an unknown outcome
   * known limitations
4. **`BUILD-LOG.md`,** with time-stamped entries (UTC) for these phases:
   * **setup** (reading and orientation)
   * **implementation**
   * **debugging**

   It must also contain these sections:
   * **Documentation gaps:** anything missing or unclear in the documents you were given.
   * **Workarounds:** anything you had to work around, with the reason.
   * **Requests for core changes:** changes you wanted in a library or framework you used but
     did not make.
   * **Final status:** what works, what doesn't, and the last visible-test result you
     observed (counts).

## Rules

* Work only inside your assigned workspace directory. Do not read or write any other folder
  in the evaluation tree: other builds, protocol internals, evaluator notes. The exceptions
  are the public protocol files you were pointed to, and any read-only source your
  arm-specific note allows.
* Do not modify `harness/` or `tests/`. You may copy them into your workspace, and you may add
  tests in your own directory.
* All effects must stay simulated. Use only the harness services; make no network calls and
  touch no real systems.
* Do not install packages. Use the Python environment you are given.
* Use no secrets, `.env` files or paid model calls.
* Do not rely on test-specific behaviour, such as detecting the test runner or hard-coding
  request ids or values from tests. The held-out tests use other values and sequences.
* **Budget:** one run of at most 300 tool calls. When you approach the limit, stop, make sure
  README.md and BUILD-LOG.md reflect the actual state, and hand off whatever you have. An
  incomplete but honest hand-off is scored as-is. There are no reruns.
* In your final message, state what you ran and the observed results. Do not claim anything
  you did not verify.
