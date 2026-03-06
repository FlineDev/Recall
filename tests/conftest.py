"""Shared fixtures for Recall plugin tests."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "skills" / "recall" / "scripts"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
JSONL_DIR = FIXTURES_DIR / "jsonl"
MD_DIR = FIXTURES_DIR / "markdown"


def _import_script(name, filename):
   """Import a Python script as a module."""
   spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
   mod = importlib.util.module_from_spec(spec)
   spec.loader.exec_module(mod)
   return mod


@pytest.fixture
def parse_mod(monkeypatch):
   """Import parse-transcript.py as a module with stable HOME."""
   monkeypatch.setenv("HOME", "/home/alex")
   # Clear cached Path.home() if applicable
   mod = _import_script("parse_transcript", "parse-transcript.py")
   return mod


@pytest.fixture
def extract_mod():
   """Import extract-longest.py as a module."""
   return _import_script("extract_longest", "extract-longest.py")


@pytest.fixture
def apply_mod():
   """Import apply-summaries.py as a module."""
   return _import_script("apply_summaries", "apply-summaries.py")


@pytest.fixture
def jsonl_fixture():
   """Return path to a JSONL fixture by name."""
   def _get(name):
      path = JSONL_DIR / name
      assert path.exists(), f"Fixture not found: {path}"
      return path
   return _get


@pytest.fixture
def md_fixture():
   """Return path to a markdown fixture by name."""
   def _get(name):
      path = MD_DIR / name
      assert path.exists(), f"Fixture not found: {path}"
      return path
   return _get


@pytest.fixture
def write_jsonl(tmp_path):
   """Write a list of dicts as a JSONL file and return the path."""
   def _write(entries, name="test.jsonl"):
      p = tmp_path / name
      with open(p, "w") as f:
         for entry in entries:
            f.write(json.dumps(entry) + "\n")
      return p
   return _write
