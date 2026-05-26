"""PyArrow schema derived from TelemetryRecord.

Built once, reused for every Parquet file. Stable column types are critical
for query engines to read a multi-file dataset as a single table.

Schema drift is intentional to fail loudly: if TelemetryRecord changes, the
writer will refuse messages that don't match. That forces a deliberate
schema-evolution decision rather than silent corruption.
"""

from __future__ import annotations

from dataclasses import fields

import pyarrow as pa

from orbit_ops.pipeline.messages import TelemetryRecord

# Map dataclass field types to PyArrow types. Keep narrow on purpose; if a
# field type isn't listed here, building the schema will raise and force us
# to decide explicitly.
_TYPE_MAP: dict[type, pa.DataType] = {
    str: pa.string(),
    float: pa.float64(),
    int: pa.int64(),
    bool: pa.bool_(),
}


def build_telemetry_schema() -> pa.Schema:
    """Construct the PyArrow schema for TelemetryRecord."""
    arrow_fields: list[pa.Field] = []
    for f in fields(TelemetryRecord):
        py_type = f.type if isinstance(f.type, type) else _resolve_type_name(f.type)
        if py_type not in _TYPE_MAP:
            raise TypeError(
                f"TelemetryRecord field {f.name!r} has unsupported type {f.type!r}; "
                f"add it to _TYPE_MAP in parquet_schema.py explicitly."
            )
        arrow_fields.append(pa.field(f.name, _TYPE_MAP[py_type], nullable=False))
    return pa.schema(arrow_fields)


def _resolve_type_name(t: object) -> type:
    """Handle string annotations from `from __future__ import annotations`."""
    if isinstance(t, str):
        return {"str": str, "float": float, "int": int, "bool": bool}[t]
    raise TypeError(f"Cannot resolve type {t!r}")


TELEMETRY_SCHEMA: pa.Schema = build_telemetry_schema()
