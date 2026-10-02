"""How a grid point is put to Jev: coordinate formats, layouts, and question builders.

A "layout" decides where the coordinate goes:
- "state":    one point per request; the coordinate is the state, the question is generic.
- "question": many points per request; a generic state, the coordinate is inside each question.
"""

from typesafe_sdk import Choice, Noul

from jevmap import geo


def _num(x: float) -> str:
    return f"{x:g}"


def fmt_coord(lat: float, lon: float, style: str) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    if style == "decimal":
        return f"latitude {_num(lat)}, longitude {_num(lon)}"
    if style == "hemi":
        return f"{_num(abs(lat))}°{ns}, {_num(abs(lon))}°{ew}"
    if style == "words":
        ns_w = "north" if lat >= 0 else "south"
        ew_w = "east" if lon >= 0 else "west"
        return f"{_num(abs(lat))} degrees {ns_w}, {_num(abs(lon))} degrees {ew_w}"
    raise ValueError(style)


# --- Experiment 1: land / water (Noul) -------------------------------------------------------------

LAND_STATE_GENERIC = "Locations on the surface of the Earth, given as latitude and longitude."


def land_state_point(coord: str) -> str:
    return f"A location on the surface of the Earth at {coord}."


LAND_QUESTION_GENERIC = "This location is on land, not in an ocean, sea or lake."


def land_question_point(coord: str) -> Noul:
    return Noul(instructions=f"The location at {coord} is on land, not in an ocean, sea or lake.")


# --- Experiment 2: physical map (Choice over elevation bands) --------------------------------------

PHYSICAL_TERRAIN = {
    "deep_ocean": ("Deep ocean", "Ocean deeper than 3,000 m"),
    "open_ocean": ("Ocean", "Ocean 200 to 3,000 m deep"),
    "shallow_sea": ("Shallow sea or lake", "Sea less than 200 m deep, continental shelf, or a lake"),
    "lowland": ("Lowland", "Land below 200 m above sea level"),
    "hills": ("Hills", "Land 200 to 500 m above sea level"),
    "upland": ("Upland or plateau", "Land 500 to 1,500 m above sea level"),
    "mountains": ("Mountains", "Land 1,500 to 3,000 m above sea level"),
    "high_mountains": ("High mountains or ice plateau", "Land more than 3,000 m above sea level"),
}

PHYSICAL_COLOURS = {
    "deep_ocean": "dark blue",
    "open_ocean": "medium blue",
    "shallow_sea": "light blue",
    "lowland": "dark green",
    "hills": "light green",
    "upland": "yellow",
    "mountains": "brown",
    "high_mountains": "dark brown",
}


def physical_criteria(variant: str) -> dict[str, str | None]:
    """Choice criteria keyed by the label Jev sees; map back with `physical_label_to_band`."""
    if variant == "terrain":
        return {label: desc for label, desc in PHYSICAL_TERRAIN.values()}
    if variant == "colour":
        return {colour: None for colour in PHYSICAL_COLOURS.values()}
    raise ValueError(variant)


def physical_label_to_band(variant: str) -> dict[str, str]:
    if variant == "terrain":
        return {label: b for b, (label, _) in PHYSICAL_TERRAIN.items()}
    return {colour: b for b, colour in PHYSICAL_COLOURS.items()}


PHYSICAL_INSTRUCTIONS = {
    "terrain": "What is the terrain or sea depth at this location?",
    "colour": "On a classic physical atlas map coloured by elevation and sea depth, what colour is this location?",
}


def physical_question(variant: str, coord: str | None) -> Choice:
    text = PHYSICAL_INSTRUCTIONS[variant]
    if coord is not None:
        text = text.replace("this location", f"the location at {coord}")
    return Choice(instructions=text, criteria=physical_criteria(variant))


# --- Experiment 3: political map (Choice over countries) -------------------------------------------

POLITICAL_INSTRUCTIONS = "Which country or territory is this location in?"


def political_criteria() -> dict[str, str | None]:
    crit: dict[str, str | None] = {name: None for name in geo.country_names()}
    crit[geo.OCEAN] = "Open sea, outside the land territory of every country"
    return crit


def political_question(coord: str | None) -> Choice:
    text = POLITICAL_INSTRUCTIONS
    if coord is not None:
        text = text.replace("this location", f"the location at {coord}")
    return Choice(instructions=text, criteria=political_criteria())


# --- Exploratory (phase 5): other ways to ask land / water -----------------------------------------

OCEANS = ["Arctic Ocean", "Atlantic Ocean", "Indian Ocean", "Pacific Ocean", "Southern Ocean"]


def continent_question(coord: str | None) -> Choice:
    text = "Which continent or ocean is this location in?"
    if coord is not None:
        text = f"Which continent or ocean is the location at {coord} in?"
    crit: dict[str, str | None] = {c: None for c in geo.CONTINENTS + OCEANS}
    crit["Oceania"] = "Australia, New Zealand and the Pacific islands (land)"
    return Choice(instructions=text, criteria=crit)


def land_choice_question(coord: str | None) -> Choice:
    text = "Is this location on land or in water?"
    if coord is not None:
        text = f"Is the location at {coord} on land or in water?"
    return Choice(instructions=text, criteria={"land": None, "water": "Ocean, sea or lake"})


# --- Original "blind model" wording (outsidetext.substack.com/p/how-does-a-blind-model-see-the-earth) ---

ORIG_INSTRUCTIONS = "If this location is over land, say 'Land'. If this location is over water, say 'Water'."


def orig_choice_question(coord: str | None) -> Choice:
    text = ORIG_INSTRUCTIONS if coord is None else f"{ORIG_INSTRUCTIONS} {coord}"
    return Choice(instructions=text, criteria={"Land": None, "Water": None})


def orig_noul_question(coord: str | None) -> Noul:
    text = "This location is over land." if coord is None else f"The location {coord} is over land."
    return Noul(instructions=text)
