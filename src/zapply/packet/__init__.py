"""Render an approved application into the paste-ready output the human submits."""

from .build import NotApprovedError, build_approved_packets, build_packet

__all__ = ["build_packet", "build_approved_packets", "NotApprovedError"]
