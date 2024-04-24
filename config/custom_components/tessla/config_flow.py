import voluptuous as vol
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
import re
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

ENTITY_INPUT_1 = "entity_input_1"
ENTITY_INPUT_2 = "entity_input_2"
ENTITY_INPUT_3 = "entity_input_3"
STREAM_NAMES_INPUT = "stream_name_input_1"
TESSLA_SPEC_INPUT = "tessla_spec_input"


# error message
async def show_error_notification(self, error_message):
    await self.hass.services.async_call(
        "persistent_notification",
        "create",
        {"title": "Error", "message": error_message},
    )


# Add the ability to configure multiple entities with corresponding stream names
async def validate_input(hass: HomeAssistant, data: dict) -> dict[str, Any]:
    """Validate the user input"""
    s = "["
    for i in data["stream"]:
        s += i + ","
    s += "]"
    streams = s[:-2] + s[-1]
    return {"title": streams}


class TesslaFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a TeSSLa config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        try:
            entities = []
            for entity in self.hass.states.async_all():
                entities.append(entity.entity_id)
            entities.sort()
            entities.insert(0, None)
            data_schema = vol.Schema(
                {
                    vol.Required(STREAM_NAMES_INPUT): str,
                    vol.Required(ENTITY_INPUT_1): vol.In(entities),
                    vol.Required(ENTITY_INPUT_2): vol.In(entities),
                    vol.Required(ENTITY_INPUT_3): vol.In(entities),
                    vol.Required(TESSLA_SPEC_INPUT): str,
                }
            )
            errors = {}

            if user_input is not None:
                # Save all data entered by the user to a new dictionary
                d = dict()
                stream = []
                # add stream to data
                for i, s in enumerate(user_input[STREAM_NAMES_INPUT].split(",")):
                    stream.insert(i, s)

                def has_duplicates(list_data):
                    l = set()
                    for item in list_data:
                        if item in l:
                            return True
                        l.add(item)
                    return False

                # if are same name of streams return error
                if has_duplicates(stream):
                    error_message = f"ERROR: The name of the streams must be diferent\n"
                    for i, s in enumerate(stream):
                        error_message += f"stream{i+1}:{s}\n"
                    raise ValueError(error_message)
                d.update({"stream": stream})

                # add all entity_input to data
                entity_input = []
                if user_input[ENTITY_INPUT_1] is not None:
                    entity_input.insert(0, user_input[ENTITY_INPUT_1])
                else:
                    error_message = f"ERROR: Must have an entity assigned\n"
                    raise ValueError(error_message)
                if user_input[ENTITY_INPUT_2] is not None:
                    entity_input.insert(1, user_input[ENTITY_INPUT_2])
                if user_input[ENTITY_INPUT_3] is not None:
                    entity_input.insert(2, user_input[ENTITY_INPUT_3])
                # if assign same entitys return error
                if has_duplicates(entity_input):
                    error_message = f"ERROR: The entitys must be diferent\n"
                    for i, e in enumerate(entity_input):
                        error_message += f"Entity{i+1}:{e}\n"
                    raise ValueError(error_message)
                d.update({"entity_input": entity_input})

                # Error when number of stream and number of entity are direfent
                if len(entity_input) != len(stream):
                    error_message = (
                        f"ERROR: Number of the chosen entity does not match number of stream\n"
                        f"Entity: {entity_input}\n"
                        f"Stream: {stream}\n"
                    )
                    raise ValueError(error_message)
                # get the type of the entered specification
                specification = user_input[TESSLA_SPEC_INPUT]
                p = specification.split()
                n = []
                p_s = ["in", "def", "out"]
                for i in p:
                    if i in p_s:
                        n.append(f"\n{i}")
                    else:
                        n.append(f" {i}")
                spec = "".join(n)
                spec_type = [
                    re.findall(r"\[(.+?)\]", linea)[0]
                    for linea in spec.split("\n")
                    if re.findall(r"^in\s(.+?)(:)", linea)
                    and re.findall(r"\[(.+?)\]", linea)
                ]
                # ERROR when Number of entity does not match the input number of the file specification.tessla
                if len(entity_input) != len(spec_type):
                    error_message = (
                        f"ERROR: Number of the chosen entity does not match the input number of the file specification.tessla\n"
                        f"entity: {entity_input}\n"
                        f"Input number of the file: {len(spec_type)}\n"
                    )
                    raise ValueError(error_message)
                if spec_type:
                    for i, tipo in enumerate(spec_type):
                        # save the type of the entity value
                        state = self.hass.states.get(entity_input[i]).state
                        if state.isdigit():
                            type_state = "int"
                        elif ("." in state) and (state.replace(".", "", 1).isdigit()):
                            type_state = "float"
                        elif state in ("true", "false"):
                            type_state = "bool"
                        else:
                            type_state = "string"
                        # Error when they are the different type
                        if type_state != tipo.lower():
                            error_message = (
                                f"ERROR:The value of the entity{i+1} must be the type {tipo}\n"
                                f"State of entity{i+1}({entity_input[i]}):{state}\n"
                                f"Type of entity{i+1}({entity_input[i]}): {type_state}\n"
                            )
                            raise ValueError(error_message)

                # add specification to data
                d.update({"tessla_spec_input": spec})
                info = await validate_input(self.hass, d)

                return self.async_create_entry(title=info["title"], data=d)

            return self.async_show_form(step_id="user", data_schema=data_schema)
        except ValueError as e:
            error_message = str(e)
            await show_error_notification(self, error_message)
            return self.async_abort(reason=e)
