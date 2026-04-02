"""Re-run domain router calibration after keyword improvements."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

from core.ctm_training_data import DomainRouterCalibrator, DomainRouterCalibrationCorpus
import json

print('=' * 70)
print('Re-calibrating domain router after keyword improvements')
print('=' * 70)

# Generate calibration corpus
gen = DomainRouterCalibrationCorpus()
corpus = gen.generate_calibration_corpus()

# Calibrate
calibrator = DomainRouterCalibrator()
report = calibrator.calibrate(corpus)

print(f'Overall accuracy: {report["overall_accuracy"]:.1%}')
print(f'Per-domain accuracy:')
for domain, acc in report['domain_accuracy'].items():
    print(f'  {domain}: {acc:.1%}')
print(f'Per-difficulty:')
for diff, acc in report['difficulty_accuracy'].items():
    print(f'  {diff}: {acc:.1%}')
print(f'Misclassifications: {report["misclassification_count"]}')

if report['sample_misclassifications']:
    print(f'\nSample misclassifications:')
    for m in report['sample_misclassifications'][:5]:
        print(f'  "{m["task"][:60]}..." expected={m["expected"]}, got={m["predicted"]}')

# Save updated report
with open('data/training_datasets/calibration_report_v2.json', 'w') as f:
    json.dump(report, f, indent=2)

print(f'\nSaved to data/training_datasets/calibration_report_v2.json')
