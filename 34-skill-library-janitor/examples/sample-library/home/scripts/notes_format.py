#!/usr/bin/env python3
"""Formats grouped changelog entries into the house release-note shape."""

def format_notes(groups):
    return [f"## {name}\n" + "\n".join(items) for name, items in groups]
