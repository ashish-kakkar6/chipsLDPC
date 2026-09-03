import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKFLOW = HERE / "workflow.py"
ADAPTER = HERE / "adapters" / "chipsldpc.py"


class WorkflowTest(unittest.TestCase):
    def test_chipsldpc_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, simulator, config = root / "benchmark.txt", root / "sim", root / "config"
            source.write_text(
                "2 3 1 2 1 2 4 7\n1 0\n"
                "0.1 3\n1 2 3\n0 1 0\n1 0 1\n1 1 0\n"
                "0.2 2\n3 2 1\n0 0 0\n1 1 1\n")
            simulator.write_text("simulator artifact\n")
            config.write_text("simulator configuration\n")
            output = root / "run"
            subprocess.run([sys.executable, str(ADAPTER), str(source), str(simulator),
                            str(output), "--shard-size", "1", "--limit-per-point", "2",
                            "--max-p", "0.1", "--simulator-config", str(config)],
                           check=True)
            manifest = json.loads((output / "jobs.json").read_text())
            self.assertEqual([(job["start"], job["count"]) for job in manifest["jobs"]],
                             [(0, 1), (1, 1)])
            self.assertEqual((output / manifest["jobs"][0]["input"]).read_text().splitlines()[0],
                             "2 3 1 2 1 1 4 7")
            self.assertEqual(len(manifest["artifacts"]), 2)
            self.assertEqual(manifest["command"][-1], str(config.resolve()))
            self.assertNotIn("decoder_clock_cycles_per_shot", manifest["metrics"])

    def test_parallel_restart_and_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simulator = root / "sim.py"
            simulator.write_text(
                "import csv,sys\n"
                "p,n=open(sys.argv[1]).read().split()\n"
                "with open(sys.argv[2],'w',newline='') as f:\n"
                " w=csv.writer(f); w.writerow(('p','shot','value'))\n"
                " [w.writerow((p,i,int(p)+i)) for i in range(int(n))]\n")
            jobs = []
            for start, count in ((0, 2), (2, 2), (4, 1)):
                input_path = root / f"in-{start}.txt"
                input_path.write_text(f"7 {count}\n")
                jobs.append({"id": f"s{start}", "input": input_path.name,
                             "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                             "output": f"raw/{start}.csv", "start": start,
                             "count": count, "groups": {"p": "7"}})
            manifest = root / "jobs.json"
            manifest.write_text(json.dumps({
                "schema": "rtl-shards.v1",
                "artifacts": [{"path": simulator.name,
                               "sha256": hashlib.sha256(simulator.read_bytes()).hexdigest()}],
                "command": [sys.executable, simulator.name, "{input}", "{output}"],
                "csv": {"index": "shot", "groups": ["p"]}, "jobs": jobs}))
            command = [sys.executable, str(WORKFLOW)]
            report = root / "run.json"
            subprocess.run(command + ["run", str(manifest), "-j", "2",
                                      "--report", str(report)], check=True)
            self.assertEqual(json.loads(report.read_text())["executed_shots"], 5)
            (root / jobs[1]["output"]).write_text("corrupt\n")
            subprocess.run(command + ["run", str(manifest), "-j", "2",
                                      "--report", str(report)], check=True)
            self.assertEqual(json.loads(report.read_text())["executed_shots"], 7)
            merged = root / "merged.csv"
            subprocess.run(command + ["merge", str(manifest), str(merged)], check=True)
            with merged.open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([int(row["shot"]) for row in rows], list(range(5)))
            self.assertEqual([int(row["value"]) for row in rows], [7, 8, 7, 8, 7])


if __name__ == "__main__":
    unittest.main()
