"""Claude API tool definitions for military command parsing.

Each tool maps to a CommandType. Claude's tool-calling picks the right one
based on the operator's natural language transcript.
"""

TOOLS = [
    {
        "name": "move_vehicle",
        "description": (
            "Move a vehicle to a specified location. Use for commands like "
            "'move to', 'proceed to', 'advance to', 'go to', 'head to', "
            "'relocate to', 'reposition to'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "callsign": {
                    "type": "string",
                    "description": "Vehicle callsign (e.g. 'UAV-1', 'UGV-2', 'USV-1') or alias (e.g. 'Alpha', 'the drone')",
                },
                "lat": {
                    "type": "number",
                    "description": "Target latitude in decimal degrees",
                },
                "lon": {
                    "type": "number",
                    "description": "Target longitude in decimal degrees",
                },
                "alt_m": {
                    "type": "number",
                    "description": "Target altitude in meters (for air vehicles). Default 100m for UAVs, 0 for ground/sea.",
                },
                "grid_ref": {
                    "type": "string",
                    "description": "Military grid reference if given instead of lat/lon",
                },
            },
            "required": ["callsign"],
        },
    },
    {
        "name": "return_to_base",
        "description": (
            "Return a vehicle to its home/launch position. Use for 'RTB', "
            "'return to base', 'come home', 'return home', 'bring it back', "
            "'abort', 'abort mission', 'abort all', 'abort all missions', "
            "'emergency RTB', 'recall', 'stand down'. Use callsign='all' to recall all vehicles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "callsign": {
                    "type": "string",
                    "description": "Vehicle callsign or 'all' for all vehicles",
                },
            },
            "required": ["callsign"],
        },
    },
    {
        "name": "set_overwatch",
        "description": (
            "Position a vehicle at a location to observe/monitor an area. "
            "Use for 'overwatch', 'observe', 'watch over', 'monitor', "
            "'establish overwatch', 'surveillance position'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "callsign": {
                    "type": "string",
                    "description": "Vehicle callsign",
                },
                "lat": {
                    "type": "number",
                    "description": "Overwatch position latitude",
                },
                "lon": {
                    "type": "number",
                    "description": "Overwatch position longitude",
                },
                "alt_m": {
                    "type": "number",
                    "description": "Overwatch altitude in meters (UAVs typically 80-150m)",
                },
                "grid_ref": {
                    "type": "string",
                    "description": "Military grid reference if given",
                },
            },
            "required": ["callsign"],
        },
    },
    {
        "name": "patrol_route",
        "description": (
            "Set a vehicle on a patrol route through multiple waypoints. "
            "Use for 'patrol', 'sweep', 'patrol route', 'patrol between', "
            "'patrol perimeter', 'sweep area'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "callsign": {
                    "type": "string",
                    "description": "Vehicle callsign",
                },
                "waypoints": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number"},
                            "lon": {"type": "number"},
                            "alt_m": {"type": "number"},
                        },
                        "required": ["lat", "lon"],
                    },
                    "description": "Ordered list of waypoints to patrol through",
                },
            },
            "required": ["callsign", "waypoints"],
        },
    },
    {
        "name": "loiter_at",
        "description": (
            "Have a vehicle loiter (circle/hold) at a position for a duration. "
            "Use for 'loiter', 'hold position', 'circle', 'orbit', 'hover', "
            "'hold at', 'wait at', 'station keep'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "callsign": {
                    "type": "string",
                    "description": "Vehicle callsign",
                },
                "lat": {
                    "type": "number",
                    "description": "Loiter position latitude",
                },
                "lon": {
                    "type": "number",
                    "description": "Loiter position longitude",
                },
                "alt_m": {
                    "type": "number",
                    "description": "Loiter altitude in meters",
                },
                "duration_min": {
                    "type": "number",
                    "description": "How long to loiter in minutes. Default 10.",
                },
            },
            "required": ["callsign"],
        },
    },
    {
        "name": "classify_contact",
        "description": (
            "Classify or reclassify a tracked contact's IFF status. "
            "Use for 'classify', 'mark as', 'designate as', 'identify as', "
            "'reclassify', 'tag as hostile/friendly/unknown/neutral'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_uid": {
                    "type": "string",
                    "description": "UID or name of the contact to classify (e.g. 'alpha-7', 'contact-3')",
                },
                "new_affiliation": {
                    "type": "string",
                    "enum": ["friendly", "hostile", "unknown", "neutral"],
                    "description": "New IFF classification",
                },
            },
            "required": ["contact_uid", "new_affiliation"],
        },
    },
    {
        "name": "request_status",
        "description": (
            "Request status report from one or all vehicles. "
            "Use for 'status', 'report', 'sitrep', 'how is', 'where is', "
            "'what is the status of', 'give me a status'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "callsign": {
                    "type": "string",
                    "description": "Vehicle callsign, or 'all' for fleet-wide status",
                },
            },
            "required": ["callsign"],
        },
    },
    {
        "name": "engage_target",
        "description": (
            "Order a vehicle to engage (track/intercept) a hostile target. "
            "CRITICAL RISK — always requires voice confirmation. "
            "Use for 'engage', 'intercept', 'neutralize', 'attack', 'weapons free on'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "callsign": {
                    "type": "string",
                    "description": "Vehicle callsign to execute engagement",
                },
                "target_uid": {
                    "type": "string",
                    "description": "UID of the hostile contact to engage",
                },
            },
            "required": ["callsign", "target_uid"],
        },
    },
    {
        "name": "takeoff_vehicle",
        "description": (
            "Command an air vehicle (UAV) to take off to a specified altitude. "
            "Use for 'take off', 'takeoff', 'launch', 'get airborne', 'lift off', "
            "'spin up and take off'. Only applies to air vehicles (copters)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "callsign": {
                    "type": "string",
                    "description": "Vehicle callsign (must be an air vehicle / UAV)",
                },
                "alt_m": {
                    "type": "number",
                    "description": "Target altitude in meters. Default 20m if not specified.",
                },
            },
            "required": ["callsign"],
        },
    },
    {
        "name": "land_vehicle",
        "description": (
            "Command a vehicle to land at its current position. "
            "Use for 'land', 'touch down', 'set down', 'bring it down', "
            "'land now', 'put it on the ground'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "callsign": {
                    "type": "string",
                    "description": "Vehicle callsign or 'all' for all vehicles",
                },
            },
            "required": ["callsign"],
        },
    },
]

# Map tool names to CommandType values
TOOL_TO_COMMAND_TYPE = {
    "move_vehicle": "move",
    "return_to_base": "rtb",
    "set_overwatch": "overwatch",
    "patrol_route": "patrol",
    "loiter_at": "loiter",
    "classify_contact": "classify",
    "request_status": "status",
    "engage_target": "engage",
    "takeoff_vehicle": "takeoff",
    "land_vehicle": "land",
}
