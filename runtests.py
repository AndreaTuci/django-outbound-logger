#!/usr/bin/env python
"""Run the test suite: python runtests.py [test label ...]"""

import os
import sys

import django
from django.conf import settings
from django.test.utils import get_runner

if __name__ == "__main__":
    os.environ["DJANGO_SETTINGS_MODULE"] = "tests.settings"
    django.setup()
    test_runner = get_runner(settings)(verbosity=2)
    sys.exit(bool(test_runner.run_tests(sys.argv[1:] or ["tests"])))
