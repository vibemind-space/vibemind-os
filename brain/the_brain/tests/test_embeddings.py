from core.semantic_coherence import SemanticEncoder
import numpy as np

# Test with neural embeddings
encoder = SemanticEncoder(use_simple=False)

# Test embeddings
text1 = 'Deploy Docker container'
text2 = 'Start Docker service'
text3 = 'Eat pizza'

emb1 = encoder.encode(text1)
emb2 = encoder.encode(text2)
emb3 = encoder.encode(text3)

print(f'Embedding dimension: {len(emb1)}')
print(f'Embedding type: {type(emb1)}')

# Compute similarities
def cosine_sim(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

sim_12 = cosine_sim(emb1, emb2)
sim_13 = cosine_sim(emb1, emb3)

print(f'\nSimilarity (Deploy Docker / Start Docker): {sim_12:.3f}')
print(f'Similarity (Deploy Docker / Eat pizza): {sim_13:.3f}')
print(f'\nDifference: {sim_12 - sim_13:.3f}')

if sim_12 > 0.6 and sim_13 < 0.4:
    print('\n[+] Neural embeddings working correctly!')
else:
    print('\n[!] Using fallback (TF-IDF)')
