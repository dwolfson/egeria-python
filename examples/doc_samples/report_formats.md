# Report Formats: Usage Guide

This guide explains how to use pyegeria’s report formats system, including:
- Selecting and listing report formats
- Loading additional report formats dynamically (no server restart required)
- Registering/unregistering formats at runtime
- Understanding the attributes-first model (formerly columns)
- Migration notes from report_spec → report_format

## Concepts

- Report Format (formerly called report_spec): A named bundle that describes how a kind of object should be presented in different output types (e.g., DICT, TABLE, MD, REPORT, MERMAID, etc.).
- Format: A single presentation configuration within a report format, usually scoped to one or more output types.
- Attributes: The data points to include in the presentation (previously referred to as columns). The term columns remains as a backward-compatible alias.

The core models are defined in pyegeria/_output_format_models.py:
- Attribute (alias of Column)
- Format (types + attributes)
- FormatSet (a collection of Format entries with metadata like heading, description, aliases)

## Quick Start: Selecting a Report Format

```python
from pyegeria.base_report_formats import select_report_format, report_format_list, get_report_format_heading

# List all available report formats
labels = report_format_list()
print(labels[:5])

# Select a particular report format for a given output type
fmt = select_report_format("Referenceable", "DICT")
if not fmt:
    raise ValueError("Report format not found")

print(fmt["heading"])          # format set heading
print(fmt["description"])      # description
print(fmt["formats"]["types"])  # e.g., ["DICT"]
print(fmt["formats"]["attributes"])  # the attributes to include

# Get just metadata (no concrete format) using output_type ANY
meta_only = select_report_format("Referenceable", "ANY")
print(meta_only["heading"])  # no "formats" key when using ANY
```

Notes:
- The selector matches by label and also respects aliases configured in a FormatSet.
- If no specific format for the output type is found, and a format with type "ALL" exists, the "ALL" format is used as a fallback.

## Dynamic Loading (No Restart)

You can load additional report formats at runtime using environment variables and JSON files (trusted sources).

Environment variables:
- PYEGERIA_REPORT_FORMATS_JSON: Comma-separated list of JSON file paths containing format sets.
- PYEGERIA_REPORT_FORMATS_MODULES: Optional. Comma-separated list of Python callables (pkg.mod:func or pkg.mod.func) that return a FormatSetDict or dict.

Example:

```bash
export PYEGERIA_REPORT_FORMATS_JSON=$HOME/.config/pyegeria/reports.json,$HOME/team/acme_formats.json
# Optional trusted python loaders
export PYEGERIA_REPORT_FORMATS_MODULES=acme_formats.load,org_formats.loader:load_all
```

In code, refresh to load new sources:

```python
from pyegeria.base_report_formats import refresh_report_specs, list_report_specs

refresh_report_specs()
print(list_report_specs())
```

Collision policy: If any newly loaded set defines a report format label that already exists, a ReportFormatCollision error is raised and the load fails for that source. Duplicate labels are not allowed.

## Runtime Registration

You can register and unregister report formats entirely in-memory during a session.

```python
from pyegeria.base_report_formats import register_report_specs, unregister_report_format, select_report_format

# Register a temporary report format programmatically
register_report_specs({
    "My-Temp-Report": {
        "heading": "My Temp Report",
        "description": "Ad-hoc report for experiments",
        "formats": [
            {"types": ["DICT"], "attributes": [
                {"name": "Display Name", "key": "display_name"},
                {"name": "GUID", "key": "guid", "format": True}
            ]}
        ]
    }
})

# Use it immediately
fmt = select_report_format("My-Temp-Report", "DICT")
print(fmt["formats"]["attributes"])  # access attributes

# Remove it if no longer wanted
unregister_report_format("My-Temp-Report")
```

## JSON File Shape

Format sets are saved/loaded as JSON dictionaries keyed by the report label. New JSON should use attributes; legacy JSON using columns will be migrated automatically when loaded.

Example JSON:

```json
{
  "Acme-Asset": {
    "heading": "Acme Asset",
    "description": "Standard Acme asset attributes",
    "formats": [
      {
        "types": ["DICT", "MD"],
        "attributes": [
          {"name": "Display Name", "key": "display_name"},
          {"name": "Qualified Name", "key": "qualified_name"}
        ]
      }
    ]
  }
}
```

Backward compatibility: When serializing, pyegeria also emits a deprecated columns field mirroring attributes so that older readers continue to work. When loading, if attributes are not present but columns are, they are migrated to attributes.

## Migration Notes

- report_spec → report_format: New public APIs use the term report format. Legacy functions remain available for now but will be deprecated in a future release.
- columns → attributes: Models and JSON prefer attributes. Legacy columns remain supported as an alias.

Minimal migration for callers:
- Replace calls like report_spec_list() with report_format_list() when convenient.
- When defining formats in JSON/Python, prefer attributes instead of columns.

## Troubleshooting

- No matching format found: Ensure the label exists and that a format for the desired output type exists, or that an ALL format is provided.
- Collision when loading JSON: Two sources define the same label. Rename one of them or remove the conflicting source.
- Paths in PYEGERIA_REPORT_FORMATS_JSON: Use absolute paths or ~ for home; multiple paths must be comma-separated.

## Related APIs

All below are available in pyegeria.base_report_formats:
- select_report_format(kind, output_type)
- report_format_list()
- get_report_format_heading(fmt_name)
- get_report_format_description(fmt_name)
- refresh_report_formats()
- register_report_formats(new_formats, source="runtime")
- unregister_report_format(label)
- clear_runtime_report_formats()
- list_report_formats()
- get_report_registry()

Core models in pyegeria._output_format_models:
- Attribute (alias Column)
- Format (types, attributes)
- FormatSet (formats, heading, description, aliases, annotations)
