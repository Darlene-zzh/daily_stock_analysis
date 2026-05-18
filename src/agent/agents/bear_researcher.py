# -*- coding: utf-8 -*-
"""Bear-side researcher for the Investment Committee debate phase.

This module is a thin re-export — both ``BullResearcher`` and
``BearResearcher`` live in :mod:`src.agent.agents.bull_researcher` because
they share prompt-construction utilities.  The split keeps the file layout
in the spec inventory satisfied while avoiding duplicated boilerplate.
"""

from __future__ import annotations

from src.agent.agents.bull_researcher import BearResearcher

__all__ = ["BearResearcher"]
