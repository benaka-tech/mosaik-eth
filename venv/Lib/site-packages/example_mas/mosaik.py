"""
This is not really a mutli-agent system (MAS) but shows of how a MAS (or other
control strategy) can get or set data from and to other simulators alghough
the scenario didn't describe explicit data flows.

These remote calls to mosaik can also be used to implement data storage
backends or visualizations.

"""
import logging

import mosaik_api


logger = logging.getLogger('example_mas')


example_sim_meta = {
    'models': {
        'Agent': {
            'public': True,
            'params': [],
            'attrs': [],
        },
    },
}


class ExampleMas(mosaik_api.Simulator):
    def __init__(self):
        super(ExampleMas, self).__init__(example_sim_meta)
        self.sid = None
        self.step_size = None
        self.agents = []
        self.rel = None

    def init(self, sid, step_size=1):
        self.sid = sid
        self.step_size = step_size
        return self.meta

    def create(self, num, model):
        if model != 'Agent':
            raise ValueError('Can only create "Agent" models.')

        num_agents = len(self.agents)
        agents = [{'eid': str(eid), 'type': model, 'rel': []}
                  for eid in range(num_agents, num_agents + num)]
        self.agents.extend(agents)
        return agents

    def step(self, time, inputs):
        prog = yield self.mosaik.get_progress()
        print('Progress: %.1f%%' % prog)

        if time == 0:
            self.rel = yield self.mosaik.get_related_entities(
                ['%s.%s' % (self.sid, a['eid']) for a in self.agents])
            print(self.rel)

        data = yield self.mosaik.get_data({eid: ['val_out']
                                           for rels in self.rel.values()
                                           for eid in rels})
        print(data)

        inputs = {}
        for a in self.agents:
            full_id = '%s.%s' % (self.sid, a['eid'])
            inputs[full_id] = {eid: {'val_in': 23}
                               for eid in self.rel[full_id]}
        yield self.mosaik.set_data(inputs)

        return time + self.step_size

    def get_data(self, outputs):
        # We have nothing to give ...
        return {}


def main():
    return mosaik_api.start_simulation(ExampleMas())
