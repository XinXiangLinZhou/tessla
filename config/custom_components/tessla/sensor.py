import time
import threading
import subprocess
import logging
import datetime
import os

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

    tessla_spec_file = os.path.join(
        "config", "custom_components", "tessla", "specification.tessla"
    )

    tessla_jar_file = os.path.join(
        "config", "custom_components", "tessla", "tessla.jar"
    )
    # 1) Get the data from the config entry
    data = config_entry.data

    hass.stream=data["stream"]
    hass.sensor=data["entity_input"]
    hass.specification= data["tessla_spec_input"]
    print(data["stream"])
    if hass.specification is not None:
        with open(tessla_spec_file, "w") as archivo:
            p = hass.specification.split()
            n = []
            p_s = ["def", "out"]

            for i in p:
                if i in p_s:
                    n.append("\n")
                n.append(i)

            result = " ".join(n)
            archivo.write(result)
            print("escritura con exito")
    archivo.close()

    tessla_process = subprocess.Popen(
        [
            "//usr/bin/java",
            "-jar",
            tessla_jar_file,
            "interpreter",
            tessla_spec_file,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,  # Linebuffer!
        universal_newlines=True,
    )

    #get the string after out in specification file
    hass.spec=[]
    with open( tessla_spec_file, 'r') as file:
        content = file.read()
    specific_string = 'out'
    indices = [i for i in range(len(content)) if content.startswith(specific_string, i)]
    if indices:
        for i,index in enumerate(indices):
            substring = content[index + len(specific_string):]
            hass.spec.insert(i,substring.split()[0])

    file.close()
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
    tessla_reader_thread = threading.Thread(target=TesslaReader(hass, tessla_process).output)

    # Set the reader thread to TesslaSensor
    ts.set_output_thread(tessla_reader_thread)

    async def _async_state_changed(entity_id, old_state, new_state):
        if new_state is None:
            return
        utc_timestamp = new_state.last_changed
        timestamp = round(
            datetime.datetime.fromisoformat(str(utc_timestamp)).timestamp() * 10000
        )
        if old_state is None:
            return
        tessla_process.stdin.write(f"{timestamp}: x = {int(new_state.state)}\n")
        _LOGGER.warning(f"Tessla notified, value: {new_state}")

    # Register a state change listener for the "sensor.random_sensor" entity
    # TODO: do this for every entity in the config_entry
    for sensor in hass.sensor:
        async_track_state_change(hass, sensor, _async_state_changed)




class TesslaSensor(SensorEntity):
    """The tesslasensor class"""

    _attr_should_poll = False

    def __init__(self, hass, process):
        self._state = "-1"
        self._hass = hass
        self.tessla = process
        self.j = 1
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
            self.t.start()
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
        _LOGGER.info("Waiting for Tessla output.")
        # TODO: Replace this with the list from the config entry

        #add stream to ostreams for output
        ostreams={}
        stream=len(self.hass.stream)
        s=self.hass.stream
        for i in range(stream):
            r=self.hass.spec[i]
            ostreams.update({r:s[i]})

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
                entity_id = f"{DOMAIN}.{ostreams[output_name]}"
                entity_state = value.strip()
                self.hass.states.set(entity_id, entity_state)

                _LOGGER.warning("Created new entity: %s=%s", entity_id, entity_state)
            else:
                _LOGGER.warning("Ignored event (No mapping for this output stream))")
