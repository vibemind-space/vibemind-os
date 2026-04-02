"""Quick verification that all 14 Tier 3 modules import and have correct API."""
import sys
sys.path.insert(0, '.')

from core.substantia_nigra import SubstantiaNigra
from core.zona_incerta import ZonaIncerta
from core.red_nucleus import RedNucleus
from core.tuberomammillary_nucleus import TuberomammillaryNucleus
from core.pedunculopontine_nucleus import PedunculopontineNucleus
from core.ventral_pallidum import VentralPallidum
from core.nucleus_tractus_solitarius import NucleusTractSolitarius
from core.olfactory_system import OlfactorySystem
from core.fusiform_gyrus import FusiformGyrus
from core.temporoparietal_junction import TemporoparietalJunction
from core.posterior_parietal_cortex import PosteriorParietalCortex
from core.cortical_column import CorticalColumn
from core.pineal_gland import PinealGland
from core.corpus_callosum import CorpusCallosum

print('All 14 Tier 3 modules import successfully')

modules = [
    SubstantiaNigra, ZonaIncerta, RedNucleus, TuberomammillaryNucleus,
    PedunculopontineNucleus, VentralPallidum, NucleusTractSolitarius,
    OlfactorySystem, FusiformGyrus, TemporoparietalJunction,
    PosteriorParietalCortex, CorticalColumn, PinealGland, CorpusCallosum
]

for m in modules:
    inst = m()
    for method in ['process', 'get_state', 'get_stats', 'reset', 'to_dict', 'from_yaml']:
        assert hasattr(inst, method), f'{m.__name__} missing {method}()'
    print(f'  {m.__name__}: all 6 methods present')

print('All 14 Tier 3 modules verified!')
