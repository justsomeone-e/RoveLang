"""Import real Rove-generated Python, without executing a compiler in the host."""
import importlib.util
import json
from pathlib import Path
import sys

path = Path(sys.argv[1] if len(sys.argv) > 1 else "build/python/metrics.py").resolve()
spec = importlib.util.spec_from_file_location("rove_metrics", path)
metrics = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = metrics
spec.loader.exec_module(metrics)
samples = [42.0, 95.0, 380.0]
assert metrics.average(samples) == 517 / 3
assert metrics.minimum(samples) == 42
assert metrics.maximum(samples) == 380
assert metrics.count_over(samples, 200.0) == 1
print(json.dumps({"samples": metrics.sample_count(samples), "average_ms": metrics.average(samples), "over_200_ms": metrics.count_over(samples, 200.0)}))
