# -*- coding: utf-8 -*-
import random


def _normalized_mapping(data):
    """
    Return a shallow copy of a mapping with normalized string keys.

    This keeps backward compatibility with legacy JSON files while also
    tolerating accidental whitespace around keys such as ``"name "``.
    """
    return {
        key.strip() if isinstance(key, str) else key: value
        for key, value in data.items()
    }


class Message:
    """
    A message exchanged between application modules.

    A message is defined by the following arguments:

    Args:
        name (str): A name, unique within each application.

        src (str): Name of the module that sends this message.

        dst (str): Name of the module that receives this message.

        instructions (int): Number of instructions to be executed (default 0).
            Instead of MIPS, we use IPT since the time is relative to the
            simulation units.

        bytes (int): Size in bytes (default 0).

    Internal attributes used in :mod:`yafs.core`:

        timestamp (float): Simulation time when the message was created.

        path (list): List of topology entities that the message must traverse
            to reach its destination module from its source module.

        dst_int (int): Identifier of the intermediate entity currently
            processing/transmitting the message.

        app_name (str): Name of the application this message belongs to.
    """

    def __init__(
        self,
        name,
        src,
        dst,
        instructions=0,
        bytes=0,
        broadcasting=False,
    ):
        self.name = name
        self.src = src
        self.dst = dst
        self.inst = instructions
        self.bytes = bytes

        self.timestamp = 0
        self.path = []
        self.dst_int = -1
        self.app_name = None
        self.timestamp_rec = 0

        self.idDES = None
        self.broadcasting = broadcasting
        self.last_idDes = []
        self.id = -1

        # This attribute identifies the user when multiple users are in
        # the same node.
        self.original_DES_src = None

    def __str__(self):
        print("{--")
        print(" Name: %s (%s)" % (self.name, self.id))
        print(" From (src): %s  to (dst): %s" % (self.src, self.dst))
        print(" --}")
        return ""


def fractional_selectivity(threshold, rng=None):
    if rng is None:
        return random.random() <= threshold
    return rng.random() <= threshold


def create_applications_from_json(data):
    applications = {}
    for app in data:
        app = _normalized_mapping(app)
        # Create a new application.
        a = Application(name=app["name"])
        modules = [{"None": {"Type": Application.TYPE_SOURCE}}]
        for module in app["module"]:
            module = _normalized_mapping(module)
            modules.append(
                {
                    module["name"]: {
                        "RAM": module["RAM"],
                        "Type": Application.TYPE_MODULE,
                    }
                }
            )
        a.set_modules(modules)

        ms = {}
        for message in app["message"]:
            message = _normalized_mapping(message)
            # Create the message and register it in the application.
            ms[message["name"]] = Message(
                message["name"],
                message["s"],
                message["d"],
                instructions=message["instructions"],
                bytes=message["bytes"],
            )
            if message["s"] == "None":
                a.add_source_messages(ms[message["name"]])

        for message in app["transmission"]:
            message = _normalized_mapping(message)
            if "message_out" in message.keys():
                a.add_service_module(
                    message["module"],
                    ms[message["message_in"]],
                    ms[message["message_out"]],
                    fractional_selectivity,
                    threshold=1.0,
                )
            else:
                a.add_service_module(message["module"], ms[message["message_in"]])

        applications[app["name"]] = a

    return applications


class Application:
    """
    An application is defined by a DAG of modules that generate, process and
    receive messages.

    Args:
        name (str): Application name. It must be unique within the same
            topology.

    Returns:
        an application

    """
    TYPE_SOURCE = "SOURCE"  # "SENSOR"
    "A source behaves like a sensor."

    TYPE_MODULE = "MODULE"
    "A processing module."

    TYPE_SINK = "SINK"
    "A sink behaves like an actuator."

    def __init__(self, name):
        self.name = name
        self.services = {}
        self.messages = {}
        self.modules = []
        self.modules_src = []
        self.modules_sink = []
        self.data = {}

    def __str__(self):
        print("___ APP. Name: %s" % self.name)
        print(" __ Transmissions ")
        for m in self.messages.values():
            print("\tModule: None : M_In: %s  -> M_Out: %s " % (m.src, m.dst))

        for modulename in self.services.keys():
            m = self.services[modulename]
            print("\t", modulename)
            for ser in m:
                if "message_in" in ser.keys():
                    try:
                        print(
                            "\t\t M_In: %s  -> M_Out: %s "
                            % (ser["message_in"].name, ser["message_out"].name)
                        )
                    except Exception:
                        print(
                            "\t\t M_In: %s  -> M_Out: [NOTHING] "
                            % (ser["message_in"].name)
                        )
        return ""

    def set_modules(self, data):
        """
        Configure the modules belonging to this application.

        Pure source or sink modules must be explicitly typed.

        Args:
            data (dict): A list of module descriptors. Each element is a
                one-key dictionary: ``{module_name: {\"Type\": <TYPE>, ...}}``.
        """
        for module in data:
            name = list(module.keys())[0]
            type_ = list(module.values())[0]["Type"]
            if type_ == self.TYPE_SOURCE:
                self.modules_src.append(name)
            elif type_ == self.TYPE_SINK:
                self.modules_sink = name

            self.modules.append(name)

        self.data = data

    def get_pure_modules(self):
        """
        Return a list of "pure" processing modules.

        These are modules that are neither pure sources nor pure sinks.
        """
        return [
            s
            for s in self.modules
            if s not in self.modules_src and s not in self.modules_sink
        ]

    def get_sink_modules(self):
        """
        Return the list of sink modules.
        """
        return self.modules_sink

    def add_source_messages(self, msg):
        """
        Register messages that originate from pure sources (sensors).

        This distinction allows them to be controlled by the
        :class:`yafs.population.Population` algorithm.
        """
        self.messages[msg.name] = msg

    def get_message(self, name):
        """
        Return a :class:`Message` instance given its identifier ``name``.
        """
        return self.messages[name]

    """
    ADD SERVICE
    """

    def add_service_source(
        self,
        module_name,
        distribution=None,
        message=None,
        module_dest=None,
        p=None,
    ):
        """
        Attach a *source* behaviour to a non-pure module so it can create
        messages.

        Args:
            module_name (str): Module name.

            distribution (callable): A distribution function controlling the
                inter-arrival time of messages.

            message (Message): Message instance to be generated.

            module_dest (list): List of modules that can receive this message
                (broadcast).

            p (list): List of probabilities to send this message to each
                destination (broadcast).

        Kwargs:
            param_distribution (dict): Parameters for the *distribution*
                function.

        """
        module_dest = module_dest or []
        p = p or []

        if distribution is not None:
            if module_name not in self.services:
                self.services[module_name] = []
            self.services[module_name].append(
                {
                    "type": Application.TYPE_SOURCE,
                    "dist": distribution,
                    "message_out": message,
                    "module_dest": module_dest,
                    "p": p,
                }
            )

    def add_service_module(
        self,
        module_name,
        message_in,
        message_out="",
        distribution="",
        module_dest=None,
        p=None,
        **param,
    ):

        """
        Attach a *processing* behaviour to a non-pure module.

        Args:
            module_name (str): Module name.

            message_in (Message): Input message to be processed.

            message_out (Message): Output message. If empty, the module is
                treated as a sink.

            distribution (callable): A distribution function controlling the
                processing time.

            module_dest (list): List of modules that can receive this message
                (broadcast).

            p (list): List of probabilities to send this message to each
                destination (broadcast).

        Kwargs:
            param (dict): Parameters for the *distribution* function.

        """
        module_dest = module_dest or []
        p = p or []

        if module_name not in self.services:
            self.services[module_name] = []

        self.services[module_name].append(
            {
                "type": Application.TYPE_MODULE,
                "dist": distribution,
                "param": param,
                "message_in": message_in,
                "message_out": message_out,
                "module_dest": module_dest,
                "p": p,
            }
        )
