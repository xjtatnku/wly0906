import argparse
from disaster.core import ROOT, run_scenario, metrics, snapshot, write_json

parser=argparse.ArgumentParser(description='Run a reproducible offline dispatch scenario')
parser.add_argument('--method',choices=['greedy','static','dynamic'],default='dynamic')
args=parser.parse_args()
state=run_scenario(method=args.method)
write_json(ROOT/f'results/demo_{args.method}.json',snapshot(state))
print(metrics(state))
