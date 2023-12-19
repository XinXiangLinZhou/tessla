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
STREAM_NAMES_INPUT = "stream_name_input_1"
TESSLA_SPEC_INPUT = "tessla_spec_input"
# TODO:
# 1) Add the ability to configure multiple entities with corresponding stream names


async def validate_input(hass: HomeAssistant, data: dict) -> dict[str, Any]:

    """Validate the user input"""
    s="["
    hass.stream=[]
    for i in range(hass.num):
        hass.stream.insert(i,data[f"stream_name_input_{i+1}"])
        s+=hass.stream[i]+","
    s+="]"
    streams=s[:-2] + s[-1]
    return {"title":streams}


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
            data_schema = vol.Schema(
                {

                    vol.Required(STREAM_NAMES_INPUT): str,
                    vol.Required(ENTITY_INPUT_1): vol.In(entities),
                    vol.Required(TESSLA_SPEC_INPUT): str,
                }
            )
            errors = {}

            if user_input is not None:
                #sacar el tipo del specification introducido
                specification=user_input[TESSLA_SPEC_INPUT]
                specific_string = 'Events'
                index = specification.find(specific_string)

                if index != -1:
                    sub_content = specification[index + len(specific_string):]
                    substring = sub_content.split(' ')[0]
                    tipo = substring.strip('[]')
                #guardar el tipo del valor del entity
                state=self.hass.states.get(user_input[ENTITY_INPUT_1]).state
                if state.isdigit():
                    type_state="int"
                elif ('.' in state) and (state.replace('.', '', 1).isdigit()):
                    type_state="float"
                else:
                    type_state="str"
                #comparar si son del mismo tipo
                if type_state != tipo.lower():
                    raise Exception(f"El valor del entity debe ser del tipo {tipo}")

                #guardar todos los datos introducido por el usuario a un nuevo diccionario
                d=dict()
                for i,s in enumerate(user_input[STREAM_NAMES_INPUT].split(",")):
                    d.update({f"stream_name_input_{i + 1}":s})
                    self.hass.num=i+1

                for i in range(self.hass.num):
                    d.update({f"entity_input_{i+1}":user_input[ENTITY_INPUT_1]})
                self.hass.sensor=user_input[ENTITY_INPUT_1]
                d.update({"tessla_spec_input":user_input[TESSLA_SPEC_INPUT]})
                print(user_input)
                print(d)
                info = await validate_input(self.hass, d)
                return self.async_create_entry(title=info["title"], data=d)

            return self.async_show_form(step_id="user", data_schema=data_schema)
        except Exception as e:
            print(e)
