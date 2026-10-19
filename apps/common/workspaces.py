"""Small URL-based local navigation. Never an authorization mechanism."""

from urllib.parse import urlencode


def section_navigation(path, sections, selected, **context):
    return [
        {
            "label": label,
            "active": key == selected,
            "url": path + "?" + urlencode({**context, "section": key}),
        }
        for key, label in sections
    ]
