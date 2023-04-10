"""
This dataflow crashes for an Exception while getting the next input.
We cause the crash by raising an Exception in DynamicInput.next
"""

# Import functions that we don't need to break form the working example
import working

from bytewax.dataflow import Dataflow
from bytewax.connectors.stdio import StdOutput
from bytewax.inputs import StatelessSource, DynamicInput


class NumberSource(StatelessSource):
    def __init__(self, max):
        self.iterator = iter(range(max))

    def next(self):
        # XXX: Error here
        raise ValueError("A vague error")
        return next(self.iterator)

    def close(self):
        pass


class NumberInput(DynamicInput):
    def __init__(self, max):
        self.max = max

    def build(self, worker_index, worker_count):
        return NumberSource(self.max)


flow = Dataflow()
flow.input("inp", NumberInput(10))
flow.map(working.stringify)
flow.output("out", StdOutput())


if __name__ == "__main__":
    from bytewax.execution import run_main
    run_main(flow)
    # from bytewax.execution import spawn_cluster
    # spawn_cluster(flow, proc_count=2, worker_count_per_proc=2)