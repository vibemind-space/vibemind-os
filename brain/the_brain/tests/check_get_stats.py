import sys
sys.path.insert(0, '.')

modules = [
    ('core.olfactory_system', 'OlfactorySystem'),
    ('core.fusiform_gyrus', 'FusiformGyrus'),
    ('core.temporoparietal_junction', 'TemporoparietalJunction'),
    ('core.posterior_parietal_cortex', 'PosteriorParietalCortex'),
    ('core.cortical_column', 'CorticalColumn'),
    ('core.pineal_gland', 'PinealGland'),
    ('core.corpus_callosum', 'CorpusCallosum'),
]

for mod_path, cls_name in modules:
    mod = __import__(mod_path, fromlist=[cls_name])
    cls = getattr(mod, cls_name)
    inst = cls()
    has_get_stats = hasattr(inst, 'get_stats')
    print(f'{cls_name}: {"OK" if has_get_stats else "MISSING get_stats"}')
