"""Run CTM training data generation, validation, and router calibration."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

from core.ctm_training_data import (
    CTMTrainingDataGenerator, CTMTrainingValidator,
    DomainRouterCalibrator, DomainRouterCalibrationCorpus
)
import json

# 1. Generate 2000 samples per domain
print('=' * 70)
print('STEP 1: Generating training datasets (2000/domain)')
print('=' * 70)
gen = CTMTrainingDataGenerator(seed=42)
summary = gen.generate_all_datasets(samples_per_domain=2000)

# 2. Validate existing training
print()
print('=' * 70)
print('STEP 2: Validating existing CTM training')
print('=' * 70)
validator = CTMTrainingValidator()
validation = validator.validate_all_domains()
print(json.dumps(validation, indent=2))

# 3. Calibrate domain router
print()
print('=' * 70)
print('STEP 3: Calibrating domain router')
print('=' * 70)
calibrator = DomainRouterCalibrator()
cal_report = calibrator.calibrate()
print(f'Overall accuracy: {cal_report["overall_accuracy"]:.1%}')
print(f'Per-domain accuracy: {json.dumps(cal_report["domain_accuracy"], indent=2)}')
print(f'Per-difficulty: {json.dumps(cal_report["difficulty_accuracy"], indent=2)}')
print(f'Misclassifications: {cal_report["misclassification_count"]}')

# 4. Find optimal thresholds
print()
print('=' * 70)
print('STEP 4: Finding optimal thresholds')
print('=' * 70)
optimal = calibrator.find_optimal_thresholds()
print(f'Best mixed_threshold: {optimal["best_mixed_threshold"]}')
print(f'Best confidence_min: {optimal["best_confidence_min"]}')
print(f'Best accuracy: {optimal["best_accuracy"]:.1%}')
print(f'Top 5 configs:')
for r in optimal['grid_search_results']:
    print(f'  mixed={r["mixed_threshold"]}, conf={r["confidence_min"]}, acc={r["accuracy"]:.1%}')

# Save calibration results
with open('data/training_datasets/calibration_report.json', 'w') as f:
    json.dump({
        'calibration': cal_report,
        'optimal_thresholds': optimal,
        'validation': validation,
    }, f, indent=2)
print()
print('Results saved to data/training_datasets/calibration_report.json')
print()
print('=' * 70)
print('ALL STEPS COMPLETE')
print('=' * 70)
