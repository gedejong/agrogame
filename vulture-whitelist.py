"""Whitelist for vulture (#297, Phase 4 of #293).

Add entries here for symbols that vulture flags as unused but are
intentionally kept — typically Pydantic field accessors, dataclass fields
exposed to consumers we don't import, or hooks called via events.

Each entry must reference the actual symbol so that vulture treats it as
"used" during analysis. The form is::

    from agrogame.<package> import SomeClass
    SomeClass.some_field  # type: ignore[attr-defined]

The file is included on the vulture command line:

    poetry run vulture agrogame vulture-whitelist.py --min-confidence 80

Document each entry with a one-line comment explaining why the symbol
appears unused but should be kept.
"""

# Currently empty — at --min-confidence 80 the project has zero findings.
# Each new whitelist entry should arrive in the PR that introduces it,
# alongside a comment justifying why the symbol is intentionally retained.
