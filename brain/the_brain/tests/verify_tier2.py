"""Quick verification that all 9 Tier 2 modules import and have correct API."""
import sys
sys.path.insert(0, '.')

from core.claustrum import Claustrum
from core.reticular_formation import ReticularFormation
from core.basal_forebrain import BasalForebrain
from core.septal_nuclei import SeptalNuclei
from core.inferior_olive import InferiorOlive
from core.mammillary_bodies import MammillaryBodies
from core.bed_nucleus_stria_terminalis import BedNucleusStriaTerminalis
from core.parabrachial_nucleus import ParabrachialNucleus
from core.orbitofrontal_cortex import OrbitofrontalCortex

print('All 9 Tier 2 modules import successfully')

modules = [
    Claustrum, ReticularFormation, BasalForebrain, SeptalNuclei,
    InferiorOlive, MammillaryBodies, BedNucleusStriaTerminalis,
    ParabrachialNucleus, OrbitofrontalCortex
]

for m in modules:
    inst = m()
    for method in ['process', 'get_state', 'get_stats', 'reset', 'to_dict', 'from_yaml']:
        assert hasattr(inst, method), f'{m.__name__} missing {method}()'
    print(f'  {m.__name__}: all 6 methods present')

print('All modules verified!')
