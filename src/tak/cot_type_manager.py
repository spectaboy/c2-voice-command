"""Mapping between domain/affiliation and MIL-STD-2525 CoT type strings.

CoT type string format: ``a-{affiliation}-{domain_code}...``

Position index 2 (the second dash-delimited segment) carries the affiliation
character:

* ``f`` -- friendly
* ``h`` -- hostile
* ``u`` -- unknown
* ``n`` -- neutral
"""

from typing import Dict, Tuple

VALID_AFFILIATIONS: set[str] = {"f", "h", "u", "n"}

COT_TYPES: Dict[Tuple[str, str], str] = {
    ("air", "f"):      "a-f-A-M-F-Q-r",   # Friendly UAV
    ("air", "h"):      "a-h-A-M-F-Q-r",   # Hostile UAV
    ("air", "u"):      "a-u-A",            # Unknown air
    ("ground", "f"):   "a-f-G-E-V",        # Friendly ground vehicle
    ("ground", "h"):   "a-h-G-E-V",        # Hostile ground vehicle
    ("ground", "u"):   "a-u-G",            # Unknown ground
    ("maritime", "f"): "a-f-S-X",           # Friendly surface vessel
    ("maritime", "h"): "a-h-S-X",           # Hostile surface vessel
    ("maritime", "u"): "a-u-S",             # Unknown sea surface
    ("air", "n"):      "a-n-A",            # Neutral air
    ("ground", "n"):   "a-n-G",            # Neutral ground
    ("maritime", "n"): "a-n-S",            # Neutral sea surface
}


def get_cot_type(domain: str, affiliation: str) -> str:
    """Look up the CoT type string for a *domain* and *affiliation* pair.

    Parameters
    ----------
    domain:
        One of ``"air"``, ``"ground"``, or ``"maritime"``.
    affiliation:
        One of ``"f"`` (friendly), ``"h"`` (hostile), ``"u"`` (unknown),
        or ``"n"`` (neutral).

    Returns
    -------
    str
        The corresponding CoT type string, e.g. ``"a-f-A-M-F-Q-r"``.

    Raises
    ------
    ValueError
        If the *(domain, affiliation)* pair is not present in
        :data:`COT_TYPES`.
    """
    key: Tuple[str, str] = (domain, affiliation)
    if key not in COT_TYPES:
        raise ValueError(
            f"No CoT type defined for domain={domain!r}, "
            f"affiliation={affiliation!r}"
        )
    return COT_TYPES[key]


def update_affiliation_in_cot_type(
    current_type: str, new_affiliation: str
) -> str:
    """Return a new CoT type string with the affiliation character replaced.

    The affiliation sits at segment index 1 (the second dash-delimited
    segment) of a CoT type string.  For example::

        update_affiliation_in_cot_type("a-f-G-E-V", "h")
        # => "a-h-G-E-V"

    Parameters
    ----------
    current_type:
        An existing CoT type string such as ``"a-f-G-E-V"``.
    new_affiliation:
        The replacement affiliation character -- one of ``"f"``, ``"h"``,
        ``"u"``, or ``"n"``.

    Returns
    -------
    str
        The updated CoT type string.

    Raises
    ------
    ValueError
        If *new_affiliation* is not a recognised affiliation character.
    """
    if new_affiliation not in VALID_AFFILIATIONS:
        raise ValueError(
            f"Invalid affiliation {new_affiliation!r}. "
            f"Must be one of {sorted(VALID_AFFILIATIONS)}."
        )

    parts: list[str] = current_type.split("-")
    parts[1] = new_affiliation
    return "-".join(parts)


def extract_affiliation(cot_type: str) -> str:
    """Extract the affiliation character from a CoT type string.

    Parameters
    ----------
    cot_type:
        A CoT type string such as ``"a-f-A-M-F-Q-r"``.

    Returns
    -------
    str
        The single-character affiliation code (e.g. ``"f"``).
    """
    return cot_type.split("-")[1]
