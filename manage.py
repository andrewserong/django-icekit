#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "icekit.project.settings")
    os.environ.setdefault(
        "ICEKIT_PROJECT_DIR",
        os.path.join(os.path.dirname(__file__), 'icekit-project'))

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
