"""
The base of every page on the plan site: its stylesheet and the appearance menu its
layout shows.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any

from basstler.locations import SiteTemplate
from basstler.plan_site.theme import SiteAppearance
from basstler.render_common import TemplatePage


@dataclass(kw_only=True)
class SitePage(TemplatePage, ABC):
    """
    A page of the plan site, drawn in the theme and colour scheme its viewer picked.
    """

    stylesheet_url: str
    """
    The address of the site's stylesheet.
    """

    appearance: SiteAppearance = field(default_factory=SiteAppearance)
    """
    The themes the viewer picks from, and the default they start from.
    """

    def render_template(self, **context: Any) -> str:
        """
        :meth:`TemplatePage.render_template`, also passing what the site's layout links
        and shows.
        """
        return super().render_template(
            stylesheet_url=self.stylesheet_url,
            appearance=self.appearance,
            appearance_script_template=SiteTemplate.APPEARANCE_SCRIPT.name,
            **context,
        )
