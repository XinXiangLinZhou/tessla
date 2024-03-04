import voluptuous as vol
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
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
# TODO:
# 1) Add the ability to configure multiple entities with corresponding stream names


# error message
async def show_error_notification(hass, error_message):
    await hass.services.async_call(
        "persistent_notification",
        "create",
        {"title": "Error", "message": error_message},
    )


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
                # guardar todos los datos introducido por el usuario a un nuevo diccionario
                d = dict()
                stream = []
                # add stream to data
                for i, s in enumerate(user_input[STREAM_NAMES_INPUT].split(",")):
                    stream.insert(i, s)

                def has_duplicates(list):
                    l = set()
                    for item in list:
                        if item in l:
                            return True
                        l.add(item)
                    return False

                # if are same name of streams return error
                if has_duplicates(stream):
                    error_message = f"ERROR: The name of the streams must be diferent\n"
                    for i, s in enumerate(stream):
                        error_message += f"stream{i+1}:{s}\n"
                    await show_error_notification(self.hass, error_message)
                d.update({"stream": stream})

                # add all entity_input to data
                entity_input = []
                entity_input.insert(0, user_input[ENTITY_INPUT_1])
                if user_input[ENTITY_INPUT_2] is not None:
                    entity_input.insert(1, user_input[ENTITY_INPUT_2])
                if user_input[ENTITY_INPUT_3] is not None:
                    entity_input.insert(2, user_input[ENTITY_INPUT_3])

                d.update({"entity_input": entity_input})
                # sacar el tipo del specification introducido
                specification = user_input[TESSLA_SPEC_INPUT]
                specific_string = "Events"
                index = [
                    i
                    for i in range(len(specification))
                    if specification.startswith(specific_string, i)
                ]
                if index:
                    for i, ind in enumerate(index):
                        sub_content = specification[ind + len(specific_string) :]
                        substring = sub_content.split(" ")[0]
                        tipo = substring.strip("[]")

                        # guardar el tipo del valor del entity
                        state = self.hass.states.get(entity_input[i]).state
                        if state.isdigit():
                            type_state = "int"
                        elif ("." in state) and (state.replace(".", "", 1).isdigit()):
                            type_state = "float"
                        else:
                            type_state = "string"
                        # comparar si son del mismo tipo
                        if type_state != tipo.lower():
                            error_message = (
                                f"ERROR:The value of the entity{i+1} must be the type {tipo}\n"
                                f"Entity Type{i+1}({entity_input[i]}): {type_state}\n"
                            )
                            await show_error_notification(self.hass, error_message)
                            raise Exception(error_message)
                if len(entity_input) != len(index):
                    error_message = (
                        f"ERROR: Number of the chosen entity does not match the input number of the file specification.tessla\n"
                        f"entity: {entity_input}\n"
                        f"Input number of the file: {len(index)}\n"
                    )
                    await show_error_notification(self.hass, error_message)
                # add specification to data
                d.update({"tessla_spec_input": user_input[TESSLA_SPEC_INPUT]})
                info = await validate_input(self.hass, d)

                return self.async_create_entry(title=info["title"], data=d)

            return self.async_show_form(step_id="user", data_schema=data_schema)
        except Exception as e:
            print(e)
