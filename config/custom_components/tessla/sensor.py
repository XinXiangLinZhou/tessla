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
import re

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
    stream = data["stream"]
    sensor = data["entity_input"]
    specification = data["tessla_spec_input"]
    if specification is not None:
        with tempfile.NamedTemporaryFile(
            mode="r+", prefix="tempo_", dir=dir_spec_file, delete=False
        ) as archivo:
            p = specification.split()
            n = []
            p_s = ["in", "def", "out"]
            for i in p:
                if i in p_s:
                    n.append(f"\n{i}")
                else:
                    n.append(f" {i}")

            result = "".join(n)
            archivo.write("in h: Events[Unit]")
            archivo.write(result)
            archivo.flush()
            print("escritura con exito")
            tessla_process = subprocess.Popen(
                [
                    "//usr/bin/java",
                    "-jar",
                    tessla_jar_file,
                    "interpreter",
                    archivo.name,  # tempo file
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,  # Linebuffer!
                universal_newlines=True,
            )
            # with open(tessla_spec_file, "r") as file:  # tempo file
            archivo.seek(0)

            # get string after out and in of the file specification
            content = archivo.read()
            specific_out = [
                re.findall(r"^out\s(.+?)(?:\s|$)", linea)[0]
                for linea in content.split("\n")
                if re.findall(r"^out\s(.+?)(?:\s|$)", linea)
            ]

            specific_in = [
                re.findall(r"^in\s(.+?)(:)", linea)[0][0]
                for linea in content.split("\n")
                if re.findall(r"^in\s(.+?)(:)", linea)
            ]
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
        target=TesslaReader(hass, tessla_process, specific_out, stream).output
    )
    # start thread
    tessla_reader_thread.start()

    # Set the reader thread to TesslaSensor
    ts.set_output_thread(tessla_reader_thread)

    async def _async_state_changed(entity_id, old_state, new_state):
        # get witch sensor of integration is change
        if new_state is None:
            return
        if old_state is None:
            return
        # when state of sensor =unknown or none
        if new_state.state == "unavailable" or new_state.state == "unknown":
            return
        # when sensor state is the type string, we need add ""
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
        s = sensor.index(entity_id)
        tessla_process.stdin.write(
            # specific_in[0]=h
            f"{timestamp}: {specific_in[s+1]} = {coma}{(new_state.state)}{coma}\n"
            f"{timestamp + 1}: h\n"
        )
        _LOGGER.warning(f"Tessla notified, value: {new_state}")
        _LOGGER.warning(f"{timestamp}: x = {coma}{(new_state.state)}{coma}\n")

    # Register a state change listener for the "sensor.random_sensor" entity
    # TODO: do this for every entity in the config_entry

    for s in sensor:
        async_track_state_change(hass, s, _async_state_changed)


class TesslaSensor(SensorEntity):
    """The tesslasensor class"""

    _attr_should_poll = False

    def __init__(self, hass, process):
        self._state = "-1"
        self.tessla = process
        self.t = None
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

    def __init__(self, hass, tessla, spec, stream):
        self.tessla = tessla
        self.hass = hass
        self.spec = spec
        self.stream = stream

    def output(self):
        """Handles the tessla output"""
        _LOGGER.info("Waiting for Tessla output.")
        # TODO: Replace this with the list from the config entry

        # add stream to ostreams for output
        ostreams = {}
        for spec in self.spec:
            ostreams.update({spec: spec})
        s = ""
        for i in self.stream:
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
                _LOGGER.info("Update entity: %s=%s", entity_id, entity_state)

            else:
                _LOGGER.warning("Ignored event (No mapping for this output stream))")

