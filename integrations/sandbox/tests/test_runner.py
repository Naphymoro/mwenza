"""The sandbox runner against real Docker and the research image (skipped where either is missing). Synthetic data."""

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
docker_ready = shutil.which("docker") and subprocess.run(["docker", "image", "inspect", "mwenza-research:1"], capture_output=True).returncode == 0
pytestmark = pytest.mark.skipif(not docker_ready, reason="needs Docker and the mwenza-research:1 image")

SURVEY = "group,score\n" + "\n".join(f"{'a' if i % 2 else 'b'},{50 + (i * 7) % 13 + (3 if i % 2 else 0)}" for i in range(40)) + "\n"


@pytest.fixture
def runner(tmp_path, monkeypatch):
    home = tmp_path / "deerflow"
    uploads = home / "users" / "mwenza-test" / "threads" / "t-1" / "user-data" / "uploads"
    outputs = uploads.parent / "outputs"
    uploads.mkdir(parents=True)
    outputs.mkdir()
    outputs.chmod(0o777)
    (uploads / "survey.csv").write_text(SURVEY)
    store = tmp_path / "capsules"
    monkeypatch.setenv("DEERFLOW_HOME", str(home))
    monkeypatch.setenv("RUNNER_STORE", str(store))
    monkeypatch.setenv("RUNNER_TIMEOUT", "60")
    sys.path.insert(0, str(HERE))
    module = importlib.reload(importlib.import_module("runner"))
    yield module, uploads, outputs, store
    sys.path.remove(str(HERE))


def go(module, code, language="python", inputs=("survey.csv",), **extra):
    return module.run({"owner": "mwenza-test", "thread": "t-1", "language": language, "code": code, "inputs": list(inputs), **extra})


ANALYSIS = """
import pandas as pd
from scipy import stats
data = pd.read_csv('/work/inputs/survey.csv')
a, b = data[data.group == 'a'].score, data[data.group == 'b'].score
t, p = stats.ttest_ind(a, b)
print(f"mean a {a.mean():.2f}, mean b {b.mean():.2f}, t({len(a) + len(b) - 2}) = {t:.2f}, p = {p:.3f}")
data.groupby('group').score.describe().to_csv('/work/outputs/summary.csv')
"""


def test_an_analysis_runs_and_leaves_a_complete_capsule(runner):
    module, uploads, outputs, store = runner
    capsule = go(module, ANALYSIS)
    assert capsule["exit_code"] == 0, capsule["stderr"]
    assert capsule["stdout"].startswith("mean a") and "t(38)" in capsule["stdout"]
    assert capsule["network"] == "none" and capsule["image_id"].startswith("sha256:")
    assert capsule["inputs"][0]["name"] == "survey.csv" and len(capsule["inputs"][0]["sha256"]) == 64
    assert [output["name"] for output in capsule["outputs"]] == ["summary.csv"] and "preview" in capsule["outputs"][0]
    stored = json.loads((store / capsule["capsule_id"] / "capsule.json").read_text())
    assert stored["code_sha256"] == capsule["code_sha256"] and stored["delivered_to"] == capsule["delivered_to"]
    delivered = outputs / f"analysis-{capsule['capsule_id']}"
    assert (delivered / "summary.csv").exists() and (delivered / "capsule.json").exists()
    assert capsule["delivered_to"] == f"/mnt/user-data/outputs/analysis-{capsule['capsule_id']}"


def test_rerun_agrees_for_a_deterministic_analysis_and_not_for_an_unseeded_one(runner):
    module, *_ = runner
    assert module.rerun({"capsule_id": go(module, ANALYSIS)["capsule_id"]})["agree"] is True
    random = go(module, "import random\nprint(random.random())", inputs=())
    assert module.rerun({"capsule_id": random["capsule_id"]})["agree"] is False


def test_r_runs_too(runner):
    module, *_ = runner
    capsule = go(module, "data <- read.csv('/mnt/user-data/uploads/survey.csv')\ncat(sprintf('rows %d, mean %.2f\\n', nrow(data), mean(data$score)))", language="r")
    assert capsule["exit_code"] == 0 and capsule["stdout"].startswith("rows 40"), capsule["stderr"]


def test_the_sandbox_has_no_network_and_cannot_write_outside_outputs(runner):
    module, *_ = runner
    probe = """
import socket, urllib.request
results = []
try:
    urllib.request.urlopen('http://1.1.1.1', timeout=3); results.append('network OPEN')
except Exception as exc:
    results.append('network blocked')
for path in ('/etc/mwenza-probe', '/work/inputs/new.csv', '/mnt/user-data/uploads/new.csv', '/work/code/x.py'):
    try:
        open(path, 'w').write('x'); results.append(f'{path} WRITABLE')
    except OSError:
        results.append(f'{path} read-only')
open('/work/outputs/ok.txt', 'w').write('fine')
import os; results.append(f'uid {os.getuid()}')
print('; '.join(results))
"""
    out = go(module, probe)["stdout"]
    assert "network blocked" in out and "OPEN" not in out and "WRITABLE" not in out and "uid 65534" in out


def test_a_runaway_analysis_is_stopped(runner):
    module, *_ = runner
    capsule = go(module, "while True:\n    pass", inputs=(), timeout_s=3)
    assert capsule["timed_out"] is True and capsule["exit_code"] is None and capsule["duration_s"] < 30


def test_inputs_and_identities_cannot_escape_the_chat(runner):
    module, uploads, *_ = runner
    for bad in ({"inputs": ["../../../../etc/passwd"]}, {"inputs": ["missing.csv"]}, {"owner": "../mwenza-test"}, {"thread": "t-1/../.."}, {"language": "bash"}):
        request = {"owner": "mwenza-test", "thread": "t-1", "language": "python", "code": "print(1)", "inputs": ["survey.csv"], **bad}
        with pytest.raises(module.RunError):
            module.run(request)
    os.symlink("/etc/passwd", uploads / "sneaky.csv")
    with pytest.raises(module.RunError, match="not a regular file"):
        go(module, "print(1)", inputs=("sneaky.csv",))
