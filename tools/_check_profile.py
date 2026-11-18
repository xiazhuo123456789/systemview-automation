import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SIM = os.path.join(ROOT, "scripts", "sim.py")
SVU = r"E:\通信原理课程设计\FM_SystemView\调频演示-可见已调波.svu"
LOG = os.path.join(os.environ["TEMP"], "check_profile_out.txt")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run(*extra):
    with open(LOG, "wb") as fh:
        p = subprocess.run([sys.executable, SIM, "--file", SVU, "--print-profile", *extra],
                           stdout=fh, stderr=fh, cwd=ROOT)
    text = open(LOG, "rb").read().decode("utf-8", "replace")
    data = json.loads(text) if text.lstrip().startswith("{") else None
    return p.returncode, data, text


cases = (("--set", ("--set", "carrier=5000", "--set", "phase=90")),
         ("none", ()),
         ("legacy", ("--carrier", "1500", "--mod-gain", "60")))

ok = True
for label, extra in cases:
    rc, d, text = run(*extra)
    if d:
        print(f"{label:7s} rc={rc} profile={d['profile']['name']} "
              f"values={d['values']} zoom={d['zoom']}")
        ok &= rc == 0
    else:
        ok = False
        print(f"{label:7s} rc={rc} FAILED\n{text[-1200:]}")

print("ALL OK" if ok else "SOME FAILED")
