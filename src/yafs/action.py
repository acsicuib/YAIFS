class generic_action(object):
    # service_coverage
    #   key   => street node identifier in the network
    #   value => software module ID

    def __init__(self, sim):  # sim is an instance of CORE.Sim
        self.sim = sim

    def action(self, mobile_agent):
        """
        Execute the action associated with the given mobile agent.

        Override this method in subclasses to define custom behaviour.
        """
        raise NotImplementedError("Subclasses must implement 'action'.")
