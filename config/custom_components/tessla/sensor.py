import time
import threading
import subprocess
import logging
import datetime
import os
import tempfile

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_track_state_change
from pathlib import Path
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, add_entities):
    """Set up the tessla platform"""
    # Start the TeSSLa interpreter process with the given specification file.
    # the spec file needs to be correctly updated before starting the process
    # Path to tessla files

    dir_spec_file = os.path.join("config", "custom_components", "tessla")

    tessla_spec_file = os.path.join(
        "config", "custom_components", "tessla", "specification.tessla"
    )

    tessla_jar_file = os.path.join(
        "config", "custom_components", "tessla", "tessla.jar"
    )
    # 1) Get the data from the config entry
    data = config_entry.data

    # FIXME: I am not sure of the data needs to be saved as part of the `hass`-object.
    # Isn't it sufficient to just keep a local variable here with the lifetime of the running
    # sensor/integration?
    hass.stream = data["stream"]
    hass.sensor = data["entity_input"]
    hass.specification = data["tessla_spec_input"]
    if hass.specification is not None:
        with tempfile.NamedTemporaryFile(
            mode="r+", prefix="tempo_", dir=dir_spec_file, delete=False
        ) as archivo:
            # with open(tessla_spec_file, "w") as archivo:
            # FIXME: clean up code, rename variables, add documentation
            p = hass.specification.split()
            n = []
            p_s = ["def", "out"]

            for i in p:
                if i in p_s:
                    n.append("\n")
                n.append(i)

            result = " ".join(n)
            archivo.write("in h: Events[Unit]\n")
            archivo.write(result)
            archivo.flush()
            # FIXME: logger.debug(), if at all?
            print("escritura con exito")
            tessla_process = subprocess.Popen(
                [
                    "//usr/bin/java",
                    "-jar",
                    tessla_jar_file,
                    "interpreter",
                    # tessla_spec_file,
                    archivo.name,  # tempo file
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,  # Linebuffer!
                universal_newlines=True,
            )
            hass.spec = []
            # with open(tessla_spec_file, "r") as file:  # tempo file
            archivo.seek(0)
            content = archivo.read()

            # FIXME: this looks like a loop over every byte of the input file? This is not efficient.
            # It probably also picks up more `out` than it should, e.g. in the middle of identifiers.
            # Either go through it line-by-line, and check that the line starts with `out`, or (better)
            # use the regexp-library to find `out ` (note the trailing white-space!).
            specific_string = "out"
            indices = [
                i for i in range(len(content)) if content.startswith(specific_string, i)
            ]

            if indices:
                for i, index in enumerate(indices):
                    substring = content[index + len(specific_string) :]
                    hass.spec.insert(i, substring.split()[0])
            archivo.close()
    _LOGGER.info("Tessla started")

    _LOGGER.warning(f"Config entry said: {config_entry.data}")

    # TODO: Config flow:

    # 2) Create a list of the the entities with corresponding stream names.
    # 3) Add entities in HA.
    # 4) Refactor the code below by removing all hardcoded stuff, everything should be set up from the config entry
    # 5) Get the specification from the config entry and write it to the specification.tessla file

    def tlogger():
        for e in tessla_process.stderr:
            _LOGGER.error(f"Tessla failed: {e}")

    threading.Thread(target=tlogger).start()

    ts = TesslaSensor(hass, tessla_process)
    add_entities([ts])
    # Create a separate thread to read and print the TeSSLa output.
    tessla_reader_thread = threading.Thread(
        target=TesslaReader(hass, tessla_process).output
    )
    # start thread
    tessla_reader_thread.start()

    # Set the reader thread to TesslaSensor
    ts.set_output_thread(tessla_reader_thread)

    async def _async_state_changed(entity_id, old_state, new_state):
        if new_state is None:
            return
        # when state of sensor =unknown or none
        if old_state is None:
            return
        if new_state.state.isdigit():
            coma = ""
        elif ("." in new_state.state) and (
            new_state.state.replace(".", "", 1).isdigit()
        ):
            coma = ""
        else:
            coma = '"'
        utc_timestamp = new_state.last_changed
        timestamp = round(
            datetime.datetime.fromisoformat(str(utc_timestamp)).timestamp() * 10000
        )

        tessla_process.stdin.write(
            f"{timestamp}: x = {coma}{(new_state.state)}{coma}\n"
            f"{timestamp + 1}: h\n"
        )
        _LOGGER.warning(f"Tessla notified, value: {new_state}")
        _LOGGER.warning(f"{timestamp}: x = {coma}{(new_state.state)}{coma}\n")

    # Register a state change listener for the "sensor.random_sensor" entity
    # TODO: do this for every entity in the config_entry

    for i, sensor in enumerate(hass.sensor):
        async_track_state_change(hass, sensor, _async_state_changed)


class TesslaSensor(SensorEntity):
    """The tesslasensor class"""

    _attr_should_poll = False

    def __init__(self, hass, process):
        self._state = "-1"
        # FIXME: Unused? Or document.
        self._hass = hass
        self.tessla = process
        self.j = 1
        self.t = None
        # FIXME: Unused? Or document.
        self.running = False

    def set_output_thread(self, t):
        """Set the output thread"""
        self.t = t

    @property
    def name(self):
        return "tessla"

    @property
    def state(self):
        if not self.running and self.t is not None:
            self.running = True
            self._state = "Running"
        return self._state


class TesslaReader:
    """The tesslareader class"""

    def __init__(self, hass, tessla):
        self.tessla = tessla
        self.hass = hass

    def output(self):
        """Handles the tessla output"""
        # FIXME: some of these should probably be `LOGGER.debug`.
        _LOGGER.info("Waiting for Tessla output.")
        # TODO: Replace this with the list from the config entry

        # add stream to ostreams for output
        ostreams = {}
        # FIXME: don't use `hass`-object, pass `spec` in constructor instead?
        for spec in self.hass.spec:
            ostreams.update({spec: spec})
        s = ""
        # FIXME: ditto
        for i in self.hass.stream:
            s += i
            s += "_"

        for line in self.tessla.stdout:
            _LOGGER.info(f"Tessla said: {line.strip()}.")
            parts = line.strip().split(" = ")
            if len(parts) != 2:
                _LOGGER.warning("Invalid output format from Tessla: %s", line.strip())
                continue
            output_name = parts[0].split(": ")[1]
            # Only do something if the output has been configured
            if output_name in ostreams:
                value = parts[1]
                entity_id = f"{DOMAIN}.{s}{ostreams[output_name]}"
                entity_state = value.strip()
                self.hass.states.set(entity_id, entity_state)
                # FIXME: message misleading, we're only posting a state-update.
                _LOGGER.warning("Created new entity: %s=%s", entity_id, entity_state)

            else:
                _LOGGER.warning("Ignored event (No mapping for this output stream))")
