"""Deliberate behavioural faults, not a mutation-coverage percentage.

Install at engine validation/dispatch/recovery boundaries in disposable instances.
Healthy adapters contain no compensating governance. Historical sources are untouched.
"""

from uuid import uuid4


def inject(bridge):
    engine = bridge.engine
    if bridge.fault == "stale_approval":
        if bridge.arm == "application":
            engine.valid = lambda *args, **kwargs: None
        else:
            original = engine.fw._revalidate
            cache = []
            change = bridge.change_evidence

            def change_without_revalidation():
                with engine.fw.store.transaction() as db:
                    cache.append(original(db, bridge.handle["token"]["payload"]))
                change()

            bridge.change_evidence = change_without_revalidation
            engine.fw._revalidate = lambda *args, **kwargs: (
                cache[0] if cache else original(*args, **kwargs)
            )
    elif bridge.fault == "duplicate_effect":
        original = engine.dispatch
        dispatched = []

        def repeat_with_new_key(handle):
            if not dispatched:
                result = original(handle)
                dispatched.append(True)
                return result
            return bridge.service.execute(
                "fault_" + uuid4().hex, bridge.action, bridge.service.facts()
            )

        engine.dispatch = repeat_with_new_key
    elif bridge.fault == "lost_response":

        def recover_with_new_key(handle):
            bridge.service.mode = "success"
            return bridge.service.execute(
                "fault_" + uuid4().hex, bridge.action, bridge.service.facts()
            )

        engine.reconcile = recover_with_new_key
    else:
        raise ValueError("Unknown pilot fault")
