#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for pilog tests (hermetic local browsing)."""

from __future__ import annotations

from urllib.parse import urlparse


def block_external(page, allowed_hosts=("127.0.0.1", "localhost", "::1")):
    """Block requests to external hosts so tests never depend on the network."""

    def handler(route):
        host = urlparse(route.request.url).hostname or ""
        if host in allowed_hosts:
            route.continue_()
        else:
            # fulfill instead of abort: abort() would surface as a console
            # resource error and pollute the test output
            route.fulfill(status=200, content_type="text/html", body="")

    page.route("**/*", handler)
